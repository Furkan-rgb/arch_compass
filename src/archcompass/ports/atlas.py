"""Repository analysis, source, freshness, and atlas-query ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.atlas import (
    Atlas,
    AtlasQuery,
    AtlasQueryResult,
    RepositoryContentIdentity,
)


class RepositoryAnalyzer(Protocol):
    def analyze(self, root: Path) -> Atlas: ...


class RepositoryIdentityReader(Protocol):
    def current_identity(self, root: Path) -> RepositoryContentIdentity: ...


class SourceReader(Protocol):
    def excerpt(
        self,
        root: Path,
        relative_path: str,
        start_line: int,
        end_line: int,
        *,
        max_lines: int,
    ) -> str: ...


class AtlasFreshnessChecker(Protocol):
    def ensure_fresh(self, atlas: Atlas) -> None: ...


class AtlasQueryService(Protocol):
    def execute(self, atlas: Atlas, query: AtlasQuery) -> AtlasQueryResult: ...
