from __future__ import annotations

from dataclasses import dataclass

from archcompass.domain._support import freeze_pairs, freeze_sequences
from archcompass.domain.repository import RepositoryRef


@dataclass(frozen=True, slots=True)
class RepositoryAtlas:
    id: str
    repository: RepositoryRef
    # Intentional migration boundary: each string is a canonical-JSON record from the
    # deterministic analyzer. Adapters own encoding/decoding until the documented
    # follow-up chooses typed atlas records or a deliberately opaque snapshot.
    nodes: tuple[str, ...] = ()
    edges: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()
    parser_configuration: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        freeze_sequences(self, "nodes", "edges", "metrics", "facts", "signals")
        freeze_pairs(self, "parser_configuration")
