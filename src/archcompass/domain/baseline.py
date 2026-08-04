"""What a branch has already seen, and how a run's boundaries stand against it.

A first run over a repository that has been alive for years lands dozens of boundaries at
once, and every one of them is news. The second run finds the same dozens, and if it
presents them the same way nobody reads it — the check becomes a wall that says the same
thing every time, which is indistinguishable from a check that says nothing. The baseline is
the mechanism that makes run two quieter than run one (docs/plans/company-readiness.md §3):
the team declares the boundaries it has already looked at, and later runs lead with what is
not on that list.

A baseline entry is a *current claim* about one boundary on one branch, which is what makes
it unlike the records around it. A review is immutable and a standing decision is
append-only, because both are accounts of something that happened. "This branch has seen
this boundary" is not an account of anything; it is a statement about now, and re-baselining
a branch overwrites it rather than adding a second copy of it. Nothing is lost by
overwriting: what a boundary was judged as at the time lives in the review that judged it,
and the verdict cache still holds the verdict itself.

What is *not* here is why anyone accepted the boundary. Baselining is a bulk act of
adoption — "we have looked at all of this" — and it says nothing about agreement. The
recorded judgement of a team, with an author and a reason, is a standing decision and is a
different object attached to the same key.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum

from pydantic import Field

from archcompass.domain.base import DomainModel, utc_now
from archcompass.domain.review import ReviewedBoundary


class BaselineEntry(DomainModel):
    """One boundary a branch has already seen, and what it looked like when it was seen.

    `material` and `verdict_label` are copied in rather than looked up. The entry has to be
    comparable against a later run without loading the review it came from — a run that
    compares dozens of boundaries would otherwise read dozens of reviews to answer a
    question about two booleans — and, more to the point, the review it came from can be
    deleted. What was true when the boundary was accepted is a fact worth keeping on the row
    that depends on it.
    """

    branch_id: str = Field(min_length=1)
    #: A `boundary_fingerprint`: the structural identity of the boundary, which is the only
    #: identifier that means the same thing on the run that baselined it and the run that
    #: checks against it. A `BR-nnn` reference is per review and a candidate id is per
    #: detection, so neither could anchor this.
    boundary_fingerprint: str = Field(min_length=1)
    material: bool
    #: The verdict in the vocabulary of the shape, as the review that baselined it phrased
    #: it. Kept for a reader — "you accepted this as *not earning its place*" — and not as a
    #: condition on anything; see `disposition_of` for why the label does not decide.
    verdict_label: str = Field(min_length=1)
    added_at: datetime = Field(default_factory=utc_now)
    #: Which review this was baselined from. Provenance, deliberately with no foreign key
    #: and no deletion rule, for the reason the verdict cache stores a review id the same
    #: way: the entry stays true about the structure it names whether or not the run that
    #: first presented it is still stored.
    added_from_review: str = Field(min_length=1)


class BoundaryDisposition(StrEnum):
    """Where one boundary of a run stands relative to what its branch has already seen."""

    #: No entry under this fingerprint. Either the structure is genuinely new, or it moved
    #: enough that its fingerprint changed — which is the same thing under the V1 identity
    #: rule that a renamed or relocated boundary is a re-judged boundary (§2).
    NEW = "new"
    #: Baselined, but the verdict has moved since. The structure survived and the judgement
    #: of it did not: the case gained a revision, the policy corpus changed, or a second
    #: pass answered a question the first one had to guess at. Worth surfacing precisely
    #: because nobody touched the code and the answer changed anyway.
    CHANGED = "changed"
    #: Baselined and standing as it was. Not hidden — a run reports how many of these it
    #: found and can list them — but this is the section that collapses.
    KNOWN = "known"


def disposition_of(
    boundary: ReviewedBoundary, baseline: Mapping[str, BaselineEntry]
) -> BoundaryDisposition:
    """Classify one reviewed boundary against a branch's baseline, keyed by fingerprint.

    Materiality is the whole of the comparison, and the verdict label deliberately is not
    part of it. The label is a function of the pattern and of `material`, so today the two
    cannot disagree; the reason to compare only the boolean is what happens when they can.
    Rewording a label — the vocabulary is presentation and has been revised before — would
    otherwise re-surface every baselined boundary in every repository as *changed*, an alarm
    raised by an edit to a phrase. The load-bearing question is whether the boundary is
    earning its place, and that is one bit.

    A boundary with no fingerprint is `new`, because it is in no baseline and cannot be:
    nothing can be looked up under an identity it does not have. The only boundaries in that
    state come from reviews stored before fingerprints existed, and a caller that would
    rather say nothing at all about them should check `fingerprint` before asking.
    """

    if boundary.fingerprint is None:
        return BoundaryDisposition.NEW
    entry = baseline.get(boundary.fingerprint)
    if entry is None:
        return BoundaryDisposition.NEW
    if entry.material != boundary.material:
        return BoundaryDisposition.CHANGED
    return BoundaryDisposition.KNOWN


def baseline_entries_for(
    review_id: str,
    branch_id: str,
    boundaries: Iterable[ReviewedBoundary],
) -> list[BaselineEntry]:
    """Every boundary of a review that can be baselined, as entries on one branch.

    Boundaries without a fingerprint are skipped rather than refused. They occur only in
    reviews stored before fingerprints existed, and there is nothing to record about them:
    an entry keyed by nothing could never be matched by a later run.
    """

    return [
        BaselineEntry(
            branch_id=branch_id,
            boundary_fingerprint=boundary.fingerprint,
            material=boundary.material,
            verdict_label=boundary.verdict_label,
            added_from_review=review_id,
        )
        for boundary in boundaries
        if boundary.fingerprint is not None
    ]
