"""Policy source-registration ports.

No index and no retriever. Both existed to rank a corpus against a query, and nothing
ranks it any more: the judging stage is shown every policy in one request and the
conversation's background carries the corpus whole (master plan §6A, ADR 0013). What is
left is the pair of things that were never about retrieval — where policies come from, and
how a directory of Markdown becomes documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from archcompass.domain.policy import PolicyDocument, PolicySourceRegistration


class PolicySourceRepository(Protocol):
    def add(self, registration: PolicySourceRegistration) -> PolicySourceRegistration: ...

    def remove(self, canonical_path: str) -> bool: ...

    def list(self) -> list[PolicySourceRegistration]: ...


class PolicySourceInspector(Protocol):
    def canonicalize(self, source: Path, *, require_exists: bool = True) -> Path: ...

    def load_documents(self, sources: list[Path]) -> list[PolicyDocument]: ...
