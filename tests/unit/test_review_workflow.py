from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from archcompass.domain import (
    Answer,
    AnswerStatus,
    ArchitectureCase,
    Candidate,
    CaseFacet,
    Finding,
    InvestigationLookup,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    Question,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    RetrievalProvenance,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import new_id, utc_now
from archcompass.domain.errors import ProviderError
from archcompass.persistence.executions import SQLiteReviewExecutionRepository
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.policies.retrieval import DensePolicyRetriever, RejudgeAllCandidates
from archcompass.ports.capabilities import (
    CandidateSelection,
    HingeInvestigator,
    InvestigatedFinding,
    LoadedReviewContext,
    ReviewDraft,
    ReviewSynopsis,
)
from archcompass.ports.dense_policy_index import DensePolicyMatch
from archcompass.workflow import ReviewWorkflowCapabilities, build_review_graph
from archcompass.workflow.defaults import DeterministicReviewComposer, NoHingeInvestigation
from archcompass.workflow.service import ReviewWorkflowService


class Context:
    def __init__(self, repository: RepositoryRef, case: ArchitectureCase) -> None:
        self.repository = repository
        self.case = case

    def load(
        self,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None,
    ) -> LoadedReviewContext:
        assert (repository_id, branch_id, case_id) == (
            self.repository.id,
            self.repository.branch_id,
            self.case.id,
        )
        return LoadedReviewContext(self.repository, self.case, None)


class Analyzer:
    def analyze(self, repository: RepositoryRef) -> RepositoryAtlas:
        return RepositoryAtlas("atlas-1", repository)


class Detector:
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )

    def detect(self, atlas: RepositoryAtlas) -> tuple[Candidate, ...]:
        return (self.candidate,)


class Revisions:
    def calculate(
        self,
        candidates: tuple[Candidate, ...],
        case: ArchitectureCase,
        previous: Review | None,
        repository: RepositoryRef,
        history: tuple[Review, ...] = (),
    ) -> ReviewDelta:
        return ReviewDelta(new=candidates)


class Initial:
    def select(
        self,
        candidates: tuple[Candidate, ...],
        delta: ReviewDelta,
        previous: Review | None,
        ci: bool,
    ) -> CandidateSelection:
        return CandidateSelection(candidates)


class Corpus:
    policy = Policy(
        "interfaces",
        "Interfaces",
        "Delay an interface until variation exists.",
        PolicyScope.GENERAL,
        PolicyStrength.GUIDANCE,
        "hash-1",
    )

    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]:
        return (self.policy,)


class Index:
    identity = "fake-index"
    embedding_identity = "fake-embedding"
    dimensions = 3

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        pass

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]:
        return (DensePolicyMatch("interfaces", 0.9),)


class Judge:
    def judge(self, candidate: Candidate, case: ArchitectureCase, policies: object) -> Finding:
        return Finding(
            candidate,
            Verdict.HELD,
            "Intent is not stated.",
            (),
            candidate.evidence,
            hinge="future variation",
        )


class FailingJudge:
    def judge(self, candidate: Candidate, case: ArchitectureCase, policies: object) -> Finding:
        raise RuntimeError("provider stopped")


class Questions:
    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if case.answers:
            return ()
        question = Question.create(
            text="Is another implementation planned?",
            facet=CaseFacet.EXPECTED_CHANGE,
            candidate_ids=tuple(str(item.candidate.id) for item in findings),
            round=round,
        )
        return () if question.equivalence_key in excluded_equivalence_keys else (question,)


class Cases:
    def open(self, case: ArchitectureCase) -> ArchitectureCase:
        return case.open_revision()

    def revise(self, case: ArchitectureCase, answers: tuple[Answer, ...]) -> ArchitectureCase:
        revised = case
        for answer in answers:
            revised = revised.with_answer(answer)
        return revised

    def seal(self, case: ArchitectureCase) -> ArchitectureCase:
        return case


