"""Persistence protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import Atlas
from archcompass.domain.case import AnsweredQuestions, ArchitectureCase, CaseRevision
from archcompass.domain.lineage import BranchLineage, RepositoryLineage
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import ReviewConversation
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


class LineageRepository(Protocol):
    """Storage for the identities a repository and its branches keep across checkouts.

    Both ids are derived from facts rather than allocated, so writing is get-or-create: the
    same repository indexed twice computes the same `repo_id` both times, and the row that
    already exists is the answer rather than a conflict.
    """

    def get_or_create_repository(self, lineage: RepositoryLineage) -> RepositoryLineage: ...

    def get_or_create_branch(self, lineage: BranchLineage) -> BranchLineage: ...

    def repository(self, repo_id: str) -> RepositoryLineage | None: ...

    def get_branch(self, branch_id: str) -> BranchLineage | None: ...

    def list_repositories(self, *, limit: int = 100) -> list[RepositoryLineage]: ...

    def list_branches(self, repo_id: str | None = None) -> list[BranchLineage]: ...


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...
