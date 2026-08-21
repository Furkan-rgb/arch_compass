"""Pydantic HTTP DTOs over immutable ArchitectureCase revisions."""

# pyright: reportUnusedFunction=false

from __future__ import annotations

from typing import Annotated

import yaml
from fastapi import APIRouter, Body, Query
from pydantic import Field, ValidationError

from archcompass.domain import ArchitectureCase, PolicyContext
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.presentation.web.dependencies import RuntimeDep
from archcompass.presentation.web.schemas import APIModel


class CaseAnswerDTO(APIModel):
    """What a person said when a judgement stopped to ask.

    The only way intent reaches a case, so it is the only thing a case listing has to show.
    Attributed and timestamped, because "somebody decided this, in reply to this question,
    on this date" is what a constraint could never say about itself.
    """

    question: str
    status: str
    value: str | None
    actor: str
    answered_at: str


class PolicyContextDTO(APIModel):
    user: str | None = None
    organisation: str | None = None
    repository: str | None = None

    def domain(self) -> PolicyContext:
        return PolicyContext(self.user, self.organisation, self.repository)


class CaseWrite(APIModel):
    """Everything a person may state when opening a case: which policies it can reach.

    It used to carry constraints and decisions too. Nothing in the product ever wrote one —
    no surface offered it and no review produced it — so the only way to fill them was to
    hand-author YAML, and what a review actually needs to know now arrives as an answer to a
    question it asked.
    """

    policy_context: PolicyContextDTO = Field(default_factory=PolicyContextDTO)


class CasePatch(APIModel):
    policy_context: PolicyContextDTO = Field(default_factory=PolicyContextDTO)


class CaseResponse(APIModel):
    case_id: str
    revision: int
    answers: list[CaseAnswerDTO]
    policy_context: PolicyContextDTO
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, case: ArchitectureCase) -> CaseResponse:
        return cls(
            case_id=case.id,
            revision=case.revision,
            answers=[
                CaseAnswerDTO(
                    question=item.question.text,
                    status=item.status.value,
                    value=item.value,
                    actor=item.actor,
                    answered_at=item.answered_at.isoformat(),
                )
                for item in case.answers
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
            policy_context=request.policy_context.domain()
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
    def rescope_case(
        runtime: RuntimeDep, case_id: str, request: CasePatch
    ) -> CaseResponse:
        """Re-scope which policies the case can retrieve.

        All that is left to patch. Intent is not written here — it is answered, through
        `POST /api/reviews/{id}/answers`, in reply to a question a judgement raised.
        """

        case = runtime.case_service.rescope(
            case_id, policy_context=request.policy_context.domain()
        )
        return CaseResponse.from_domain(case)

    @router.get("/api/cases/{case_id}/history")
    def case_history(runtime: RuntimeDep, case_id: str) -> list[CaseResponse]:
        return [
            CaseResponse.from_domain(item)
            for item in runtime.case_service.history(case_id)
        ]

    return router
