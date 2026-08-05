"""The line a boundary keeps across revisions, and what one revision changed.

A review used to be a complete account of a repository: every boundary detected, every one
judged, every one asked about. That is the right shape for the first revision on a branch
and the wrong one for the ninth. The ninth revision is read by someone who has already read
the eighth, and telling them again about forty boundaries nothing has touched is how a check
stops being read at all — the same failure the baseline was invented to solve and solved by
declaring things fine rather than by knowing they were unchanged.

So a revision is judged against the branch's previous one, and every boundary lands in
exactly one state:

- **carried** — the inputs are identical, so the verdict, the standing and the silence all
  carry. No model is called and no question may be asked about it. This is most boundaries
  in most revisions, and it is what makes the rest legible.
- **judged** — new, or something it rests on moved: its own source, the case, the policy
  corpus, the model, the prompt. Only these may earn an elicitation question, which is what
  makes re-asking a settled thing structurally impossible rather than merely cached away.
- **succeeded** — the shape moved (a participant renamed, one added) and this boundary was
  matched to the one that disappeared. The standing carries across wearing a visible mark;
  the succession is recorded so the line is auditable. A successor is judged too, since a
  changed shape is by definition a changed input.
- **addressed** — present in the previous revision and matched by nothing here. The loop
  closing, and the best news the tool can deliver. Nothing is deleted: the standing and its
  discussion key on `(branch_id, fingerprint)` and stay exactly where they are, so a
  fingerprint that ever comes back resurfaces with its history rather than starting blank.

`judged` is about what this revision put back on the table, not about whether a model call
was paid for it. A boundary that vanished in revision 5 and returned unchanged in revision 9
is judged — it is news again — and its verdict may still be served from the cache, because
the question it asks has an answer already.

Nothing here reads or writes storage, and nothing here is written by a model. Succession
matching in particular is a pure function of two sets of shapes, so the same pair of
revisions always produces the same successions.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from archcompass.domain.atlas import FindingPattern
from archcompass.domain.base import DomainModel, new_id, utc_now


class BoundaryState(StrEnum):
    """Where one boundary stands relative to the branch's previous revision."""

    CARRIED = "carried"
    JUDGED = "judged"
    SUCCEEDED = "succeeded"
    ADDRESSED = "addressed"


class JudgedBecause(StrEnum):
    """Which input moved, for a boundary this revision did not carry.

    Named rather than left to the reader to infer. "Changed" on its own is the word that
    broke the baseline — a reader hears it as a statement about their code, and it was just
    as often the model having been upgraded or a policy having been edited. Every value here
    is something a person can point at.
    """

    #: Not present in the previous revision, and no predecessor matched it.
    NEW = "new"
    #: Present in the previous revision, and the participants' source moved under it.
    CONTENT = "content"
    #: The shape itself moved and a predecessor was matched — the successor case.
    SHAPE = "shape"
    #: The case was revised: an answer recorded, or the problem statement edited.
    CASE = "case"
    #: The policy corpus this boundary would be weighed under is not the same corpus.
    POLICIES = "policies"
    #: A different reasoning model reached the previous verdict.
    MODEL = "model"
    #: The judgement prompt itself changed, which is a change of question.
    PROMPT = "prompt"
    #: Closed as addressed in an earlier revision on this branch, and back now.
    RESURFACED = "resurfaced"


class BoundaryShape(DomainModel):
    """A boundary's structural identity, as succession matching sees it.

    Deliberately not the whole candidate. Matching compares what a boundary *is* — which
    detector recognised it and what participates in it — and a summary, a measurement or a
    rationale would only give two revisions more ways to look different while describing the
    same situation.
    """

    fingerprint: str = Field(min_length=1)
    pattern: FindingPattern
    #: Participants' qualified names. Sorted by the caller or not; matching sorts nothing
    #: into identity and compares them as a set.
    participants: list[str] = Field(min_length=1)


class AddressedBoundary(DomainModel):
    """A boundary the previous revision had and this one does not.

    Everything a reader needs to be told what closed is copied here rather than joined back
    to the review that last held it. Partly cost — a summary line should not open a stored
    report — and mostly durability: the review that judged it can be deleted, and what was
    addressed is exactly the fact that must not go with it.
    """

    fingerprint: str = Field(min_length=1)
    pattern: FindingPattern
    #: The candidate's own summary, so the closure can be named in the words the boundary was
    #: presented in rather than in a sentence composed about it.
    title: str = Field(min_length=1)
    #: What it was last judged as. A material boundary that has gone is the loop closing; a
    #: cleared one that has gone is ordinary tidying, and a reader should be able to tell.
    material: bool
    verdict_label: str = Field(min_length=1)
    #: The revision that last saw it, and the reference it wore there, so the closure can be
    #: traced back to the run it was last evidence in.
    last_seen_in_review: str = Field(min_length=1)
    last_reference: str = Field(pattern=r"^BR-[0-9]{3}$")


