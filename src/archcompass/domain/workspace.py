"""Compact read models for the local workspace interface."""

from __future__ import annotations

from datetime import datetime

from archcompass.domain.base import DomainModel
from archcompass.domain.case import Confidence, RecommendationState
from archcompass.domain.consultation import (
    ConsultationFailureStage,
    ConsultationStatus,
    RecommendationDisposition,
)


class CaseSummary(DomainModel):
    case_id: str
    revision: int
    title: str
    problem_statement: str
    repository_root: str | None = None
    current_recommendation: RecommendationState | None = None
    confidence: Confidence | None = None
    updated_at: datetime


class RunSummary(DomainModel):
    run_id: str
    case_id: str
    status: ConsultationStatus
    input_case_revision: int
    result_case_revision: int | None = None
    disposition: RecommendationDisposition | None = None
    failure_stage: ConsultationFailureStage | None = None
    started_at: datetime
    completed_at: datetime


class RepositorySummary(DomainModel):
    version_id: str
    repository_identity: str
    root_path: str
    git_commit_sha: str | None = None
    created_at: datetime
    node_count: int = 0
    edge_count: int = 0
    signal_count: int = 0
