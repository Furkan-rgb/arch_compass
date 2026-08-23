"""Persistence protocols, and the projections they answer with.

A projection is here rather than in `domain/` on purpose. `ReviewSummary` is what this
boundary *returns* — a handful of columns read without decoding the several megabytes a
stored review actually is — so it is persistence-facing vocabulary, not a concept the
domain has. It sat in `reviews.py` beside the SQLite class that builds it, which meant a
protocol naming it dragged a concrete implementation module into every caller's imports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from archcompass.analysis.atlas import Atlas
from archcompass.domain import ArchitectureCase, RepositoryRef, Review
from archcompass.repositories.lineage import BranchLineage, RepositoryLineage
from archcompass.repositories.records import (
    RepositorySummary,
    SourceOrigin,
)


@dataclass(frozen=True, slots=True)
class ReviewSummary:
    """One review as a listing reads it, assembled without opening the review.

    A listing shows a handful of facts about a review, and a stored review is most of a
    repository's atlas — several megabytes of it. Listing a hundred used to decode a
    hundred of those documents into a full object graph so that five integers could be
    counted off it, which is the same work as opening every review at once and then
    throwing all of them away.

    So this is read out of the stored document by SQLite: the columns where there is a
    column, `json_extract` and `json_each` where there is not, and the blob never enters
    Python at all. `repository` is the real domain record because every field of it is one
    `json_extract` away and a listing already knows how to render one.

    Deliberately not a `Review` with the expensive fields left empty. A record that says it
    is a review and has no findings would eventually be handed to something that needs
    them, and would answer that there are none.
    """

    id: str
    sequence: int
    round: int
    status: str
    repository: RepositoryRef
    case_id: str
    case_revision: int
    started_at: datetime
    finished_at: datetime | None = None
    previous_review_id: str | None = None
    #: How many questions this review's case has answers on. A revision number says which
    #: case a run will continue and not how much is in it, and "continues revision 4" with no
    #: second number is the same sentence for a case somebody has filled in and one that was
    #: opened and never answered.
    answer_count: int = 0
    finding_count: int = 0
    material_count: int = 0
    held_count: int = 0
    cleared_count: int = 0
    question_count: int = 0
    unchanged_count: int = 0
    changed_count: int = 0
    new_count: int = 0
    addressed_count: int = 0


class ReviewSnapshots(Protocol):
    """Reading the immutable reviews a branch has accumulated.

    One protocol where there were five. `StandingDecisionService` and the conversation
    service wanted `get`, `ArchitectureCaseService` wanted `latest_for_branch`, and
    `SQLiteContextLoader` wanted two — so one SQLite class was described by five partial
    protocols in four modules, three of them a single method named `get`. A one-method
    protocol called `get` is not a boundary; it is a type alias with a ceremony, and a
    reader asking what a review store can do got five partial answers and no whole one.

    Writing is not here. `ReviewRecorder` in `capabilities.py` is the graph's seam for
    that, and it is a real one — `CachingReviewRecorder` wraps it.
    """

    def get(self, review_id: str) -> Review: ...

    def latest_for_branch(self, branch_id: str) -> Review | None: ...

    def history_for_branch(self, branch_id: str) -> tuple[Review, ...]: ...


class CaseSnapshots(Protocol):
    """Reading and writing the revisions of one architecture case.

    One protocol where there were four — `CaseSnapshots`, `CoreCaseSnapshots`,
    `CaseSnapshotStore` and `CaseSnapshotRecorder`, in four modules, describing one SQLite
    class between them. Two of them were a single `record`.

    `next_revision` belongs with the rest because opening a revision and writing it are the
    same store's business: `PersistentCaseReviser` asks for a free number when a review
    opens one and writes the snapshot when that review finishes, and a protocol carrying
    only half of that would describe half a reviser.
    """

    def get(self, case_id: str, revision: int | None = None) -> ArchitectureCase: ...

    def record(self, case: ArchitectureCase) -> ArchitectureCase: ...

    def history(self, case_id: str) -> tuple[ArchitectureCase, ...]: ...

    def list(self, *, limit: int = 100) -> tuple[ArchitectureCase, ...]: ...

    def next_revision(self, case_id: str) -> int: ...


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


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_repositories(self, *, limit: int = 100) -> list[RepositorySummary]:
        """Each indexed repository once, described by the newest atlas built of it.

        `limit` counts repositories. It used to count atlas versions, which is the same
        number only in a workspace where nothing has ever been indexed twice.
        """
        ...


class ScopeSelectionRepository(Protocol):
    """Which folders a repository is reviewed without, kept beyond the request that said so.

    Persisted rather than passed, because the caller that has to apply a scope is usually not
    the caller that chose it: a freshness check recomputes the repository's fingerprint from a
    stored atlas, and a fingerprint taken over a different set of files would mark that atlas
    stale forever.

    Keyed by canonical root path, which is what a stored atlas holds.
    """

    def record(self, root_path: str, excluded_paths: Sequence[str]) -> None:
        """Remember this scope for this repository, replacing whatever was chosen before.

        An empty sequence is a scope: it says "review everything", and it is recorded so a
        later index that names no scope keeps reviewing everything rather than falling back
        to a choice that was deliberately undone.
        """
        ...

    def get(self, root_path: str) -> tuple[str, ...] | None:
        """The folders this repository is reviewed without, or `None` if nobody has chosen.

        `None` and `()` are different answers and both are ordinary. Nobody choosing is the
        common case — every repository indexed from the CLI — and choosing everything is
        what somebody who opened the folder list and cleared it meant.
        """
        ...


class SourceOriginRepository(Protocol):
    """Where a fetched directory came from, for a workspace that may not keep the directory."""

    def record(self, origin: SourceOrigin) -> None: ...

    def get(self, root_path: str) -> SourceOrigin | None:
        """The address behind this directory, or `None` for one nobody fetched.

        `None` is an ordinary answer rather than a miss: a bundled example was never
        fetched, and neither was a folder somebody picked on their own machine.
        """
        ...
