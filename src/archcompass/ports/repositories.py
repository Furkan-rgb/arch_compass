"""Persistence protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import Atlas
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.review import BoundaryReview
from archcompass.domain.review_conversation import ReviewConversation
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
        origin_run_id: str | None = None,
    ) -> CaseRevision: ...

    def history(self, case_id: str) -> list[CaseRevision]: ...

    def list(self, *, limit: int = 100) -> list[CaseSummary]: ...


class BoundaryReviewRepository(Protocol):
    """Immutable storage for one advisory review."""

    def save(self, review: BoundaryReview) -> None: ...

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


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...
