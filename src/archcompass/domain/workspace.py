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
    #: The first pass this one answers, where this is a second pass. A listing uses it to
    #: pair the two rather than guessing from adjacency, and the waiting page uses it in
    #: reverse to ask whether anyone has carried on from it yet.
    elicited_from: str | None = None
    #: Which repository and branch lineage this run was about. Absent on a review of an atlas
    #: indexed before lineages existed, and on nothing else.
    repo_id: str | None = None
    branch_id: str | None = None


class RepositorySummary(DomainModel):
    version_id: str
    #: Where this checkout is. Kept as the location it has always been, beside the durable
    #: identity below rather than replaced by it.
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    #: The repository this checkout belongs to, and the branch lineage the run attached to.
    #: Both absent on an atlas indexed before lineages existed; re-indexing fills them.
    repo_id: str | None = None
    branch_name: str | None = None
    created_at: datetime
    node_count: int = 0
    edge_count: int = 0
    signal_count: int = 0
