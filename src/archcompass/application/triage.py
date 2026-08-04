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
"""

from __future__ import annotations

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

    def decisions_for_branch(self, branch_id: str) -> list[StandingDecision]:
        self._require_branch(branch_id)
        return self._decisions.current_for_branch(branch_id)

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