class Composer:
    def compose(self, draft: ReviewDraft, *, waiting: bool) -> Review:
        now = utc_now()
        return Review(
            id=new_id("review"),
            sequence=1 if draft.previous is None else draft.previous.sequence + 1,
            round=draft.round,
            repository=draft.repository,
            atlas=draft.atlas,
            case=draft.case,
            findings=draft.findings,
            questions=draft.questions,
            status=ReviewStatus.AWAITING_ANSWERS if waiting else ReviewStatus.COMPLETED,
            delta=draft.delta,
            started_at=now,
            finished_at=None if waiting else now,
        )


class Recorder:
    def __init__(self) -> None:
        self.recorded: list[Review] = []

    def record(self, review: Review) -> Review:
        self.recorded.append(review)
        return review


def test_graph_interrupts_and_resumes_through_explicit_nodes(tmp_path: Path) -> None:
    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    recorder = Recorder()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=Composer(),
            recorder=recorder,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "review-thread"}}
    paused = graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
        config,
    )
    question = paused["questions"][0]
    answer = Answer(question, AnswerStatus.ANSWERED, "No", "reader", utc_now())

    completed = graph.invoke(Command(resume={"answers": [answer]}), config)

    assert [review.status for review in recorder.recorded] == [
        ReviewStatus.AWAITING_ANSWERS,
        ReviewStatus.COMPLETED,
    ]
    assert completed["review"].case.answers == (answer,)


class TwoRoundQuestions:
    """A generator that asks once, is answered, asks again, and then settles."""

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        if round > 2:
            return ()
        question = Question.create(
            text="Is another implementation planned?"
            if round == 1
            else "Is the second one owned by this team?",
            facet=CaseFacet.EXPECTED_CHANGE if round == 1 else CaseFacet.DECISION,
            candidate_ids=tuple(str(item.candidate.id) for item in findings),
            round=round,
        )
        return () if question.equivalence_key in excluded_equivalence_keys else (question,)


def test_a_review_that_asks_twice_stays_one_revision(tmp_path: Path) -> None:
    """Answering completes the revision that asked. It does not start the next one.

    Every snapshot the run files carries one sequence and one case revision — the waiting
    record of each round, and the record it finished as. What tells them apart is the round,
    which is why the round is on the review rather than only in the graph's state.
    """

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    recorder = Recorder()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=TwoRoundQuestions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=Composer(),
            recorder=recorder,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "review-thread"}}

    state = graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
        config,
    )
    for _ in range(2):
        question = state["questions"][0]
        state = graph.invoke(
            Command(
                resume={
                    "answers": [
                        Answer(question, AnswerStatus.ANSWERED, "No", "reader", utc_now())
                    ]
                }
            ),
            config,
        )

    assert [item.status for item in recorder.recorded] == [
        ReviewStatus.AWAITING_ANSWERS,
        ReviewStatus.AWAITING_ANSWERS,
        ReviewStatus.COMPLETED,
    ]
    assert {item.sequence for item in recorder.recorded} == {1}
    assert [item.round for item in recorder.recorded] == [1, 2, 3]
    # One revision opened, and both rounds recorded on it. The first snapshot is the case
    # as it was loaded, because nothing had been answered when it was filed.
    assert [item.case.revision for item in recorder.recorded] == [1, 2, 2]
    assert len(recorder.recorded[-1].case.answers) == 2


class NoQuestions:
    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        return ()


class CountingCases(Cases):
    def __init__(self) -> None:
        self.sealed: list[ArchitectureCase] = []

    def seal(self, case: ArchitectureCase) -> ArchitectureCase:
        self.sealed.append(case)
        return case


def test_a_review_that_asks_nothing_writes_no_case_revision(tmp_path: Path) -> None:
    """No answers, no revision. A number nobody put anything in is a number to read past."""

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    cases = CountingCases()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=NoQuestions(),
            rejudgements=RejudgeAllCandidates(),
            cases=cases,
            composer=Composer(),
            recorder=Recorder(),
        ),
    )

    state = graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
    )

    assert state["review"].status is ReviewStatus.COMPLETED
    assert cases.sealed == []
    assert state["review"].case.revision == case.revision


