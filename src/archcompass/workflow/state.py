"""Execution-only state passed between review graph capabilities."""

from __future__ import annotations

from typing import Annotated, TypedDict

from archcompass.domain import (
    Answer,
    ArchitectureCase,
    Candidate,
    Finding,
    Policy,
    Question,
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    ReviewDelta,
)
from archcompass.ports.capabilities import ReviewDraft, ReviewSynopsis
from archcompass.ports.policy_retrieval import RetrievedPolicySet


def merge_mappings[Value](
    left: dict[str, Value], right: dict[str, Value]
) -> dict[str, Value]:
    return {**left, **right}


class ReviewInput(TypedDict):
    repository_id: str
    branch_id: str
    case_id: str
    case_revision: int | None
    ci: bool


class ReviewState(ReviewInput):
    repository: RepositoryRef
    case: ArchitectureCase
    previous_case: ArchitectureCase
    previous_review: Review | None
    review_history: tuple[Review, ...]
    atlas: RepositoryAtlas
    candidates: tuple[Candidate, ...]
    selected_candidates: tuple[Candidate, ...]
    candidate: Candidate
    corpus: tuple[Policy, ...]
    retrieval: RetrievedPolicySet
    retrievals: Annotated[dict[str, RetrievedPolicySet], merge_mappings]
    findings: Annotated[dict[str, Finding], merge_mappings]
    investigations: Annotated[dict[str, RecordedInvestigation], merge_mappings]
    delta: ReviewDelta
    questions: tuple[Question, ...]
    pending_answers: tuple[Answer, ...]
    excluded_equivalence_keys: frozenset[str]
    round: int
    stop_requested: bool
    synopsis: ReviewSynopsis | None
    draft: ReviewDraft
    review: Review


class CandidateReviewOutput(TypedDict):
    retrievals: dict[str, RetrievedPolicySet]
    findings: dict[str, Finding]
