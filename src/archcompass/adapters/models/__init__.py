"""Local model adapters and deterministic test providers."""

from archcompass.adapters.models.deterministic import (
    DeterministicReasoningProvider,
    probe_deterministic,
)
from archcompass.adapters.models.google import GoogleReasoningProvider, probe_google
from archcompass.adapters.models.ollama import OllamaReasoningProvider, probe_ollama
from archcompass.adapters.models.selected import SelectedModelReasoner

__all__ = [
    "DeterministicReasoningProvider",
    "GoogleReasoningProvider",
    "OllamaReasoningProvider",
    "SelectedModelReasoner",
    "probe_deterministic",
    "probe_google",
    "probe_ollama",
]
