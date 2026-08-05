"""What stands over a boundary, and what is therefore still asking for attention.

The baseline is gone and the standings are the memory in its place. That swap turns on one
sentence, and this module is where the sentence lives: **a boundary needs attention when it is
material and nobody has decided anything about it.** Quiet is no longer a button somebody
pressed over a list they did not read — it is the model having cleared the boundary, or a
person having accepted, waived or parked it with their name on the record. Every quiet row is
quiet for a reason a reader can point at, which is the whole of what the baseline could not
say.

Two lookups make that sentence true more often than a naive read would, and both are here
rather than at the call sites, because three copies of "which decision applies to this
boundary" is three places for them to disagree:

**Through the base branch.** A branch scoped strictly to itself has decided nothing on the day
it is created, so a pull request would re-open every boundary its repository settled on `main`
years ago — the wall of noise, arriving as a blocked pull request. A branch therefore reads
through to the branch it came from: its own record always wins, and where it has none the
base's applies. The walk is bounded and cycle-safe because the chain is application data, set
one row at a time, and nothing in the schema can promise it is a line rather than a ring.

**Through a succession.** A renamed participant is a new fingerprint, and the standing the team
took is filed under the old one. Phase A recorded which fingerprint a boundary succeeded
precisely so the decision could carry across; reading it here is what makes the carry real
rather than merely recorded. Without it, renaming a class would silently re-open a decided
boundary — and a rename is not a decision.

Nothing here reads storage. The chain walk takes the repository it needs as an argument, and
everything else is a pure function of a boundary and a map somebody else assembled.
"""

from __future__ import annotations

from collections.abc import Mapping

from archcompass.domain.review import ReviewedBoundary
from archcompass.domain.triage import StandingDecision
from archcompass.ports.repositories import LineageRepository

#: How far a read-through will walk before it stops. A base chain is a team's own topology —
#: a release branch off a develop branch off `main` is three, and anything beyond that is a
#: workspace nobody is navigating by hand. The bound is not really about depth: it is what
#: guarantees termination in a shape a database constraint cannot police, alongside the visited
#: set that catches an outright ring.
MAX_BASE_DEPTH = 8


def branch_chain(lineages: LineageRepository, branch_id: str | None) -> list[str]:
    """This branch, then the branch it came from, then that one's, nearest first.

    Order is the whole contract: a caller merges in reverse so the nearest record wins, and
    "a branch's own decision always wins" is that ordering and nothing more. There is no rule
    about recency, deliberately — a base branch that decided something yesterday does not
    override what this branch decided last month, because the question is whose opinion
    governs here rather than whose is newest.

    A branch nothing has stored answers with itself alone rather than with nothing. The id is
    derived from the repository and the name, so asking about a branch this workspace has not
    indexed is an ordinary first call, and a caller that gets back an empty list would read it
    as "no standings" when the honest answer is "none inherited".
    """

    if branch_id is None:
        return []
    chain = [branch_id]
    seen = {branch_id}
    current = branch_id
    while len(chain) < MAX_BASE_DEPTH:
        lineage = lineages.get_branch(current)
        base = None if lineage is None else lineage.base_branch_id
        # A base that is already in the chain is a cycle, and stopping is the only sane
        # answer: following it would loop for ever, and refusing the read would take a
        # team's standings away over a row nobody can see.
        if base is None or base in seen:
            break
        chain.append(base)
        seen.add(base)
        current = base
    return chain


def standing_for(
    boundary: ReviewedBoundary, standings: Mapping[str, StandingDecision]
) -> StandingDecision | None:
    """The decision that governs this boundary, or `None` where nobody has taken one.

    `standings` is already read through the base chain by the caller, so what is left here is
    the succession: the boundary's own fingerprint first, then the fingerprint it succeeded.
    Own first because a team that decided about the new shape has spoken about the new shape,
    and the carried decision is what applies only until they do.

    A boundary with no fingerprint — a review stored before fingerprints existed — has no
    identity to look anything up under, and answers `None` without asking.
    """

    if boundary.fingerprint is None:
        return None
    decision = standings.get(boundary.fingerprint)
    if decision is not None:
        return decision
    if boundary.succeeds is None:
        return None
    return standings.get(boundary.succeeds)


def needs_attention(
    boundary: ReviewedBoundary, standings: Mapping[str, StandingDecision]
) -> bool:
    """Whether this boundary is still asking something of the team.

    Material and undecided, and nothing else. Not *new* — the word the baseline made
    meaningless — and not *changed*, which as often as not meant the model had been upgraded.
    A cleared verdict is evidence the advisor looked, so it is not a finding; a decided
    boundary has an author and a date on it, so it is not an open question.

    All three states silence, parking included. Parking is a decision — "we have seen this and
    it is not now" — recorded by a person under their own name, and treating it as though
    nobody had answered would leave a team with no way to say that except by accepting
    something they do not accept.
    """

    return boundary.material and standing_for(boundary, standings) is None


__all__ = ["MAX_BASE_DEPTH", "branch_chain", "needs_attention", "standing_for"]