class RevisionDelta(DomainModel):
    """What this revision changed against the branch's previous one, counted and named.

    Stored on the review rather than joined at read time, which is the opposite of how the
    baseline comparison works and deliberately so. A baseline disposition is a fact about
    *now* — it moves the moment somebody baselines something — but a delta is a fact about a
    pair of revisions that are both immutable. Computing it again later could only produce
    the same answer or a wrong one, and it would need the previous revision to still exist to
    produce either.
    """

    #: The revision this one was judged against. `None` on a branch's first revision, and on
    #: a run whose atlas predates branch lineages — there is nothing to have compared with,
    #: which is not the same as having compared and found no difference.
    previous_review_id: str | None = None
    #: True when there was no previous revision. Every boundary is then `judged`, and none of
    #: that means anything moved.
    first_revision: bool = True
    carried: int = Field(default=0, ge=0)
    judged: int = Field(default=0, ge=0)
    succeeded: int = Field(default=0, ge=0)
    addressed: int = Field(default=0, ge=0)
    #: How many of the judged boundaries are fingerprints that were closed as addressed on
    #: this branch and have come back.
    resurfaced: int = Field(default=0, ge=0)
    #: The closures themselves, whole, because they are the only part of the partition with
    #: no row of its own in the report — an addressed boundary is not in `reviewed`, having
    #: not been detected here.
    addressed_boundaries: list[AddressedBoundary] = Field(
        default_factory=list[AddressedBoundary]
    )

    @property
    def quiet(self) -> bool:
        """Whether this revision changed nothing anyone has to look at."""

        return self.judged == 0 and self.succeeded == 0 and self.addressed == 0


class BoundaryLineEventType(StrEnum):
    """The three things that can happen to a boundary's line, as opposed to its verdict."""

    #: The shape moved and a successor was matched. Recorded on the *predecessor*, naming
    #: what it became.
    SUCCEEDED = "succeeded"
    #: Gone with no successor. The line is closed, not deleted.
    ADDRESSED = "addressed"
    #: A closed line's fingerprint has reappeared on this branch.
    RESURFACED = "resurfaced"


class BoundaryLineEvent(DomainModel):
    """One thing that happened to one boundary's line on one branch.

    Append-only and immutable, like `standing_decisions` and for the same reason: this is an
    account of something that happened, and an account that can be rewritten is not evidence
    of anything. The state of a line is read as its latest event, never stored as a column
    that could disagree with the history behind it.

    Keyed on `(branch_id, boundary_fingerprint)` — the same pair a standing decision and its
    discussion thread key on, which is what makes resurrection free: nothing has to be moved
    or restored when a fingerprint comes back, because nothing was ever taken away.
    """

    schema_version: Literal[1] = 1
    event_id: str = Field(default_factory=lambda: new_id("line"))
    branch_id: str = Field(min_length=1)
    boundary_fingerprint: str = Field(min_length=1)
    event: BoundaryLineEventType
    #: The revision that observed it. Provenance, and never a condition on the event
    #: applying: a line stays closed whether or not the run that closed it is still stored.
    review_id: str = Field(min_length=1)
    #: What this fingerprint became, on a `succeeded` event and on no other.
    successor_fingerprint: str | None = None
    recorded_at: datetime = Field(default_factory=utc_now)


def match_successions(
    *,
    gone: Sequence[BoundaryShape],
    appeared: Sequence[BoundaryShape],
) -> dict[str, str]:
    """Pair disappeared shapes with appeared ones, successor fingerprint to predecessor.

    Git's rename detection, applied to boundaries. A participant renamed produces a new
    fingerprint, and without this the standing decision silently orphans while the boundary
    reads as brand new — the worst of both, since nobody is told anything was lost.

    Two shapes are the same question when they come from the same detector and share at
    least half their participants. Half rather than a strict majority, because the commonest
    shape in the catalogue has exactly two participants — an abstraction and its single
    implementation — and renaming one of them shares exactly one of two. A strict majority
    would make rename detection impossible for precisely the case it exists for.

    The pattern must match exactly. Two detectors reporting on overlapping code are reporting
    different things about it, and carrying an accepted "this indirection is fine" onto "this
    constant has no owner" would be a decision attributed to a team that never took it.

    Matching is one-to-one and greedy over the strongest overlaps first, with fingerprints
    breaking ties, so the same pair of revisions always produces the same successions. A
    predecessor is claimed by at most one successor and vice versa: a boundary that split in
    two has one successor recorded and the other reported as new, which is the honest half of
    an answer no amount of overlap arithmetic can settle.
    """

    scored: list[tuple[int, str, str]] = []
    for successor in appeared:
        after = set(successor.participants)
        for predecessor in gone:
            if predecessor.pattern is not successor.pattern:
                continue
            before = set(predecessor.participants)
            shared = len(before & after)
            # `max` rather than `min`: a boundary that kept one participant and gained four
            # is not the same question wearing a new name, and comparing against the smaller
            # side would call it one.
            if shared * 2 < max(len(before), len(after)):
                continue
            scored.append((shared, successor.fingerprint, predecessor.fingerprint))

    matched: dict[str, str] = {}
    claimed: set[str] = set()
    for _, successor_fingerprint, predecessor_fingerprint in sorted(
        scored, key=lambda item: (-item[0], item[1], item[2])
    ):
        if successor_fingerprint in matched or predecessor_fingerprint in claimed:
            continue
        matched[successor_fingerprint] = predecessor_fingerprint
        claimed.add(predecessor_fingerprint)
    return matched
