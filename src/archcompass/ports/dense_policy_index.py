"""Infrastructure port used only by the dense retriever implementation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from archcompass.domain.core import Policy


@dataclass(frozen=True, slots=True)
class DensePolicyMatch:
    policy_id: str
    score: float


class DensePolicyIndex(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def embedding_identity(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def synchronize(self, corpus: tuple[Policy, ...]) -> None: ...

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]: ...
