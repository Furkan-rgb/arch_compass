"""Compact read models for the local workspace interface."""

from __future__ import annotations

from datetime import datetime

from archcompass.domain.base import DomainModel


class CaseSummary(DomainModel):
    case_id: str
    revision: int
    title: str
    problem_statement: str
    repository_root: str | None = None
    updated_at: datetime


class BoundaryReviewSummary(DomainModel):
    """One row of a review listing, read from columns rather than a stored document."""

    review_id: str
    case_id: str
    case_revision: int
    atlas_version_id: str
    status: str
    boundaries_reviewed: int
    boundaries_material: int
    created_at: str


class RepositorySummary(DomainModel):
    version_id: str
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    created_at: datetime
    node_count: int = 0
    edge_count: int = 0
    signal_count: int = 0
