"""What a team has decided about one boundary, and what it argued about first.

A review is a judgement, and a judgement is not a disposition. The model says a boundary is
or is not earning its place; whether the team accepts that, waives it for a reason it can
state, or parks it until someone has time, is a different act by a different author, and it
outlives the run that prompted it. So a standing decision is its own aggregate: nothing here
changes a `BoundaryReview`, and — the invariant the whole design rests on — nothing in the
review pipeline ever reads this module. The model judges; the team disposes.

What a decision keys on follows from that. Not the review id and not the `BR-nnn` reference,
both of which are minted per run and mean nothing the next morning. It keys on
`(branch_id, boundary_fingerprint)`: the line of work a team holds opinions on, and the
structural identity of the thing the opinion is about.

There are four states and only three are written down. Accepted, waived and parked are
decisions someone took; *unreviewed* is the absence of one, and it is represented by absence
— no row, no enum member — because a stored "unreviewed" would be a claim that somebody
decided not to decide, which is not what silence means.

History is append-only, and both models here are frozen. Changing a decision appends another
one; the latest by `decided_at` is what stands, and what was thought before it stays readable.
Comments thread on the boundary rather than on any decision row, because argument routinely
precedes the decision it produces and has to survive the decision changing.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from archcompass.domain.base import DomainModel, new_id, utc_now


class DecisionState(StrEnum):
    """The three dispositions a team can record. Unreviewed is absence, not a member."""

    ACCEPTED = "accepted"
    WAIVED = "waived"
    PARKED = "parked"


class StandingDecision(DomainModel):
    """One team's disposition toward one boundary, taken against a verdict it can name.

    The four context fields are not decoration. A decision taken while looking at "this
    boundary is not earning its place" means something specific, and the same boundary can be
    judged differently by a later run — after the case is answered, after the code moves,
    after the policy corpus grows. Pinning what was actually looked at is what lets a reader
    be told "you decided this against an earlier verdict" instead of being shown a stale
    disposition with a confident face. The decision does not expire on its own: re-affirming
    is a human act.
    """

    schema_version: Literal[1] = 1
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    #: The line of work this opinion is held on. Decisions do not propagate across branches
    #: in V1; adopting a branch's decisions into another is a deliberate manual act.
    branch_id: str = Field(min_length=1)
    #: The structural identity of the boundary, from `domain.fingerprint`.
    boundary_fingerprint: str = Field(min_length=1)
    state: DecisionState
    #: Free text and honestly self-reported: there is no identity in the product yet. When
    #: there is, this becomes a validated value and no row has to move.
    author: str = Field(min_length=1)
    #: Required for a waiver, optional otherwise. A waiver without a reason is noise wearing
    #: a uniform — it silences a finding while recording nothing anyone can weigh later.
    reason: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)
    #: The verdict context: which run was on screen, which boundary in it, and what that run
    #: concluded. `review_id` and `boundary_reference` are per-run by nature and are kept as
    #: provenance only — nothing keys on them.
    review_id: str = Field(min_length=1)
    boundary_reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    material: bool
    verdict_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def a_waiver_states_its_reason(self) -> StandingDecision:
        if self.state is DecisionState.WAIVED and not (self.reason or "").strip():
            raise ValueError("A waived boundary must say why it was waived")
        return self

    def taken_on(self, *, material: bool, verdict_label: str) -> bool:
        """Whether this decision was taken against the verdict described.

        Compared on what the verdict *said* rather than on the review it was said in: a
        second run reaching the same conclusion has not invalidated anybody's judgement, and
        telling a reader to look again because a run id changed would train them to ignore
        the warning that matters.
        """

        return self.material == material and self.verdict_label == verdict_label


class DecisionComment(DomainModel):
    """One remark in the thread hanging off a boundary.

    Ordered by an ordinal assigned at write time rather than by timestamp: two remarks
    written in the same millisecond still have an order, and the order is the record.
    Append-only, like everything else here — no edits, no deletes.
    """

    schema_version: Literal[1] = 1
    comment_id: str = Field(default_factory=lambda: new_id("dcom"))
    branch_id: str = Field(min_length=1)
    boundary_fingerprint: str = Field(min_length=1)
    author: str = Field(min_length=1)
    body: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    #: Position in this boundary's thread, counting from one.
    ordinal: int = Field(default=1, ge=1)
