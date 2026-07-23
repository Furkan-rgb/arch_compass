"""Policy indexing, retrieval, and source-registration ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.policy import (
    PolicyDocument,
    PolicyIndexVersion,
    PolicySourceRegistration,
    RetrievedPolicy,
)


class PolicyIndex(Protocol):
    def rebuild(self, sources: list[Path]) -> PolicyIndexVersion: ...

    def ensure_current(self, sources: list[Path]) -> PolicyIndexVersion: ...

    def current_version(self) -> PolicyIndexVersion | None: ...

    def list_policies(self, version_id: str | None = None) -> list[PolicyDocument]: ...

    def get_policy(
        self, policy_id: str, version_id: str | None = None
    ) -> PolicyDocument: ...


class PolicyRetriever(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        version_id: str | None = None,
        max_sections_per_policy: int | None = None,
    ) -> list[RetrievedPolicy]: ...


class PolicySourceRepository(Protocol):
    def add(self, registration: PolicySourceRegistration) -> PolicySourceRegistration: ...

    def remove(self, canonical_path: str) -> bool: ...

    def list(self) -> list[PolicySourceRegistration]: ...


class PolicySourceInspector(Protocol):
    def canonicalize(self, source: Path, *, require_exists: bool = True) -> Path: ...
