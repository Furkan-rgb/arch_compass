"""Pydantic boundary for standing decisions over clean-break findings."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field, model_validator

from archcompass.domain.core import DecisionDisposition, StandingDecision
from archcompass.presentation.web.dependencies import RuntimeDep
from archcompass.presentation.web.schemas import APIModel, problem_responses


class DecisionRequest(APIModel):
    review_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    disposition: DecisionDisposition
    author: str = Field(min_length=1)
    reasoning: str | None = None

    @model_validator(mode="after")
    def waiver_has_reasoning(self) -> DecisionRequest:
        if self.disposition is DecisionDisposition.WAIVE and not (
            self.reasoning or ""
        ).strip():
            raise ValueError("a waiver must include reasoning")
        return self


class BulkDecisionItem(APIModel):
    candidate_id: str = Field(min_length=1)


class BulkDecisionRequest(APIModel):
    review_id: str = Field(min_length=1)
    disposition: DecisionDisposition
    author: str = Field(min_length=1)
    reasoning: str | None = None
    candidates: list[BulkDecisionItem] = Field(min_length=1)

    @model_validator(mode="after")
    def waiver_has_reasoning(self) -> BulkDecisionRequest:
        if self.disposition is DecisionDisposition.WAIVE and not (
            self.reasoning or ""
        ).strip():
            raise ValueError("a waiver must include reasoning")
        return self


class DecisionResponse(APIModel):
    id: str
    branch_id: str
    candidate_id: str
    disposition: str
    author: str
    reasoning: str | None
    decided_at: str
    review_id: str
    finding_verdict: str
    finding_model_identity: str
    finding_prompt_identity: str
    finding_retrieval_identity: str

    @classmethod
    def from_domain(cls, decision: StandingDecision) -> DecisionResponse:
        return cls(
            id=decision.id,
            branch_id=decision.branch_id,
            candidate_id=str(decision.candidate_id),
            disposition=decision.disposition.value,
            author=decision.author,
            reasoning=decision.reasoning,
            decided_at=decision.decided_at.isoformat(),
            review_id=decision.review_id,
            finding_verdict=decision.finding_verdict.value,
            finding_model_identity=decision.finding_model_identity,
            finding_prompt_identity=decision.finding_prompt_identity,
            finding_retrieval_identity=decision.finding_retrieval_identity,
        )


class BulkDecisionResponse(APIModel):
    recorded: int
    decisions: list[DecisionResponse]


class BranchDecisionsResponse(APIModel):
    branch_id: str
    decisions: list[DecisionResponse]


def routes() -> APIRouter:
    router = APIRouter()

    @router.get("/api/branches/{branch_id}/decisions")
    def branch_decisions(
        runtime: RuntimeDep, branch_id: str
    ) -> BranchDecisionsResponse:
        return BranchDecisionsResponse(
            branch_id=branch_id,
            decisions=[
                DecisionResponse.from_domain(item)
                for item in runtime.standing_decision_service.current(branch_id)
            ],
        )

    @router.post(
        "/api/decisions", status_code=201, responses=problem_responses(404, 422)
    )
    def record_decision(
        runtime: RuntimeDep, request: DecisionRequest
    ) -> DecisionResponse:
        return DecisionResponse.from_domain(
            runtime.standing_decision_service.decide(
                review_id=request.review_id,
                candidate_id=request.candidate_id,
                disposition=request.disposition,
                author=request.author,
                reasoning=request.reasoning,
            )
        )

    @router.post(
        "/api/decisions/bulk", status_code=201, responses=problem_responses(404, 422)
    )
    def record_decisions(
        runtime: RuntimeDep, request: BulkDecisionRequest
    ) -> BulkDecisionResponse:
        decisions = runtime.standing_decision_service.decide_many(
            review_id=request.review_id,
            candidate_ids=tuple(item.candidate_id for item in request.candidates),
            disposition=request.disposition,
            author=request.author,
            reasoning=request.reasoning,
        )
        return BulkDecisionResponse(
            recorded=len(decisions),
            decisions=[DecisionResponse.from_domain(item) for item in decisions],
        )

    @router.get("/api/decisions/{branch_id}/{candidate_id}/history")
    def decision_history(
        runtime: RuntimeDep, branch_id: str, candidate_id: str
    ) -> list[DecisionResponse]:
        return [
            DecisionResponse.from_domain(item)
            for item in runtime.standing_decision_service.history(branch_id, candidate_id)
        ]

    return router
