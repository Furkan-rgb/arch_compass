"""What a team has decided about a boundary, and what they said about it.

Triage, and it is append-only throughout: deciding again writes another decision rather
than editing the last one, because "we accepted this in March and waived it in August" is
the sentence a team most needs to be able to reconstruct. Decisions are filed under a
branch and a boundary fingerprint, never under a review — a review is one run, and an
opinion outlives it.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field, model_validator

from archcompass.domain.triage import DecisionComment, DecisionState, StandingDecision
from archcompass.presentation.web.dependencies import RuntimeDep
from archcompass.presentation.web.schemas import APIModel, problem_responses


class DecisionRequest(APIModel):
    """A disposition somebody took, together with the verdict they took it against.

    The verdict context is sent by the client rather than looked up here, and that is the
    point of it: it records what was actually on the reader's screen. Resolving it server-side
    from the review would record what the server believes now, which is the one thing the
    field exists to be able to disagree with.
    """

    branch_id: str = Field(min_length=1)
    boundary_fingerprint: str = Field(min_length=1)
    state: DecisionState
    author: str = Field(min_length=1)
    #: Required when waiving, and the request is refused without it rather than stored as a
    #: silent waiver.
    reason: str | None = None
    review_id: str = Field(min_length=1)
    boundary_reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    material: bool
    verdict_label: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_as_a_decision(self) -> DecisionRequest:
        """Refuse here whatever the domain would refuse, using the domain to decide.

        Building the aggregate is the check. Restating its rules in this model would be two
        places for one invariant, and the one that drifts is always the copy — while this way
        a body that cannot become a `StandingDecision` fails as a 422 naming the field, rather
        than as a 500 raised on the line that tried.
        """

        self.as_decision()
        return self

    def as_decision(self) -> StandingDecision:
        return StandingDecision(
            branch_id=self.branch_id,
            boundary_fingerprint=self.boundary_fingerprint,
            state=self.state,
            author=self.author,
            reason=self.reason,
            review_id=self.review_id,
            boundary_reference=self.boundary_reference,
            material=self.material,
            verdict_label=self.verdict_label,
        )


class BulkDecisionBoundary(APIModel):
    """One boundary in a bulk decision, with the verdict the reader took it against.

    The verdict context is per boundary and cannot be hoisted onto the request, for the same
    reason a single decision carries it: it records what was actually on screen. Forty
    boundaries were forty different verdicts, and a single `material` on the envelope would be
    a claim about all of them that is false for most.
    """

    boundary_fingerprint: str = Field(min_length=1)
    boundary_reference: str = Field(pattern=r"^BR-[0-9]{3}$")
    material: bool
    verdict_label: str = Field(min_length=1)


class BulkDecisionRequest(APIModel):
    """One disposition, taken over many boundaries at once, by one person.

    What replaced bulk baselining. The shape is deliberately the same shape as deciding one
    boundary — a state, an author, a reason where one is required — repeated over a list,
    because that is exactly what it does: it writes N standing decisions, each with a name on
    it, rather than one administrative act that silences a list nobody read.
    """

    branch_id: str = Field(min_length=1)
    state: DecisionState
    author: str = Field(min_length=1)
    #: Required when waiving, refused without it, exactly as a single decision is. A bulk
    #: waiver with no reason would be the baseline coming back wearing an author's name.
    reason: str | None = None
    review_id: str = Field(min_length=1)
    #: At least one: a bulk decision over nothing is a request that means nothing, and
    #: answering it with a cheerful zero would hide a client that failed to build its list.
    boundaries: list[BulkDecisionBoundary] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_as_decisions(self) -> BulkDecisionRequest:
        """Refuse here whatever the domain would refuse, using the domain to decide.

        Building the aggregates is the check, as it is for a single decision. Every one of them
        is built, not just the first: a list with a duplicate fingerprint or a malformed
        reference in the fortieth entry has to fail as a 422 naming the field rather than as a
        500 raised partway through the write.
        """

        self.as_decisions()
        return self

    def as_decisions(self) -> list[StandingDecision]:
        return [
            StandingDecision(
                branch_id=self.branch_id,
                boundary_fingerprint=item.boundary_fingerprint,
                state=self.state,
                author=self.author,
                reason=self.reason,
                review_id=self.review_id,
                boundary_reference=item.boundary_reference,
                material=item.material,
                verdict_label=item.verdict_label,
            )
            for item in self.boundaries
        ]


class BulkDecisionResponse(APIModel):
    """What one bulk decision wrote, and everything it now stands as."""

    branch_id: str
    recorded: int
    decisions: list[StandingDecision]


class DecisionCommentRequest(APIModel):
    """One remark in a boundary's thread. Its position is assigned by the server."""

    author: str = Field(min_length=1)
    body: str = Field(min_length=1)


