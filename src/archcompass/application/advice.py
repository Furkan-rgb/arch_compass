"""Advice orchestration use case including durable report output."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.application.reports import ReportService
from archcompass.domain.consultation import ConsultationRun
from archcompass.ports.progress import ConsultationProgressSink


class ConsultationUseCase(Protocol):
    def advise(
        self,
        case_id: str,
        *,
        atlas_version_id: str | None = None,
        repository_root: Path | None = None,
        run_id: str | None = None,
        input_case_revision: int | None = None,
        progress: ConsultationProgressSink | None = None,
    ) -> ConsultationRun: ...


class AdviceService:
    def __init__(
        self,
        *,
        consultation: ConsultationUseCase,
        reports: ReportService,
    ) -> None:
        self._consultation = consultation
        self._reports = reports

    def advise(
        self,
        case_id: str,
        *,
        repository_root: Path | None = None,
        atlas_version_id: str | None = None,
        run_id: str | None = None,
        input_case_revision: int | None = None,
        progress: ConsultationProgressSink | None = None,
    ) -> ConsultationRun:
        run = self._consultation.advise(
            case_id,
            repository_root=repository_root,
            atlas_version_id=atlas_version_id,
            run_id=run_id,
            input_case_revision=input_case_revision,
            progress=progress,
        )
        self._reports.write(run)
        return run
