"""Pydantic HTTP DTOs over immutable ArchitectureCase revisions."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from typing import Annotated

import yaml
from fastapi import APIRouter, Body, Query
from pydantic import Field, ValidationError

from archcompass.domain import (
    ArchitectureCase,
    CaseConstraint,
    CaseDecision,
    CaseFacet,
    PolicyContext,
)
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.presentation.web.dependencies import RuntimeDep
from archcompass.presentation.web.schemas import APIModel


class ConstraintDTO(APIModel):
    text: str
    facet: CaseFacet = CaseFacet.CONSTRAINT
    source: str | None = None

    def domain(self) -> CaseConstraint:
        return CaseConstraint(self.text, self.facet, self.source)


class DecisionDTO(APIModel):
    text: str
    source: str | None = None

    def domain(self) -> CaseDecision:
        return CaseDecision(self.text, self.source)


class PolicyContextDTO(APIModel):
    user: str | None = None
    organisation: str | None = None
    repository: str | None = None

    def domain(self) -> PolicyContext:
        return PolicyContext(self.user, self.organisation, self.repository)


class CaseWrite(APIModel):
    constraints: list[ConstraintDTO] = Field(
        default_factory=lambda: list[ConstraintDTO]()
    )
    decisions: list[DecisionDTO] = Field(
        default_factory=lambda: list[DecisionDTO]()
    )
    policy_context: PolicyContextDTO = Field(default_factory=PolicyContextDTO)


class CasePatch(APIModel):
    constraints: list[ConstraintDTO] | None = None
    decisions: list[DecisionDTO] | None = None
    policy_context: PolicyContextDTO | None = None


class CaseResponse(APIModel):
    case_id: str
    revision: int
    constraints: list[ConstraintDTO]
    decisions: list[DecisionDTO]
    policy_context: PolicyContextDTO
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, case: ArchitectureCase) -> CaseResponse:
        return cls(
            case_id=case.id,
            revision=case.revision,
            constraints=[
                ConstraintDTO(text=item.text, facet=item.facet, source=item.source)
                for item in case.constraints
            ],
            decisions=[
                DecisionDTO(text=item.text, source=item.source)
                for item in case.decisions
            ],
            policy_context=PolicyContextDTO(
                user=case.policy_context.user,
                organisation=case.policy_context.organisation,
                repository=case.policy_context.repository,
            ),
            created_at=case.created_at.isoformat(),
            updated_at=case.updated_at.isoformat(),
        )


def routes() -> APIRouter:
    router = APIRouter()

    @router.get("/api/cases")
    def list_cases(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[CaseResponse]:
        return [
            CaseResponse.from_domain(item)
            for item in runtime.case_service.list(limit=limit)
        ]

    @router.post("/api/cases", status_code=201)
    def create_case(runtime: RuntimeDep, request: CaseWrite) -> CaseResponse:
        case = runtime.case_service.create(
            constraints=tuple(item.domain() for item in request.constraints),
            decisions=tuple(item.domain() for item in request.decisions),
            policy_context=request.policy_context.domain(),
        )
        return CaseResponse.from_domain(case)

    @router.post("/api/cases/import-yaml", status_code=201)
    def import_case_yaml(
        runtime: RuntimeDep,
        source: Annotated[str, Body(media_type="text/yaml")],
    ) -> CaseResponse:
        try:
            request = CaseWrite.model_validate(yaml.safe_load(source))
        except (yaml.YAMLError, ValidationError, TypeError, ValueError) as error:
            raise ModelOutputValidationError(
                f"Invalid architecture case YAML: {error}"
            ) from error
        return create_case(runtime, request)

    @router.get("/api/cases/{case_id}")
    def get_case(
        runtime: RuntimeDep, case_id: str, revision: int | None = None
    ) -> CaseResponse:
        return CaseResponse.from_domain(runtime.case_service.show(case_id, revision))

    @router.patch("/api/cases/{case_id}")
    def update_case(
        runtime: RuntimeDep, case_id: str, request: CasePatch
    ) -> CaseResponse:
        case = runtime.case_service.revise(
            case_id,
            constraints=(
                None
                if request.constraints is None
                else tuple(item.domain() for item in request.constraints)
            ),
            decisions=(
                None
                if request.decisions is None
                else tuple(item.domain() for item in request.decisions)
            ),
            policy_context=(
                None if request.policy_context is None else request.policy_context.domain()
            ),
        )
        return CaseResponse.from_domain(case)

    @router.get("/api/cases/{case_id}/history")
    def case_history(runtime: RuntimeDep, case_id: str) -> list[CaseResponse]:
        return [
            CaseResponse.from_domain(item)
            for item in runtime.case_service.history(case_id)
        ]

    return router
