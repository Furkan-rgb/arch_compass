"""Local model adapters and deterministic test providers.

One provider per vendor — `google.py`, `ollama.py` — and a deterministic double, all of
them thin: what a stage tells a model and what shape the reply must take is decided once,
in `structured/`, which is where to read first. `prompt_contracts.py` holds the words
themselves, and `selected.py` is the indirection that lets a workspace change its mind
about which provider answers.

Each transport module also exports a `DESCRIPTOR` naming itself, its probe and its
defaults. Those are reached through the modules rather than re-exported here: the
composition root is the one caller, and a second list of provider names in this file is a
second list to keep in step with the first.
"""

from archcompass.adapters.models.deterministic import DeterministicReasoningProvider
from archcompass.adapters.models.google import GoogleReasoningProvider
from archcompass.adapters.models.ollama import OllamaReasoningProvider
from archcompass.adapters.models.selected import SelectedModelReasoner

__all__ = [
    "DeterministicReasoningProvider",
    "GoogleReasoningProvider",
    "OllamaReasoningProvider",
    "SelectedModelReasoner",
]
