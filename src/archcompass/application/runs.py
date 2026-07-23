"""Consultation-run read use case."""

from __future__ import annotations

from archcompass.domain.consultation import ConsultationRun
from archcompass.ports.repositories import ConsultationRunRepository


class RunService:
    def __init__(self, runs: ConsultationRunRepository) -> None:
        self._runs = runs

    def show(self, run_id: str) -> ConsultationRun:
        return self._runs.get(run_id)
