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
from archcompass.domain.errors import ReviewNotCancellableError
from archcompass.persistence.executions import SQLiteReviewExecutionRepository
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.policies.ports import DensePolicyMatch
from archcompass.policies.retrieval import DensePolicyRetriever
from archcompass.ports.capabilities import (
    CandidateSelection,
    LoadedReviewContext,
    ReviewDraft,
    ReviewSynopsis,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet
from archcompass.workflow import ReviewWorkflowCapabilities, build_review_graph
from archcompass.workflow.report import DeterministicReviewComposer
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
    """Holds on intent, and settles once the lookups have been put in front of it.

    `settles_on_observations` is what makes this the *second* judgement rather than a repeat
    of the first: the same candidate, the same case, the same policies, plus a record — and
    a different verdict. That is the whole shape the investigation pass now has, and a stub
    that ignored its fourth argument could not tell a working rejudgement from a skipped one.
    """

    def __init__(self, *, settles_on_observations: bool = False) -> None:
        self.investigated: list[str] = []
        self._settles = settles_on_observations

    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: object,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: object = None,
    ) -> Finding:
        del subject
        if investigation is not None:
            self.investigated.append(str(candidate.id))
        if investigation is not None and investigation.lookups and self._settles:
            return Finding(
                candidate,
                Verdict.CLEARED,
                "The repository settles this.",
                (),
                candidate.evidence,
            )
        return Finding(
            candidate,
            Verdict.HELD,
            "Intent is not stated.",
            (),
            candidate.evidence,
            hinge="future variation",
        )


class FailingJudge:
    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: object,
        investigation: RecordedInvestigation | None = None,
        *,
        subject: object = None,
    ) -> Finding:
        del subject
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
    # Stamped with the revision the graph opened for this review, which is the whole of what
    # `case_revision` is for: a round is addressed by which revision asked and which of its
    # rounds, and `round` alone repeats across a case's life.
    assert completed["review"].case.answers == (
        replace(answer, case_revision=completed["review"].case.revision),
    )


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
    # The rule is the case's own now: a revision either continues an earlier one or it does
    # not, and each way of failing says which. It used to sit behind a selector protocol in
    # `policies/retrieval.py`, which is a module about retrieving policies.
    answered.validate_continuation_of(opened)

    with pytest.raises(ValueError, match="answers the previous round did not record"):
        answered.validate_continuation_of(answered)
    with pytest.raises(ValueError, match="the same case"):
        answered.validate_continuation_of(ArchitectureCase.create())


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
    # No second pass: a judgement that needed a repository fact got it while deciding.
    assert "investigate_hinges" not in rendered
    assert "rejudge_investigated" not in rendered
    assert "generate_questions" in rendered
    assert "select_candidates_for_rejudgement" in rendered


def test_a_round_being_judged_cannot_be_cancelled_out_from_under_itself(
    tmp_path: Path,
) -> None:
    """The guard `cancel`'s own docstring claimed and did not have.

    Both of its checks pass over a round that has already been answered but is still being
    judged. The snapshot is immutable, so it says `awaiting_answers` for ever; and
    `current_review_id` still names *that* snapshot for the whole of the rejudgement, because
    the next one is not filed until the end of it. So a second tab still holding the
    pre-answer page could stop a review that was mid-flight — writing `cancelled` over
    `running`, and then `_release` deleting the checkpoints the streaming driver was reading,
    out from under it. The run died with no error recorded anywhere and nothing to resume.

    The interleaving is built rather than raced. `resume_background` marks the execution
    `running` and only then starts the thread, so setting that status by hand is exactly the
    window a second tab presses the button in — and it is the one state neither of the old
    checks could see.
    """

    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create()
    database = tmp_path / "cancel.sqlite3"

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
            cases=Cases(),
            composer=Composer(),
            recorder=reviews,
        ),
        checkpointer=InMemorySaver(),
    )
    service = ReviewWorkflowService(
        graph, reviews=reviews, recorder=reviews, executions=executions
    )

    waiting = service.start(
        repository_id=repository.id,
        branch_id=repository.branch_id,
        case_id=case.id,
    )
    assert waiting.status is ReviewStatus.AWAITING_ANSWERS
    thread_id = executions.thread_for_review(waiting.id)

    # While it is genuinely waiting, stopping it is how a round ends.
    assert service.is_answerable(waiting.id) is True

    # The window: answers taken, thread running, no later snapshot filed yet. Both of the
    # facts the old checks read still point at this review.
    executions.resume(thread_id)
    assert executions.status(thread_id) == "running"
    assert executions.current_review_id(thread_id) == waiting.id
    assert reviews.get(waiting.id).status is ReviewStatus.AWAITING_ANSWERS

    with pytest.raises(ReviewNotCancellableError, match="being judged"):
        service.cancel(waiting.id)

    # And nothing was written: the execution is still the one the driver is running.
    assert executions.status(thread_id) == "running"
    assert executions.current_review_id(thread_id) == waiting.id
    assert service.is_answerable(waiting.id) is False


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
            cases=Cases(),
            composer=Composer(),
            recorder=reviews,
        ),
        checkpointer=InMemorySaver(),
    )
    service = ReviewWorkflowService(
        graph, reviews=reviews, recorder=reviews, executions=executions
    )

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
    # The one thing a listing reads off the case besides its number. A skipped answer is an
    # answer — it records that somebody was asked and declined — so this counts above zero
    # here, which is what makes the assertion about the projection rather than about a blank.
    assert summary.answer_count == len(review.case.answers) == 1
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
            cases=Cases(),
            composer=Composer(),
            recorder=reviews,
        ),
        checkpointer=InMemorySaver(),
    )
    service = ReviewWorkflowService(
        graph, reviews=reviews, recorder=reviews, executions=executions
    )

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








def _round_state(
    repository: RepositoryRef, case: ArchitectureCase
) -> tuple[dict[str, object], Candidate, Candidate]:
    """One round holding two hinged findings, of which it judged only the first.

    The shape a second review has: `candidates` is everything the detector found, and
    `selected_candidates` is the subset whose evidence moved. The other is carried unchanged
    from the previous review — its finding is in `findings`, and nothing this round
    retrieved policies for it.
    """

    changed = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    carried = Candidate.identified(
        pattern="sole_implementation",
        summary="Sink has one implementation",
        participants=(Participant("Sink", "interface"),),
    )
    hinged = {
        str(item.id): Finding(
            item, Verdict.HELD, "Intent is not stated.", (), item.evidence,
            hinge="future variation",
        )
        for item in (changed, carried)
    }
    provenance = RetrievalProvenance(
        candidate_id=changed.id, retriever="r", version="1",
        corpus_fingerprint="f", selected_policy_ids=(), query_fingerprint="q",
    )
    state: dict[str, object] = {
        "candidates": (changed, carried),
        "selected_candidates": (changed,),
        "findings": hinged,
        "case": case,
        "repository": repository,
        "atlas": RepositoryAtlas("atlas_1", repository),
        # Both, because a round that re-judges re-retrieves for everything it selected —
        # the distinction under test is `selected_candidates`, and a missing retrieval would
        # skip the carried one for the wrong reason.
        "retrievals": {
            str(item.id): RetrievedPolicySet(
                candidate_id=str(item.id), selections=(), provenance=provenance
            )
            for item in (changed, carried)
        },
        "investigations": {},
    }
    return state, changed, carried










