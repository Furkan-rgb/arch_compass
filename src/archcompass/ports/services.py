"""Compatibility exports for the cohesive service-port modules.

New code should import from ``ports.atlas``, ``ports.models``,
``ports.policies``, or ``ports.reasoning`` directly.
"""

from archcompass.ports.atlas import (
    AtlasQueryService,
    RepositoryAnalyzer,
    SourceReader,
)
from archcompass.ports.models import EmbeddingProvider
from archcompass.ports.policies import PolicyIndex, PolicyRetriever
from archcompass.ports.reasoning import FocusedReasoningProvider

ReasoningProvider = FocusedReasoningProvider

__all__ = [
    "AtlasQueryService",
    "EmbeddingProvider",
    "PolicyIndex",
    "PolicyRetriever",
    "ReasoningProvider",
    "RepositoryAnalyzer",
    "SourceReader",
]
