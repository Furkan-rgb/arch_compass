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
    #: How many the sweep found. `None` until detection finishes, which is the one moment
    #: a run has no answer to give: before it, nothing is known; after it, the length is
    #: fixed. Against `boundaries_reviewed` it is what makes a running review countable.
    boundaries_detected: int | None
    boundaries_reviewed: int
    boundaries_material: int
    created_at: str
    #: When the row last moved. On a finished review this is when it finished; on a running
    #: one it is when its last verdict landed, which is how long a reader can tell it has
    #: been quiet.
    updated_at: str
    #: What the review judged, so a listing can be read without opening every row. Absent
    #: on a review that failed before composing a report, which has no title to carry.
    case_title: str | None = None


class RepositorySummary(DomainModel):
    version_id: str
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    created_at: datetime
    node_count: int = 0
    edge_count: int = 0
    signal_count: int = 0
