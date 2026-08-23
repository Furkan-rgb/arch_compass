"""Stable application ports.

The protocols the application calls and the adapters implement — one per thing the outside
world is asked for: analysing a repository, storing a record, reading source, reasoning.
Read `capabilities.py` first; it is the widest of them and the one the review graph is
sequenced entirely out of.
"""

from archcompass.ports.atlas import (
    AtlasQueryService,
    AtlasSource,
    SourceReader,
)
from archcompass.ports.persistence import (
    AtlasRepository,
)
from archcompass.ports.policies import PolicySourceInspector, PolicySourceRepository

__all__ = [
    "AtlasQueryService",
    "AtlasRepository",
    "AtlasSource",
    "PolicySourceInspector",
    "PolicySourceRepository",
    "SourceReader",
]
