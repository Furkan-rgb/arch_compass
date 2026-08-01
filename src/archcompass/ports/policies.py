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

from archcompass.domain.policy import (
    PolicyDocument,
    PolicyDraft,
    PolicySourceRegistration,
)


class PolicySourceRepository(Protocol):
    def add(self, registration: PolicySourceRegistration) -> PolicySourceRegistration: ...

    def remove(self, canonical_path: str) -> bool: ...

    def list(self) -> list[PolicySourceRegistration]: ...


class PolicySourceInspector(Protocol):
    def canonicalize(self, source: Path, *, require_exists: bool = True) -> Path: ...

    def load_documents(self, sources: list[Path]) -> list[PolicyDocument]: ...


class PolicyStore(Protocol):
    """Writing the one directory of policies a workspace owns.

    Staged before it is published, because the only check that matters cannot be made on
    text: a policy is valid if the parser reads it back, and the parser reads files. A draft
    is written where nothing looks for it, parsed there, and given the name the catalog reads
    it under only once it has survived that — so a rejected edit never displaces the policy
    it was an edit of, and a file that cannot be parsed is never left where a review would
    trip over it.
    """

    def stage(self, directory: Path, policy_id: str, draft: PolicyDraft) -> Path: ...

    def publish(self, staged: Path) -> Path: ...

    def discard(self, staged: Path) -> None: ...

    def remove(self, directory: Path, policy_id: str) -> None: ...