def test_rejudgement_asks_for_answers_rather_than_a_higher_number() -> None:
    """The guard reads the answers, because the revision no longer moves between rounds."""

    opened = ArchitectureCase.create().open_revision()
    question = Question.create(
        text="Who owns the boundary?",
        facet=CaseFacet.DECISION,
        candidate_ids=("candidate-1",),
        round=1,
    )
    answered = opened.with_answer(
        Answer(question, AnswerStatus.ANSWERED, "Platform", "reader", utc_now())
    )
    selector = RejudgeAllCandidates()

    assert selector.select((Detector.candidate,), opened, answered) == (Detector.candidate,)
    with pytest.raises(ValueError, match="answers the previous round did not record"):
        selector.select((Detector.candidate,), answered, answered)


def test_graph_exposes_capability_sequence_and_candidate_fanout(tmp_path: Path) -> None:
    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=Composer(),
            recorder=Recorder(),
        )
    )

    rendered = graph.get_graph().draw_mermaid()

    assert "analyze_repository" in rendered
    assert "detect_candidates" in rendered
    assert "calculate_delta" in rendered
    assert "review_candidate" in rendered
    assert "investigate_hinges" in rendered
    assert "generate_questions" in rendered
    assert "select_candidates_for_rejudgement" in rendered


def test_workflow_service_resumes_idempotently_and_records_omissions_as_skips(
    tmp_path: Path,
) -> None:
    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    database = tmp_path / "workflow.sqlite3"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    reviews = SQLiteCoreReviewRepository(connect)
    executions = SQLiteReviewExecutionRepository(connect)
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=Composer(),
            recorder=reviews,
        ),
        checkpointer=InMemorySaver(),
    )
    service = ReviewWorkflowService(graph, reviews=reviews, executions=executions)

    waiting = service.start(
        repository_id=repository.id,
        branch_id=repository.branch_id,
        case_id=case.id,
    )
    completed = service.resume(waiting.id, (), stop=True)
    duplicate = service.resume(waiting.id, (), stop=True)

    assert completed.status is ReviewStatus.COMPLETED
    assert completed.case.answers[0].status is AnswerStatus.SKIPPED
    assert duplicate.id == completed.id

    # The listing projection, which is read out of the stored document by SQLite rather
    # than by decoding it. It has to agree with the full listing on every row it shares,
    # because eight screens read one and the review page reads the other.
    summaries = service.list_summaries()
    listed = service.list()
    assert [item.id for item in summaries] == [item.id for item in listed]
    summary = summaries[0]
    review = listed[0]
    assert summary.sequence == review.sequence
    assert summary.round == review.round
    assert summary.status == review.status.value
    assert summary.repository == review.repository
    assert (summary.case_id, summary.case_revision) == (review.case.id, review.case.revision)
    assert summary.started_at == review.started_at
    assert summary.finished_at == review.finished_at
    assert summary.previous_review_id == review.previous_review_id
    assert summary.finding_count == len(review.findings)
    assert summary.question_count == len(review.questions)
    assert summary.material_count == sum(
        1 for finding in review.findings if finding.verdict is Verdict.MATERIAL
    )
    assert summary.held_count == sum(
        1 for finding in review.findings if finding.verdict is Verdict.HELD
    )
    assert summary.cleared_count == sum(
        1 for finding in review.findings if finding.verdict is Verdict.CLEARED
    )
    assert (
        summary.unchanged_count,
        summary.changed_count,
        summary.new_count,
        summary.addressed_count,
    ) == (
        len(review.delta.unchanged),
        len(review.delta.changed),
        len(review.delta.new),
        len(review.delta.addressed),
    )


