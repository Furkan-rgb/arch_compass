from __future__ import annotations

import sqlite3
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
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
    ReviewStatus,
    Verdict,
)
from archcompass.domain._support import new_id, utc_now
from archcompass.persistence.executions import SQLiteReviewExecutionRepository
from archcompass.persistence.reviews import SQLiteCoreReviewRepository
from archcompass.policies.retrieval import DensePolicyRetriever, RejudgeAllCandidates
from archcompass.ports.capabilities import (
    CandidateSelection,
    LoadedReviewContext,
    ReviewDraft,
)
from archcompass.ports.dense_policy_index import DensePolicyMatch
from archcompass.workflow import ReviewWorkflowCapabilities, build_review_graph
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
    def revise(self, case: ArchitectureCase, answers: tuple[Answer, ...]) -> ArchitectureCase:
        revised = case
        for answer in answers:
            revised = revised.with_answer(answer)
        return revised


class Composer:
    def compose(self, draft: ReviewDraft, *, waiting: bool) -> Review:
        now = utc_now()
        return Review(
            id=new_id("review"),
            sequence=1 if draft.previous is None else draft.previous.sequence + 1,
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


def test_workflow_records_a_failed_snapshot_after_context_exists(tmp_path: Path) -> None:
    repository = RepositoryRef("repo-1", tmp_path.resolve(), "branch-1", "content-1")
    case = ArchitectureCase.create("Keep the boundary explicit")
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
