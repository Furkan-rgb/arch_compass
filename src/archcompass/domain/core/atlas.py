from __future__ import annotations

from dataclasses import dataclass

from archcompass.domain.core._support import freeze_pairs, freeze_sequences
from archcompass.domain.core.repository import RepositoryRef


@dataclass(frozen=True, slots=True)
class RepositoryAtlas:
    id: str
    repository: RepositoryRef
    # Canonical JSON records keep the deterministic analyzer's complete representation
    # without importing a parser DTO into the domain. Adapters own decoding.
    nodes: tuple[str, ...] = ()
    edges: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()
    parser_configuration: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        freeze_sequences(self, "nodes", "edges", "metrics", "facts", "signals")
        freeze_pairs(self, "parser_configuration")
