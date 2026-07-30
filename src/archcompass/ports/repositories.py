"""Persistence protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import Atlas
from archcompass.domain.case import AnsweredQuestions, ArchitectureCase, CaseRevision
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


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...
