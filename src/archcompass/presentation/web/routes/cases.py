"""The architecture case: writing one, reading it, and reading how it got that way.

Every route here is a thin pass through `case_service`. A case is a revision series rather
than a document, which is why reading takes an optional revision and why the history is a
route of its own.
"""

# Pyright cannot see FastAPI's decorator registration as a function reference.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from typing import Annotated

import yaml
from fastapi import APIRouter, Body, Query
from pydantic import ValidationError

from archcompass.domain.case import ArchitectureCase, CaseRevision, CaseUpdate
from archcompass.domain.errors import ModelOutputValidationError
from archcompass.domain.workspace import CaseSummary
from archcompass.presentation.web.dependencies import RuntimeDep


def routes() -> APIRouter:
    """Listing, writing, reading and amending architecture cases."""

    router = APIRouter()

    @router.get("/api/cases")
    def list_cases(
        runtime: RuntimeDep,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> list[CaseSummary]:
        return runtime.case_service.list(limit=limit)

    @router.post("/api/cases", status_code=201)
    def create_case(runtime: RuntimeDep, case: ArchitectureCase) -> CaseRevision:
        return runtime.case_service.create(case)

    @router.post("/api/cases/import-yaml", status_code=201)
    def import_case_yaml(
        runtime: RuntimeDep,
        source: Annotated[str, Body(media_type="text/yaml")],
    ) -> CaseRevision:
        try:
            case = ArchitectureCase.model_validate(yaml.safe_load(source))
        except (yaml.YAMLError, ValidationError, TypeError, ValueError) as error:
            raise ModelOutputValidationError(f"Invalid architecture case YAML: {error}") from error
        return runtime.case_service.create(case)

    @router.get("/api/cases/{case_id}")
    def get_case(runtime: RuntimeDep, case_id: str, revision: int | None = None) -> CaseRevision:
        return runtime.case_service.show(case_id, revision)

    @router.patch("/api/cases/{case_id}")
    def update_case(runtime: RuntimeDep, case_id: str, update: CaseUpdate) -> CaseRevision:
        return runtime.case_service.update(case_id, update)

    @router.get("/api/cases/{case_id}/history")
    def case_history(runtime: RuntimeDep, case_id: str) -> list[CaseRevision]:
        return runtime.case_service.history(case_id)

    return router
