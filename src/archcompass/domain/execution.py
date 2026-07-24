"""Persistent operational state for local consultation execution."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from archcompass.domain.base import DomainModel, new_id, utc_now
from archcompass.domain.diagnostics import FailureDiagnostic


class ConsultationJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_WITH_WARNINGS = "succeeded_with_warnings"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ProgressEventType(StrEnum):
    QUEUED = "queued"
    STAGE_STARTED = "stage_started"
    ARTIFACT_AVAILABLE = "artifact_available"
    STAGE_COMPLETED = "stage_completed"
    WARNING = "warning"
    COMPLETED = "completed"
    FAILED = "failed"


class ConsultationJob(DomainModel):
    schema_version: Literal[1] = 1
    run_id: str = Field(default_factory=lambda: new_id("run"))
    case_id: str
    input_case_revision: int = Field(ge=1)
    repository_root: str | None = None
    status: ConsultationJobStatus = ConsultationJobStatus.QUEUED
    current_stage: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    warning: str | None = None
    error: str | None = None
    failure_diagnostics: list[FailureDiagnostic] = Field(
        default_factory=list[FailureDiagnostic]
    )


class ConsultationProgressEvent(DomainModel):
    schema_version: Literal[1] = 1
    run_id: str
    sequence: int = Field(ge=1)
    event_type: ProgressEventType
    stage: str | None = None
    title: str
    summary: str = ""
    data: dict[str, JsonValue] = Field(default_factory=dict[str, JsonValue])
    occurred_at: datetime = Field(default_factory=utc_now)
