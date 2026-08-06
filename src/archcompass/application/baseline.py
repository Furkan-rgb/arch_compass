"""Adopting a repository, and keeping the ratchet honest afterwards.

Baselining is one action on purpose: "we have looked at all of this". A team arriving with a
legacy repository has no appetite for accepting a hundred boundaries one at a time, and an
adoption flow that demanded it would end with the tool closed. So the unit is a review — the
whole of what one run found, declared seen — and the finer-grained act of agreeing or
disagreeing with a particular verdict is a standing decision, which is a different record
with an author and a reason on it.

Two refusals live here, and both are refusals rather than best-effort behaviour because
silently baselining the wrong thing is worse than not baselining. A review that reached no
verdicts has nothing to declare seen. A review with no branch lineage has nowhere to put the
claim: the entry would be filed under nothing and the next run would find it under nothing,
which looks from the outside exactly like a baseline that does not work.
"""

from __future__ import annotations

from archcompass.domain.base import DomainModel
from archcompass.domain.baseline import BaselineEntry, baseline_entries_for
from archcompass.domain.errors import (
    BaselineEntryNotFoundError,
    ReviewHasNoBranchError,
    ReviewNotBaselineableError,
)
from archcompass.domain.review import BoundaryReview, BoundaryReviewReport, ReviewStatus
from archcompass.ports.repositories import BaselineRepository, BoundaryReviewRepository

#: The two statuses that got as far as judging. A review awaiting answers has verdicts for
#: every boundary — its questions are the residue of those verdicts — and a team is entitled
#: to declare those boundaries seen without first answering anything.
_BASELINEABLE = frozenset({ReviewStatus.SUCCEEDED, ReviewStatus.AWAITING_ANSWERS})


class BaselineOutcome(DomainModel):
    """What one act of baselining did, in the terms the person who asked for it thinks in."""

    branch_id: str
    #: How many entries this write recorded — every fingerprinted boundary in the review,
    #: whether it was already baselined or not. Deliberately not "how many were new":
    #: baselining is idempotent, and a second run of it reporting zero would read as a
    #: failure rather than as agreement with what is already stored.
    entries_written: int
    #: What the branch's baseline holds afterwards. The number that answers "is this
    #: working", and the one that stays still when the same review is baselined twice.
    baseline_size: int
    #: Boundaries the review carried that have no fingerprint and therefore cannot be
    #: baselined. Only ever non-zero for a review stored before fingerprints existed; named
    #: rather than absorbed, so a count that does not add up has an explanation.
    boundaries_without_fingerprint: int = 0


class BaselineService:
    def __init__(
        self,
        *,
        reviews: BoundaryReviewRepository,
        baselines: BaselineRepository,
    ) -> None:
        self._reviews = reviews
        self._baselines = baselines

    def baseline_review(self, review_id: str) -> BaselineOutcome:
        """Declare every boundary this review found as seen, on the branch it ran against.

        No author is recorded, and that is a statement rather than an omission. Baselining
        says a team has looked, not that it agrees; attaching a name to it would dress a
        bulk administrative act up as a hundred individual judgements, which is exactly the
        confusion standing decisions exist to avoid.
        """

        review = self._reviews.get(review_id)
        branch_id, report = self._require_baselineable(review)
        entries = baseline_entries_for(review.review_id, branch_id, report.reviewed)
        written = self._baselines.put_all(entries)
        return BaselineOutcome(
            branch_id=branch_id,
            entries_written=written,
            baseline_size=self._baselines.count_for_branch(branch_id),
            boundaries_without_fingerprint=len(report.reviewed) - len(entries),
        )

    def for_branch(self, branch_id: str) -> dict[str, BaselineEntry]:
        """What this branch has already seen, keyed by boundary fingerprint, oldest first.

        Keyed rather than listed because the two callers both look boundaries up in it: a
        run classifying its findings, and a page drawing them. A caller that wants the
        entries as a sequence takes the values, which are in insertion order.
        """

        return self._baselines.for_branch(branch_id)

    def remove_entry(self, branch_id: str, boundary_fingerprint: str) -> None:
        """Stop treating one boundary as seen, so the next run surfaces it again.

        The only way a baseline shrinks, and deliberately an explicit act: this is the
        ratchet released by hand. A fingerprint the branch never held is an error rather
        than a quiet success — a caller that mistyped it would otherwise be told the
        boundary is no longer baselined while it still is.
        """

        if not self._baselines.remove(branch_id, boundary_fingerprint):
            raise BaselineEntryNotFoundError(
                f"Branch {branch_id} has no baselined boundary {boundary_fingerprint}."
            )

    def _require_baselineable(
        self, review: BoundaryReview
    ) -> tuple[str, BoundaryReviewReport]:
        report = review.report
        if review.status not in _BASELINEABLE or report is None:
            raise ReviewNotBaselineableError(
                f"Review {review.review_id} ended as {review.status.value} and reached no "
                "verdicts, so it has no boundaries to declare seen. Run the review again."
            )
        if review.branch_id is None:
            raise ReviewHasNoBranchError(
                f"Review {review.review_id} ran against a repository indexed before branch "
                "lineages existed, so there is no branch to baseline it on. Re-index the "
                "repository to stamp its lineage, then run the review again."
            )
        return review.branch_id, report
