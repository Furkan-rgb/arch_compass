"""Stable application ports.

The protocols the application calls and the adapters implement — one per thing the outside
world is asked for: analysing a repository, storing a record, reading source, reasoning.
Read `reasoning.py` first; it is the widest of them and the one the whole advisory flow
turns on.
"""

from archcompass.ports.atlas import (
    AtlasQueryService,
    RepositoryAnalyzer,
    SourceReader,
)
from archcompass.ports.policies import PolicySourceInspector, PolicySourceRepository
from archcompass.ports.repositories import (
    AtlasRepository,
)

__all__ = [
    "AtlasQueryService",
    "AtlasRepository",
    "PolicySourceInspector",
    "PolicySourceRepository",
    "RepositoryAnalyzer",
    "SourceReader",
]
