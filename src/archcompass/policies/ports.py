"""What policy retrieval asks the outside world for.

Two boundaries that meet nowhere else. **Sources** own where authored policy documents come
from and what is done to a file before the catalog will read it under a policy's name.
**The dense index** is what one retrieval strategy is built on — embeddings and a vector
store — and is reached only by `adapters/sqlite_index.py`.

They are in one file because they are the whole of what this feature cannot do for itself,
and a reader of `policies/` should be able to see that list without leaving the directory.
The source catalog stays authoritative whichever retrieval strategy is configured: selection
and indexing sit behind `PolicyRetriever`, which is a graph seam and lives in `ports/`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from archcompass.domain import Policy
from archcompass.policies.records import (
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


@dataclass(frozen=True, slots=True)
class DensePolicyMatch:
    policy_id: str
    score: float


@runtime_checkable
class DensePolicyIndex(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def embedding_identity(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def synchronize(self, corpus: tuple[Policy, ...]) -> None: ...

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]: ...
