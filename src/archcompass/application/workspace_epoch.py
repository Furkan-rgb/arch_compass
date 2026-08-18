"""Application facade for explicit workspace schema-epoch operations."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class SchemaEpoch(Protocol):
    def export_legacy(self, destination: Path) -> Path: ...

    def reset(self) -> Path | None: ...


class WorkspaceEpochService:
    def __init__(self, epoch: SchemaEpoch) -> None:
        self._epoch = epoch

    def export_legacy(self, destination: Path) -> Path:
        return self._epoch.export_legacy(destination)

    def reset(self) -> Path | None:
        return self._epoch.reset()