class BranchDecisionsResponse(APIModel):
    """Everything one branch currently thinks about the boundaries it has opinions on.

    Comment counts are reported separately from decisions rather than beside them, because
    the two sets differ: a boundary can be argued about before anyone decides anything, and a
    count folded into the decision list would have nowhere to put that thread. A fingerprint
    missing from either map is the honest absence — undecided, or undiscussed.
    """

    branch_id: str
    #: One per boundary this branch has decided on, latest decision only.
    decisions: list[StandingDecision]
    #: Fingerprint to number of comments, for every discussed boundary on the branch.
    comment_counts: dict[str, int]


def routes() -> APIRouter:
    """Recording dispositions, reading a branch's standings, and the threads on them."""

    router = APIRouter()

    @router.get(
        "/api/branches/{branch_id}/decisions",
        responses=problem_responses(404),
    )
    def branch_decisions(runtime: RuntimeDep, branch_id: str) -> BranchDecisionsResponse:
        """What this branch currently thinks, across every boundary anyone has triaged.

        One row per boundary with an opinion, not one per boundary that exists: the
        unreviewed state is absence, and a listing that invented rows for it would be
        asserting that somebody had looked.
        """

        return BranchDecisionsResponse(
            branch_id=branch_id,
            decisions=runtime.triage_service.decisions_for_branch(branch_id),
            comment_counts=runtime.triage_service.comment_counts(branch_id),
        )

    @router.post(
        "/api/decisions",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def record_decision(runtime: RuntimeDep, request: DecisionRequest) -> StandingDecision:
        """Record a disposition toward one boundary, and return what now stands.

        Always an append, including when it contradicts what the same author said an hour
        ago. The previous decision stays readable through the history route, because "we
        accepted this in March and waived it in August" is the sentence a team most needs
        to be able to reconstruct.
        """

        return runtime.triage_service.decide(request.as_decision())

    @router.post(
        "/api/decisions/bulk",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def record_decisions(
        runtime: RuntimeDep, request: BulkDecisionRequest
    ) -> BulkDecisionResponse:
        """Take one disposition over many boundaries, and record it as many decisions.

        How a team adopts a legacy repository now that the baseline is gone. The first run over
        a code base that has been alive for years lands dozens of boundaries, and asking for
        dozens of requests would end with the tool closed — but the answer is not a button that
        silences a list nobody read. It is this: select them, decide once, and every boundary
        gets a real decision with an author, a date and a reason where one is required, all
        written together so a half-adopted branch cannot exist.

        201 because this creates records, and it is not idempotent: pressing it twice appends a
        second decision per boundary, exactly as deciding twice by hand does. That is the
        append-only rule and not an oversight — what a team thought in March stays readable
        after they change their mind in August.
        """

        decisions = runtime.triage_service.decide_many(request.as_decisions())
        return BulkDecisionResponse(
            branch_id=request.branch_id,
            recorded=len(decisions),
            decisions=decisions,
        )

    @router.get(
        "/api/decisions/{branch_id}/{fingerprint}/history",
        responses=problem_responses(404),
    )
    def decision_history(
        runtime: RuntimeDep, branch_id: str, fingerprint: str
    ) -> list[StandingDecision]:
        """Every disposition ever recorded for this boundary, oldest first."""

        return runtime.triage_service.history(branch_id, fingerprint)

    @router.get(
        "/api/decisions/{branch_id}/{fingerprint}/comments",
        responses=problem_responses(404),
    )
    def decision_comments(
        runtime: RuntimeDep, branch_id: str, fingerprint: str
    ) -> list[DecisionComment]:
        """The thread on this boundary, in the order it was written."""

        return runtime.triage_service.comments(branch_id, fingerprint)

    @router.post(
        "/api/decisions/{branch_id}/{fingerprint}/comments",
        status_code=201,
        responses=problem_responses(404, 422),
    )
    def add_decision_comment(
        runtime: RuntimeDep,
        branch_id: str,
        fingerprint: str,
        request: DecisionCommentRequest,
    ) -> DecisionComment:
        """Append one remark. No decision has to exist first, and none is implied by it."""

        return runtime.triage_service.comment(
            DecisionComment(
                branch_id=branch_id,
                boundary_fingerprint=fingerprint,
                author=request.author,
                body=request.body,
            )
        )

    return router
