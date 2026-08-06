"""Persistence protocols."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import Atlas
from archcompass.domain.baseline import BaselineEntry
from archcompass.domain.case import AnsweredQuestions, ArchitectureCase, CaseRevision
from archcompass.domain.delta import BoundaryLineEvent
from archcompass.domain.lineage import BranchLineage, RepositoryLineage
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import ReviewConversation
from archcompass.domain.triage import DecisionComment, StandingDecision
from archcompass.domain.verdict_cache import CachedVerdict
from archcompass.domain.workspace import (
    BoundaryReviewSummary,
    CaseSummary,
    RepositorySummary,
)


class CaseRepository(Protocol):
    def create(self, case: ArchitectureCase, *, actor: str) -> CaseRevision: ...

    def get(self, case_id: str, revision: int | None = None) -> CaseRevision: ...

    def append(
        self,
        case: ArchitectureCase,
        *,
        expected_revision: int,
        event_type: str,
        actor: str,
        answered: AnsweredQuestions | None = None,
    ) -> CaseRevision: ...

    def history(self, case_id: str) -> list[CaseRevision]: ...

    def list(self, *, limit: int = 100) -> list[CaseSummary]: ...


class BoundaryReviewRepository(Protocol):
    """Storage for one advisory review, written once and visible throughout.

    A review's content is still immutable: `complete` writes the judgement exactly once and
    nothing edits it afterwards. What `begin` adds is the row's existence during the minutes
    the run takes, so a review can be found while it is being produced rather than only
    after. The only transition a stored review makes is out of `running`.
    """

    def begin(self, review: BoundaryReview) -> None: ...

    def record_progress(
        self,
        review_id: str,
        *,
        detected: int | None = None,
        reviewed: int | None = None,
        material: int | None = None,
        carried: int | None = None,
    ) -> None: ...

    def complete(self, review: BoundaryReview) -> None: ...

    def cancel(self, review_id: str) -> bool: ...

    def is_running(self, review_id: str) -> bool: ...

    def delete(self, review_id: str) -> None: ...

    def abandon_running(self, *, reason: str) -> int: ...

    def get(self, review_id: str) -> BoundaryReview: ...

    def list(
        self,
        *,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[BoundaryReviewSummary]: ...

    def latest_case_for_branch(self, branch_id: str) -> str | None: ...

    def previous_revision_for_branch(
        self, branch_id: str, *, excluding_review_id: str
    ) -> BoundaryReview | None: ...


class ReviewConversationRepository(Protocol):
    """Ordered, append-only question history about one review."""

    def create(self, conversation: ReviewConversation) -> ReviewConversation: ...

    def get(self, conversation_id: str) -> ReviewConversation: ...

    def append(self, conversation: ReviewConversation) -> ReviewConversation: ...

    def list(self, *, review_id: str) -> list[ReviewConversation]: ...


class VerdictCacheRepository(Protocol):
    """Storage for verdicts already reached, keyed by the question that produced them.

    Write-once per key: `put` on a key that already has a verdict leaves the stored one
    standing, because an unchanged question returning an unchanged answer is the guarantee
    this exists to make. Nothing removes rows — a cached verdict outlives the review that
    reached it on purpose (migration 025).
    """

    def get(self, cache_key: str) -> CachedVerdict | None: ...

    def put(self, cached: CachedVerdict) -> None: ...


class BaselineRepository(Protocol):
    """Storage for the boundaries a branch has already seen.

    Last-writer-wins per `(branch_id, boundary_fingerprint)`, unlike the write-once verdict
    cache: an entry is a claim about the present, and re-baselining a branch is that claim
    being made again. Removal is explicit and never a side effect of a run — a baseline
    shrinks only when someone says so (migration 027).
    """

    def put_all(self, entries: Iterable[BaselineEntry]) -> int: ...

    def for_branch(self, branch_id: str) -> dict[str, BaselineEntry]: ...

    def remove(self, branch_id: str, boundary_fingerprint: str) -> bool: ...

    def count_for_branch(self, branch_id: str) -> int: ...


class BoundaryLineRepository(Protocol):
    """Append-only storage for what happened to a boundary's line across revisions.

    Successions, closures and resurrections, keyed on `(branch_id, boundary_fingerprint)` —
    the same pair a standing decision and its discussion thread key on. Nothing updates and
    nothing deletes: a line's state is read as its latest event, so a closure that turns out
    to have been premature is answered by appending the resurrection rather than by removing
    the closure (migration 029).
    """

    def append_all(self, events: Iterable[BoundaryLineEvent]) -> int: ...

    def latest_for(
        self, branch_id: str, fingerprints: Iterable[str]
    ) -> dict[str, BoundaryLineEvent]: ...

    def history(
        self, branch_id: str, boundary_fingerprint: str
    ) -> list[BoundaryLineEvent]: ...


class LineageRepository(Protocol):
    """Storage for the identities a repository and its branches keep across checkouts.

    Both ids are derived from facts rather than allocated, so writing is get-or-create: the
    same repository indexed twice computes the same `repo_id` both times, and the row that
    already exists is the answer rather than a conflict.

    `set_base_branch` is the exception and is deliberately not an update: it fills in a base
    that is not yet known and leaves a known one alone, because which branch a line of work
    reads its standings through is not something a re-index should be able to move.
    """

    def get_or_create_repository(self, lineage: RepositoryLineage) -> RepositoryLineage: ...

    def get_or_create_branch(self, lineage: BranchLineage) -> BranchLineage: ...

    def set_base_branch(self, branch_id: str, base_branch_id: str) -> BranchLineage: ...

    def repository(self, repo_id: str) -> RepositoryLineage | None: ...

    def get_branch(self, branch_id: str) -> BranchLineage | None: ...

    def list_repositories(self, *, limit: int = 100) -> list[RepositoryLineage]: ...

    def list_branches(self, repo_id: str | None = None) -> list[BranchLineage]: ...


class StandingDecisionRepository(Protocol):
    """Append-only storage for what a team decided about a boundary, and what it said about it.

    Both halves key on `(branch_id, boundary_fingerprint)` and neither has an update or a
    delete: a decision is superseded by appending another, and the thread is a history rather
    than a document. Absence of a decision is the unreviewed state and is reported as absence
    — `current_for` returns `None`, and `current_for_branch` omits the boundary entirely.
    """

    def append_decision(self, decision: StandingDecision) -> StandingDecision: ...

    def append_decisions(self, decisions: Iterable[StandingDecision]) -> int: ...

    def current_for_branch(self, branch_id: str) -> list[StandingDecision]: ...

    def current_for(
        self, branch_id: str, boundary_fingerprint: str
    ) -> StandingDecision | None: ...

    def history(
        self, branch_id: str, boundary_fingerprint: str
    ) -> list[StandingDecision]: ...

    def append_comment(self, comment: DecisionComment) -> DecisionComment: ...

    def comments_for(
        self, branch_id: str, boundary_fingerprint: str
    ) -> list[DecisionComment]: ...

    def comment_counts_for_branch(self, branch_id: str) -> dict[str, int]: ...


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...
