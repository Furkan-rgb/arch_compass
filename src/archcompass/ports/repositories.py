"""Persistence protocols."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import Atlas
from archcompass.domain.case import ArchitectureCase, CaseRevision
from archcompass.domain.consultation import ConsultationRun
from archcompass.domain.workspace import CaseSummary, RepositorySummary, RunSummary


class CaseRepository(Protocol):
    def create(self, case: ArchitectureCase, *, actor: str) -> CaseRevision: ...

    def get(self, case_id: str, revision: int | None = None) -> CaseRevision: ...

    def append(
        self,
        case: ArchitectureCase,
        *,
        expected_revision: int,
        event_type: str,
        actor: str,
        origin_run_id: str | None = None,
    ) -> CaseRevision: ...

    def history(self, case_id: str) -> list[CaseRevision]: ...

    def list(self, *, limit: int = 100) -> list[CaseSummary]: ...


class ConsultationRunRepository(Protocol):
    def save(self, run: ConsultationRun) -> None: ...

    def get(self, run_id: str) -> ConsultationRun: ...

    def list(
        self,
        *,
        case_id: str | None = None,
        limit: int = 100,
    ) -> list[RunSummary]: ...


class ConsultationCommitRepository(Protocol):
    def commit_success(
        self,
        run: ConsultationRun,
        case: ArchitectureCase,
        *,
        expected_revision: int,
    ) -> CaseRevision: ...


class AtlasRepository(Protocol):
    def save(self, atlas: Atlas) -> None: ...

    def get(self, version_id: str) -> Atlas: ...

    def latest_for_path(self, root: Path) -> Atlas | None: ...

    def list_versions(self, *, limit: int = 100) -> list[RepositorySummary]: ...
