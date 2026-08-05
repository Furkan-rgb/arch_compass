"""Ask what a new revision would find, before deciding whether to make one.

Pressing **New revision** always runs this check, and a revision that would move nothing is
reported rather than recorded. The reason is what a branch's history is for: it is the line
of what happened to the code, and an entry whose whole content is that somebody pressed a
button is noise in exactly the place a reader goes to find signal. Worse, it is expensive
noise — a recorded revision appends a case revision, a review row and a set of ledger events,
all of them repeating what the entry above them already said.

So the check is the same work the run would do, stopped at the last moment before it costs
anything: re-index the repository, resolve the case the run would judge against, detect the
candidates, and partition them against the branch's latest revision. Every step is
deterministic and local, so the answer is not an estimate of what a run would conclude — it
is the run's own first decision, taken early and thrown away if it says there is nothing to
do.

The one thing that *is* written is the atlas. Re-indexing is how the check knows what the
code says now, and refusing to write it would mean either answering from a stale atlas or
building one twice; the atlas is also a derived artefact of the code rather than a statement
about the review, so a run that follows uses it and a run that does not costs the workspace a
row nobody reads.
"""

from __future__ import annotations

from pathlib import Path

from archcompass.application.cases import CaseService
from archcompass.application.repository_index import RepositoryIndexService
from archcompass.application.reviews import ReviewService
from archcompass.domain.delta import RevisionPreflight


class RevisionPreflightService:
    def __init__(
        self,
        *,
        repositories: RepositoryIndexService,
        cases: CaseService,
        reviews: ReviewService,
    ) -> None:
        self._repositories = repositories
        self._cases = cases
        self._reviews = reviews

    def check(self, repository_root: Path) -> RevisionPreflight:
        """Whether a revision started here and now would find anything moved.

        The start step's own two opening moves — index, then resolve the branch's case — with
        the second one made read-only, and then the partition. Taking them in that order
        matters and is the reason this is one call rather than three the caller makes: the
        case is resolved *per branch*, and which branch this checkout is on is something only
        the index it just built can say.
        """

        version = self._repositories.index(repository_root)
        return self._reviews.preflight(
            repository_root=repository_root,
            revision=self._cases.continuing_case(branch_id=version.branch_id),
        )
