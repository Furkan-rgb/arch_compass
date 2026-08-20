"""Application seams used one-for-one by the review graph.

The protocols describe ArchCompass operations, never a library.  LangGraph sequences them;
adapters decide whether an implementation uses LangChain, SQLite, or deterministic Python.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from archcompass.domain import (
    Answer,
    ArchitectureCase,
    Candidate,
    Finding,
    Policy,
    Question,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.ports.policy_retrieval import RetrievedPolicySet


class RepositoryAnalyzer(Protocol):
    def analyze(self, repository: RepositoryRef) -> RepositoryAtlas: ...


class CandidateDetector(Protocol):
    def detect(self, atlas: RepositoryAtlas) -> tuple[Candidate, ...]: ...


class RevisionCalculator(Protocol):
    def calculate(
        self,
        candidates: tuple[Candidate, ...],
        case: ArchitectureCase,
        previous: Review | None,
        repository: RepositoryRef,
        history: tuple[Review, ...] = (),
    ) -> ReviewDelta: ...


class PolicyRetriever(Protocol):
    def retrieve(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        corpus: tuple[Policy, ...],
    ) -> RetrievedPolicySet: ...


class ArchitectureJudge(Protocol):
    def judge(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        policies: RetrievedPolicySet,
    ) -> Finding: ...


@dataclass(frozen=True, slots=True)
class JudgementRequest:
    """One candidate, and everything the model needs to judge it."""

    candidate: Candidate
    case: ArchitectureCase
    policies: RetrievedPolicySet


@runtime_checkable
class BatchArchitectureJudge(Protocol):
    """A judge that can put a whole review to the model in one submission.

    A hosted provider meters interactive calls per minute and a batch of them per day,
    which is the difference between a review of forty candidates failing halfway through
    and finishing. Whether that is available depends on the model selected right now, not
    on how the graph was built, so `supports_batch` is asked at dispatch time rather than
    answered once at startup.
    """

    def supports_batch(self) -> bool: ...

    def judge_all(
        self, requests: Sequence[JudgementRequest]
    ) -> tuple[Finding, ...]: ...


class QuestionGenerator(Protocol):
    def generate(
        self,
        case: ArchitectureCase,
        findings: tuple[Finding, ...],
        *,
        round: int,
        excluded_equivalence_keys: frozenset[str],
    ) -> tuple[Question, ...]: ...


class RejudgementSelector(Protocol):
    def select(
        self,
        candidates: tuple[Candidate, ...],
        previous_case: ArchitectureCase,
        revised_case: ArchitectureCase,
    ) -> tuple[Candidate, ...]: ...


class CaseReviser(Protocol):
    def revise(
        self, case: ArchitectureCase, answers: Sequence[Answer]
    ) -> ArchitectureCase: ...


@dataclass(frozen=True, slots=True)
class ReviewDraft:
    repository: RepositoryRef
    atlas: RepositoryAtlas
    case: ArchitectureCase
    findings: tuple[Finding, ...]
    questions: tuple[Question, ...]
    delta: ReviewDelta
    previous: Review | None
    retrievals: tuple[RetrievedPolicySet, ...]


class ReviewComposer(Protocol):
    def compose(self, draft: ReviewDraft, *, waiting: bool) -> Review: ...


class ReviewRecorder(Protocol):
    def record(self, review: Review) -> Review: ...


class PolicyCorpus(Protocol):
    def policies_for(self, repository: RepositoryRef) -> tuple[Policy, ...]: ...


@dataclass(frozen=True, slots=True)
class LoadedReviewContext:
    repository: RepositoryRef
    case: ArchitectureCase
    previous_review: Review | None
    review_history: tuple[Review, ...] = ()


class ContextLoader(Protocol):
    def load(
        self,
        repository_id: str,
        branch_id: str,
        case_id: str,
        case_revision: int | None,
    ) -> LoadedReviewContext: ...


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    selected: tuple[Candidate, ...]
    carried_findings: tuple[Finding, ...] = ()


class InitialCandidateSelector(Protocol):

    def select(
        self,
        candidates: tuple[Candidate, ...],
        delta: ReviewDelta,
        previous: Review | None,
        ci: bool,
    ) -> CandidateSelection: ...
