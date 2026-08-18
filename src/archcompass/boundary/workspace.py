"""Validated repository-listing DTOs."""

from __future__ import annotations

from datetime import datetime

from archcompass.boundary.base import DomainModel


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
