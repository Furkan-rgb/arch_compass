"""The boundaries around choosing a reasoning model: probing, storing, resolving.

None of these are `runtime_checkable`, and none of them carry the `_conforms` line the
streaming protocols do. That idiom exists for protocols reached by `isinstance`, which
compares method names alone. Everything here is passed by name into a typed parameter, so
the signature is already checked at each call site.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.model_catalog import ProbeResult, ReasoningModelSelection
from archcompass.ports.reasoning import FocusedReasoningProvider

#: Whether a provider is reachable and what it currently offers.
#:
#: A plain function rather than a method on the reasoner, and that is the whole design.
#: Constructing a provider is exactly what fails when a provider is unavailable — the Google
#: transport resolves its API key in `__init__` — so a probe reached through a constructed
#: reasoner could never report the most common reason for unavailability. It also lets the
#: probe set its own timeout: a transport bakes in `timeout_seconds`, which is 360 in both
#: shipped configurations and is right for a judgement, not for a dropdown.
type ReasoningModelProbe = Callable[[ReasoningModelConfig], ProbeResult]

#: Building the reasoner for one resolved configuration.
type ReasoningProviderFactory = Callable[[ReasoningModelConfig], FocusedReasoningProvider]


class ReasoningModelSelectionRepository(Protocol):
    """The one row a workspace keeps about which model it reasons with."""

    def get(self) -> ReasoningModelSelection | None: ...

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection: ...

    def clear(self) -> None: ...

    def record_failure(self, detail: str) -> None: ...

    def clear_failure(self) -> None: ...


class SelectedReasoningModel(Protocol):
    """What the delegating reasoner needs from the selection, and deliberately nothing else.

    Narrower than the service that satisfies it. The reasoner lives among the model adapters
    and has one job — reason with whatever is currently chosen — so it is handed the two
    methods that job needs rather than a catalog it could probe providers through.
    """

    def current(self) -> ReasoningModelConfig | None:
        """The configuration to reason with, or `None` where nothing is chosen."""
        ...

    def record_failure(self, detail: str) -> None:
        """Note that a call against the current selection failed, and why."""
        ...
