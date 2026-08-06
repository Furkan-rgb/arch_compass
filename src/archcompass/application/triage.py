"""Recording what a team decided about a boundary, and what it said about it.

Thin on purpose. Whether a waiver states a reason, whether an author is blank, what a
`BR-nnn` reference looks like — all of that is the domain model's, enforced wherever a
`StandingDecision` is constructed rather than only on the path through this service. What is
left here is the one check no model can make about itself: that the branch being decided on is
a branch this workspace has actually seen.

Nothing in this module is reachable from a review. `ReviewService` never reads decisions, and
this never reads verdicts — the verdict context on a decision arrives as data from the caller
who was looking at it. That separation is the design's one invariant: the model judges, the
team disposes, and neither is allowed to move the other.

Reading is where the standings stopped being thin. A branch answers with what it decided and,
where it decided nothing, with what the branch it came from decided — the read-through that
replaced the baseline as the reason a boundary is quiet. The walk itself is
`application/standings.py`; what is here is the merge, in one place, so no caller can assemble
a different answer to "what stands on this branch".
"""

from __future__ import annotations

from collections.abc import Sequence

from archcompass.application.standings import branch_chain
from archcompass.domain.errors import BranchNotFoundError
from archcompass.domain.triage import DecisionComment, StandingDecision
from archcompass.ports.repositories import LineageRepository, StandingDecisionRepository


class TriageService:
    def __init__(
        self,
        *,
        decisions: StandingDecisionRepository,
        lineages: LineageRepository,
    ) -> None:
        self._decisions = decisions
        self._lineages = lineages

    def decide(self, decision: StandingDecision) -> StandingDecision:
        """Append one disposition, and hand back what now stands for that boundary.

        What now stands is what was just written: appends are the only writer, and the row
        just committed is the latest by construction.
        """

        self._require_branch(decision.branch_id)
        return self._decisions.append_decision(decision)

    def decide_many(
        self, decisions: Sequence[StandingDecision]
    ) -> list[StandingDecision]:
        """Record one disposition over many boundaries, as many decisions, in one write.

        The act a team adopting a legacy repository actually performs, and the replacement for
        bulk baselining. The difference is the whole point: baselining silenced a list nobody
        had to look at and recorded no author, while this writes a real decision per boundary
        with a name on it — the same rows, the same history, the same append-only semantics as
        deciding one at a time. Nothing here is a bulk *object*; there is no record that these
        N decisions were taken together, because that is a fact about the afternoon rather than
        about any boundary.

        One transaction, so a partial adoption cannot exist. Half a branch decided and half not
        would be indistinguishable from a team that had worked through half the list, and the
        caller would have no way to find out which half.
        """

        for decision in decisions:
            self._require_branch(decision.branch_id)
        self._decisions.append_decisions(decisions)
        return list(decisions)

    def standings_for_branch(self, branch_id: str | None) -> dict[str, StandingDecision]:
        """What governs this branch, keyed by fingerprint, read through to its base.

        The branch's own decisions win; where it has none, the branch it came from answers.
        Assembled by walking the chain furthest-first and letting each nearer branch overwrite,
        which is "own always wins" expressed as an order rather than as a condition.

        Tolerant of a branch nothing has stored, unlike every write here: the first pull
        request against a fresh repository asks this about a lineage no run has ever produced,
        and the honest answer is that nobody has decided anything. A *write* to an unknown
        branch is a mistake worth refusing; a read of one is a question with an answer.
        """

        standings: dict[str, StandingDecision] = {}
        for candidate in reversed(branch_chain(self._lineages, branch_id)):
            for decision in self._decisions.current_for_branch(candidate):
                standings[decision.boundary_fingerprint] = decision
        return standings

    def decisions_for_branch(self, branch_id: str) -> list[StandingDecision]:
        """Everything that stands on this branch, inherited entries included.

        Sorted by fingerprint, as the storage layer sorts what it returns, so a listing has a
        stable order whichever branch of the chain each row came from. An inherited decision
        names its own `branch_id`, which is how a reader tells "we decided this" from "`main`
        decided this and we have not disagreed".
        """

        self._require_branch(branch_id)
        standings = self.standings_for_branch(branch_id)
        return [standings[key] for key in sorted(standings)]

    def comment_counts(self, branch_id: str) -> dict[str, int]:
        return self._decisions.comment_counts_for_branch(branch_id)

    def history(self, branch_id: str, boundary_fingerprint: str) -> list[StandingDecision]:
        self._require_branch(branch_id)
        return self._decisions.history(branch_id, boundary_fingerprint)

    def comment(self, comment: DecisionComment) -> DecisionComment:
        """Append one remark to a boundary's thread, wherever that boundary is in triage.

        No decision has to exist first. Argument routinely precedes judgement, and a thread
        that could only be opened after somebody had already decided would be a thread for
        agreeing in.
        """

        self._require_branch(comment.branch_id)
        return self._decisions.append_comment(comment)

    def comments(self, branch_id: str, boundary_fingerprint: str) -> list[DecisionComment]:
        self._require_branch(branch_id)
        return self._decisions.comments_for(branch_id, boundary_fingerprint)

    def _require_branch(self, branch_id: str) -> None:
        """Refuse a branch this workspace has never seen.

        An unknown branch id is almost always a repository that has not been indexed here, and
        accepting the write would file the team's decisions under an identity nothing will ever
        look up again — silently, since nothing else in the system reads these rows.

        The fingerprint gets no such check. A boundary that no run has reported yet is a
        perfectly ordinary thing to hold an opinion about — a decision outlives the runs on
        both sides of it — and there is no table that could be asked.
        """

        if self._lineages.get_branch(branch_id) is None:
            raise BranchNotFoundError(
                f"No branch {branch_id} is known to this workspace. Index the repository it "
                "belongs to, then record the decision again."
            )