def test_workflow_records_a_failed_snapshot_after_context_exists(tmp_path: Path) -> None:
    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    database = tmp_path / "failed.sqlite3"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(database)

    reviews = SQLiteCoreReviewRepository(connect)
    executions = SQLiteReviewExecutionRepository(connect)
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=FailingJudge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=Composer(),
            recorder=reviews,
        ),
        checkpointer=InMemorySaver(),
    )
    service = ReviewWorkflowService(graph, reviews=reviews, executions=executions)

    with pytest.raises(RuntimeError, match="provider stopped"):
        service.start(
            repository_id=repository.id,
            branch_id=repository.branch_id,
            case_id=case.id,
        )

    failed = service.list()
    assert len(failed) == 1
    assert failed[0].status is ReviewStatus.FAILED
    assert failed[0].failure == "RuntimeError: provider stopped"
    assert failed[0].retrieval_manifest == ()


class Synopsist:
    """A stand-in for the model asked what the review comes to."""

    def __init__(self) -> None:
        self.asked: list[tuple[int, bool]] = []

    def write(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        questions: tuple[Question, ...],
        delta: ReviewDelta,
        previous: Review | None,
        waiting: bool,
    ) -> ReviewSynopsis | None:
        self.asked.append((len(findings), waiting))
        return ReviewSynopsis("the review comes to one thing", "stub:summariser")


def test_the_summary_is_written_once_per_review_and_kept_on_it(tmp_path: Path) -> None:
    """A review is a record, so the prose about it is part of the record.

    Composed on the way to the composer rather than when somebody opens the report: two
    readers of one immutable review have to see one document, and the Markdown that is
    downloaded, attached to a pull request and rendered on the page is the same string.

    The waiting review gets its own — it is a document a reviewer may hand over part-way
    through a clarification round — which is why the writer is asked twice for one lineage.
    """

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    recorder = Recorder()
    synopsist = Synopsist()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=DeterministicReviewComposer(),
            recorder=recorder,
            synopsist=synopsist,
        ),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "summary-thread"}}
    paused = graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
        config,
    )
    question = paused["questions"][0]
    answer = Answer(question, AnswerStatus.ANSWERED, "No", "reader", utc_now())

    completed = graph.invoke(Command(resume={"answers": [answer]}), config)

    review = completed["review"]
    assert review.synopsis == "the review comes to one thing"
    assert review.synopsis_identity == "stub:summariser"
    assert review.markdown_report is not None
    assert "**In summary.** The review comes to one thing." in review.markdown_report
    assert "- **Summarised by** `stub:summariser`" in review.markdown_report
    assert [waiting for _, waiting in synopsist.asked] == [True, False]
    assert all(count > 0 for count, _ in synopsist.asked)


def test_a_workspace_with_no_summariser_composes_the_same_review(tmp_path: Path) -> None:
    """The report opens on its counts, as it did before a summary existed."""

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    graph = build_review_graph(
        ReviewWorkflowCapabilities(
            context=Context(repository, case),
            analyzer=Analyzer(),
            detector=Detector(),
            revisions=Revisions(),
            initial_candidates=Initial(),
            corpus=Corpus(),
            retriever=DensePolicyRetriever(Index(), top_k=8),
            judge=Judge(),
            questions=Questions(),
            rejudgements=RejudgeAllCandidates(),
            cases=Cases(),
            composer=DeterministicReviewComposer(),
            recorder=Recorder(),
        ),
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "no-summary-thread"}}
    graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
        config,
    )

    completed = graph.invoke(Command(resume={"answers": [], "stop": True}), config)

    review = completed["review"]
    assert review.synopsis is None
    assert review.markdown_report is not None
    assert "**In summary.**" not in review.markdown_report


