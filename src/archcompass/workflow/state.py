"""Execution-only state passed between review graph capabilities."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass
class ReviewRuntime:
    """What a judgement needs that must never be written down.

    A `Send` payload is checkpointed once per branch, so anything travelling in it is stored
    as many times as there are candidates — one round of six cost 21 MB of `__pregel_tasks`
    when the atlas went that way. The atlas is also the one thing a per-candidate judgement
    cannot do without: it is what its tools answer from.

    So it travels as run-scoped context instead, which LangGraph passes to every node of a
    run and never serialises. `subject` is set by the dispatch that fans the candidates out,
    from state it already holds, and it is set again on every dispatch — which is what makes
    this survive a clarification round. A resumed review starts with a fresh context object,
    and the second fan-out repopulates it before any branch reads it.

    `None` where a review runs without tools at all: the deterministic provider, and any
    caller that has not set a context. The judgement then reads only its dossier.
    """

    subject: JudgementSubject | None = None


@dataclass(frozen=True)
class JudgementSubject:
    """The repository and atlas one round's judgements are about."""

    repository: RepositoryRef
    atlas: RepositoryAtlas


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
    #: Whether this review has opened a case revision of its own. False until the first
    #: answers arrive, so a review that settled without asking, or that nobody answered,
    #: seals nothing.
    case_opened: bool
    stop_requested: bool
    synopsis: ReviewSynopsis | None
    draft: ReviewDraft
    review: Review


class CandidateReviewOutput(TypedDict):
    """What one candidate's branch hands back, and nothing else.

    A key missing here does not fail: it is written inside the branch and silently dropped
    at its edge. `investigations` was, and the review composed with an empty manifest while
    every finding carried the identity of a trace nothing had stored.
    """

    retrievals: dict[str, RetrievedPolicySet]
    findings: dict[str, Finding]
    investigations: dict[str, RecordedInvestigation]
