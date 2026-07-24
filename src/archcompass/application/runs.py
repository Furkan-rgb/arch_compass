"""Consultation-run read use case."""

from __future__ import annotations

from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.workspace import RunSummary
from archcompass.ports.repositories import ConsultationRunRepository


class RunService:
    def __init__(self, runs: ConsultationRunRepository) -> None:
        self._runs = runs

    def show(self, run_id: str) -> ConsultationRun:
        return self._runs.get(run_id)

    def list(
        self,
        *,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[RunSummary]:
        return self._runs.list(case_id=case_id, limit=limit)