def test_the_manifest_carries_provenance_only_for_findings_this_review_holds(
    tmp_path: Path,
) -> None:
    """An addressed boundary's provenance leaves with it.

    The manifest audits the policies each of this review's findings was judged against, and
    the delta reads the corpus fingerprint out of it per candidate. Keeping the entry for a
    boundary that is gone left a review claiming provenance for a finding it does not have —
    and, because that entry named an older corpus, it made every later review report that
    the corpus had moved.
    """

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    atlas = RepositoryAtlas("atlas-1", repository)
    case = ArchitectureCase.create()
    surviving = Candidate.identified(
        pattern="sole_implementation",
        summary="One adapter behind a port",
        participants=(Participant("app.Port", "abstraction"),),
    )
    gone = Candidate.identified(
        pattern="duplicated_knowledge",
        summary="A constant stated twice",
        participants=(Participant("app.limits.RETRY", "copy"),),
    )
    now = utc_now()
    previous = Review(
        "review-1",
        1,
        repository,
        atlas,
        case,
        (
            Finding(surviving, Verdict.CLEARED, "No conflict was found.", (), ()),
            Finding(gone, Verdict.CLEARED, "No conflict was found.", (), ()),
        ),
        (),
        ReviewStatus.COMPLETED,
        ReviewDelta(new=(surviving, gone)),
        now,
        now,
        retrieval_manifest=(
            RetrievalProvenance(surviving.id, "dense", "1", "old-corpus", ("policy-a",)),
            RetrievalProvenance(gone.id, "dense", "1", "old-corpus", ("policy-a",)),
        ),
    )
    draft = ReviewDraft(
        repository=repository,
        atlas=atlas,
        case=case,
        findings=(Finding(surviving, Verdict.CLEARED, "Still no conflict.", (), ()),),
        questions=(),
        delta=ReviewDelta(unchanged=(surviving,)),
        previous=previous,
        retrievals=(),
    )

    review = DeterministicReviewComposer().compose(draft, waiting=False)

    assert [str(item.candidate_id) for item in review.retrieval_manifest] == [
        str(surviving.id)
    ]


class Investigator:
    """A hinge pass whose answers a test dictates, recording what it was asked about.

    Declared beside the tests that use it rather than up top, like `Synopsist`: every
    other capability in this file is one a review cannot be produced without, and this is
    one most workspaces will never have.
    """

    def __init__(self, *, resolve: bool = False, fail: bool = False) -> None:
        self.seen: list[str] = []
        self._resolve = resolve
        self._fail = fail

    def supports_tools(self) -> bool:
        return True

    def investigate(
        self,
        finding: Finding,
        case: ArchitectureCase,
        *,
        repository: RepositoryRef,
        atlas: RepositoryAtlas,
    ) -> InvestigatedFinding:
        del case, atlas
        self.seen.append(str(finding.candidate.id))
        if self._fail:
            raise ProviderError("the provider stopped mid-investigation")
        record = RecordedInvestigation(
            candidate_id=finding.candidate.id,
            lookups=(InvestigationLookup("find_code", (("name", "Port"),), "one row"),),
            resolved=self._resolve,
            atlas_fingerprint=repository.content_id,
        )
        if not self._resolve:
            return InvestigatedFinding(
                replace(finding, investigation_identity=record.identity), record
            )
        return InvestigatedFinding(
            replace(
                finding,
                verdict=Verdict.CLEARED,
                reasoning="The repository settles this.",
                hinge=None,
                investigation_identity=record.identity,
            ),
            record,
        )


class HingeSensitiveQuestions:
    """The real generator's own gate: nothing to ask when nothing is hinged.

    `Questions` above asks regardless, which is what most of this file needs. These tests
    are about whether a settled hinge stops a person being interrupted, so they need the
    rule the production generator actually applies (`langchain.py`, `generate`).
    """

    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]:
        del excluded_equivalence_keys
        hinged = [item for item in findings if item.hinge]
        if not hinged:
            return ()
        return (
            Question.create(
                text="Is another implementation planned?",
                facet=CaseFacet.EXPECTED_CHANGE,
                candidate_ids=tuple(str(item.candidate.id) for item in hinged),
                round=round,
            ),
        )


