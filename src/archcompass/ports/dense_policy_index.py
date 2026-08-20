"""Infrastructure port used only by the dense retriever implementation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from archcompass.domain import Policy


@dataclass(frozen=True, slots=True)
class DensePolicyMatch:
    policy_id: str
    score: float


@runtime_checkable
class BatchDocumentEmbeddings(Protocol):
    """Embeddings that can put a whole corpus to the provider in one submission.

    Indexing and searching are different jobs with different deadlines. Building the index
    is bulk work nobody is waiting on, so it can go to a batch endpoint that is metered
    separately and costs half; a search embeds one text to answer a retrieval happening
    now, and stays interactive whatever the quota says. Only the first is offered here.
    """

    def supports_batch(self) -> bool: ...

    def embed_documents_batched(self, texts: Sequence[str]) -> list[list[float]]: ...


class DensePolicyIndex(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def embedding_identity(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def synchronize(self, corpus: tuple[Policy, ...]) -> None: ...

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]: ...
