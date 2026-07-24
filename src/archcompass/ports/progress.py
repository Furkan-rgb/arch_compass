"""Progress reporting and persistence ports."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from archcompass.domain.execution import (
    ConsultationJob,
    ConsultationJobStatus,
    ConsultationProgressEvent,
    ProgressEventType,
)


class ConsultationProgressSink(Protocol):
    def emit(
        self,
        *,
        event_type: ProgressEventType,
        stage: str | None,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> ConsultationProgressEvent: ...


class ConsultationJobRepository(Protocol):
    def create(self, job: ConsultationJob) -> ConsultationJob: ...

    def get(self, run_id: str) -> ConsultationJob: ...

    def list(self, *, limit: int = 50) -> list[ConsultationJob]: ...

    def update(
        self,
        run_id: str,
        *,
        status: ConsultationJobStatus,
        current_stage: str | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> ConsultationJob: ...

    def append_event(
        self,
        run_id: str,
        *,
        event_type: ProgressEventType,
        stage: str | None,
        title: str,
        summary: str = "",
        data: dict[str, JsonValue] | None = None,
    ) -> ConsultationProgressEvent: ...

    def events(
        self, run_id: str, *, after_sequence: int = 0
    ) -> list[ConsultationProgressEvent]: ...

    def interrupt_unfinished(self) -> int: ...