def _investigating(
    repository: RepositoryRef,
    case: ArchitectureCase,
    investigator: HingeInvestigator | None = None,
) -> ReviewWorkflowCapabilities:
    """The capability set the investigation tests share.

    Two of these differ from the literals above, and both differences are the point:
    `HingeSensitiveQuestions` applies the rule the production generator applies, and the
    real composer is what actually keeps a manifest.
    """

    return ReviewWorkflowCapabilities(
        context=Context(repository, case),
        analyzer=Analyzer(),
        detector=Detector(),
        revisions=Revisions(),
        initial_candidates=Initial(),
        corpus=Corpus(),
        retriever=DensePolicyRetriever(Index(), top_k=8),
        judge=Judge(),
        questions=HingeSensitiveQuestions(),
        rejudgements=RejudgeAllCandidates(),
        cases=Cases(),
        # The real composer, not the stub above: these tests are about what the review
        # keeps, and the stub keeps none of the manifests.
        composer=DeterministicReviewComposer(),
        recorder=Recorder(),
        investigator=investigator or NoHingeInvestigation(),
    )


def _run(
    capabilities: ReviewWorkflowCapabilities,
    repository: RepositoryRef,
    case: ArchitectureCase,
) -> dict[str, object]:
    graph = build_review_graph(capabilities, checkpointer=InMemorySaver())
    return graph.invoke(
        {
            "repository_id": repository.id,
            "branch_id": repository.branch_id,
            "case_id": case.id,
            "case_revision": None,
            "ci": False,
        },
        {"configurable": {"thread_id": "investigation-thread"}},
    )


def test_a_hinge_the_repository_settles_never_reaches_the_question_generator(
    tmp_path: Path,
) -> None:
    """The whole point. A question a lookup answered is an interruption nobody needed."""

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    investigator = Investigator(resolve=True)

    state = _run(
        _investigating(repository, case, investigator),
        repository,
        case,
    )

    assert investigator.seen
    assert state["questions"] == ()
    assert [item.verdict for item in state["review"].findings] == [Verdict.CLEARED]


def test_a_hinge_nothing_could_settle_reaches_the_question_generator_unchanged(
    tmp_path: Path,
) -> None:
    """The behaviour that existed before this pass, now guarded rather than assumed."""

    repository = RepositoryRef("repo-2", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()

    state = _run(
        _investigating(repository, case, Investigator(resolve=False)),
        repository,
        case,
    )

    assert state["questions"]
    assert [item.hinge for item in state["review"].findings] == ["future variation"]


def test_a_review_composes_the_same_way_when_nothing_can_look_anything_up(
    tmp_path: Path,
) -> None:
    """Omitting the capability entirely is the configuration most workspaces run."""

    repository = RepositoryRef("repo-3", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()

    state = _run(_investigating(repository, case), repository, case)

    assert state["questions"]
    assert state["review"].investigation_manifest == ()


def test_an_investigation_that_fails_does_not_fail_the_review(tmp_path: Path) -> None:
    """Losing an improvement must never cost the review the question belongs to."""

    repository = RepositoryRef("repo-4", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()

    state = _run(
        _investigating(repository, case, Investigator(fail=True)),
        repository,
        case,
    )

    assert state["questions"]
    assert [item.hinge for item in state["review"].findings] == ["future variation"]


def test_the_review_keeps_what_each_hinge_checked(tmp_path: Path) -> None:
    """A hinge nobody can see the checking behind is a hinge a reader cannot weigh."""

    repository = RepositoryRef("repo-5", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()

    state = _run(
        _investigating(repository, case, Investigator(resolve=True)),
        repository,
        case,
    )

    manifest = state["review"].investigation_manifest
    assert [item.tool for item in manifest[0].lookups] == ["find_code"]
    assert manifest[0].identity == state["review"].findings[0].investigation_identity
