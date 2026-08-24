"""Choosing what this workspace reasons with.

Three questions, deliberately answered separately because they cost different things.
`status` reads one row and is asked on every page load. `catalog` asks every enabled
provider what it has and is asked when someone opens the chooser. `current` resolves the
choice into a configuration and is asked before every model call, which is once per
boundary of a review — so it is memoised.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError, PersistenceError
from archcompass.reasoning.ports import (
    ProviderDescriptor,
    ReasoningModelSelectionRepository,
)
from archcompass.reasoning.records import (
    ModelCandidate,
    ModelCatalog,
    ProviderAvailability,
    ReasoningModelSelection,
    ReasoningModelStatus,
)
from archcompass.records import ThinkingMode


def reasoning_config(
    descriptor: ProviderDescriptor,
    model: str,
    thinking: ThinkingMode,
) -> ReasoningModelConfig:
    """One provider's defaults, one model name and one thinking mode, as a request shape.

    The output budget is chosen by the mode rather than fixed per provider. Thinking tokens
    are spent from the same allowance as the answer on both providers, so a selection that
    reasons needs headroom the response JSON alone would never suggest — and giving every
    selection the larger number instead would raise the ceiling for the runs that cannot use
    it, which is the direction that truncates rather than refuses.
    """

    defaults = descriptor.defaults
    return ReasoningModelConfig(
        provider=descriptor.name,
        model=model,
        base_url=defaults.resolved_base_url(),
        api_key_env=defaults.api_key_env,
        timeout_seconds=defaults.timeout_seconds,
        context_window_tokens=defaults.context_window_tokens,
        max_output_tokens=(
            defaults.max_output_tokens
            if _spends_little_on_thinking(thinking)
            else defaults.max_output_tokens_thinking
        ),
        thinking=thinking,
        # The descriptor's number unless the environment says otherwise. Resolved here
        # because this is the one place both a pinned run and a stored selection pass
        # through, so the operator's knob reaches a local workspace and a hosted session
        # without either entry point knowing it exists.
    )


def _spends_little_on_thinking(thinking: ThinkingMode) -> bool:
    """Whether this mode can be trusted to leave the answer room in a small budget.

    Only the two modes that ask for as little thinking as the provider allows. Everything
    else gets the headroom, `None` included — a request that names no level does not get a
    model that skips thinking, it gets one that decides for itself how much to do, and
    budgeting as though it had chosen none is how a structured answer arrives truncated.
    """

    return thinking is False or thinking == "minimal"


class ModelCatalogService:
    """What this workspace could reason with, what it does, and how to change it."""

    def __init__(
        self,
        *,
        registry: Mapping[str, ProviderDescriptor],
        selections: ReasoningModelSelectionRepository,
        pin: ReasoningModelConfig | None = None,
    ) -> None:
        self._registry = registry
        self._selections = selections
        self._pin = pin
        self._resolved: dict[str, ReasoningModelConfig] = {}

    def providers(self) -> tuple[ProviderDescriptor, ...]:
        """Every provider this deployment has enabled, in the order it named them."""

        return tuple(self._registry.values())

    def status(self) -> ReasoningModelStatus:
        """Which model is in force, and how it came to be."""

        if self._pin is not None:
            return ReasoningModelStatus(
                provider=self._pin.provider,
                model=self._pin.model,
                thinking=self._pin.thinking,
                pinned=True,
            )
        stored = self._stored()
        # A selection naming a provider this deployment does not enable reports as nothing
        # chosen, rather than as a state of its own. The two have the same cure — choose
        # something reachable — and a hosted deployment that dropped Ollama would otherwise
        # greet every workspace carrying a local selection with an error about a file.
        if stored is None or stored.provider not in self._registry:
            return ReasoningModelStatus()
        return ReasoningModelStatus(
            selection=stored,
            provider=stored.provider,
            model=stored.model,
            thinking=stored.thinking,
        )

    def catalog(self) -> ModelCatalog:
        """Every enabled provider, whether it answered, and what it offered.

        A provider that is unreachable still appears, carrying why — see `ModelCatalog`.

        Each offered model becomes one candidate per thinking mode it genuinely has, because
        that is what is being chosen: `gemini-3.6-flash` thinking and `gemini-3.6-flash` not
        thinking cost differently and answer differently.

        A successful probe clears any failure recorded against the current selection: the
        provider has just answered, so a note about a call that failed earlier is now a
        claim nothing supports.
        """

        status = self.status()
        chosen = status.selection
        providers: list[ProviderAvailability] = []
        candidates: list[ModelCandidate] = []
        healthy = False
        for descriptor in self._registry.values():
            result = descriptor.probe(descriptor.defaults)
            providers.append(
                ProviderAvailability(
                    provider=descriptor.name,
                    available=result.available,
                    detail=result.detail,
                    label=descriptor.label,
                )
            )
            if result.available and chosen is not None and chosen.provider == descriptor.name:
                healthy = True
            candidates.extend(
                ModelCandidate(
                    provider=descriptor.name,
                    model=offered.name,
                    thinking=mode,
                    label=offered.label,
                    input_token_limit=offered.input_token_limit,
                    output_token_limit=offered.output_token_limit,
                    is_selected=(
                        chosen is not None
                        and (chosen.provider, chosen.model, chosen.thinking)
                        == (descriptor.name, offered.name, mode)
                    ),
                )
                for offered in result.models
                for mode in offered.thinking_modes
            )
        if healthy:
            self._forget_failure()
        return ModelCatalog(providers=providers, candidates=candidates)

    def select(
        self, provider: str, model: str, thinking: ThinkingMode = None
    ) -> ReasoningModelStatus:
        """Record which model this workspace reasons with, and whether it reasons.

        The model is not checked against the last probe. A listing is a snapshot, and a
        candidate can go stale between the chooser opening and a row being clicked; refusing
        a choice on that basis trades a working selection for a confusing refusal, when the
        failure it prevents would arrive named and retryable from the run itself.
        """

        if self._pin is not None:
            raise ConfigurationError(
                "This run was told which model to use with --provider and --model, so the "
                "model is not this workspace's to choose. Restart without them to choose "
                "here."
            )
        descriptor = self._registry.get(provider)
        if descriptor is None:
            offered = ", ".join(self._registry) or "none"
            raise ConfigurationError(
                f"{provider} is not a provider this workspace can reach. It has: {offered}."
            )
        if not model.strip():
            raise ConfigurationError("A selection has to name a model.")
        limits = self._limits(descriptor, model)
        self._selections.set(
            ReasoningModelSelection(
                provider=descriptor.name,
                model=model,
                thinking=thinking,
                input_token_limit=limits[0],
                output_token_limit=limits[1],
            )
        )
        self._resolved.clear()
        return self.status()

    def clear(self) -> None:
        self._selections.clear()
        self._resolved.clear()

    def current(self) -> ReasoningModelConfig | None:
        """The configuration to reason with, or `None` where nothing is chosen.

        Asked before every model call, so the resolved result is kept: a review judges each
        boundary in its own call, and rebuilding the same shape for each of them would be
        work done forty times to reach the same answer.

        Those calls may now arrive from several threads at once, and the memo is left
        unlocked deliberately. Two threads that both miss it both resolve the same stored
        selection through the same descriptor and store the same immutable configuration
        under the same key, so the race costs one wasted resolution and can produce no wrong
        answer; a lock here would serialise every judgement behind a dictionary lookup to
        prevent that. `select` and `clear` empty it, which is a rebind of what is already
        there rather than a mutation of what a caller is holding.
        """

        if self._pin is not None:
            return self._pin
        stored = self.status().selection
        if stored is None:
            return None
        descriptor = self._registry[stored.provider]
        # Keyed by the thinking mode as well: the same model with and without reasoning are
        # two configurations, with different output budgets and different answers.
        key = f"{stored.provider}\0{stored.model}\0{stored.thinking}"
        cached = self._resolved.get(key)
        if cached is not None:
            return cached
        base = reasoning_config(descriptor, stored.model, stored.thinking)
        resolved = base.model_copy(
            update={
                # Downwards only. The descriptor's numbers are already deliberately below
                # what a vendor advertises — they feed a budget check where under-stating
                # refuses a borderline request and over-stating lets one through to be
                # truncated — so a provider's larger figure is never an improvement on them.
                "context_window_tokens": _clamped(
                    base.context_window_tokens, stored.input_token_limit
                ),
                "max_output_tokens": _clamped(
                    base.max_output_tokens, stored.output_token_limit
                ),
            }
        )
        self._resolved[key] = resolved
        return resolved

    def record_failure(self, detail: str) -> None:
        # A failure note is the least important thing in a failing run. Losing it must not
        # replace the provider's own message with a database one.
        with suppress(PersistenceError):
            self._selections.record_failure(detail)

    def _stored(self) -> ReasoningModelSelection | None:
        try:
            return self._selections.get()
        except PersistenceError:
            # A runtime built without initializing its database has no such table. Reporting
            # "nothing chosen" is both true and the state the interface can act on.
            return None

    def _forget_failure(self) -> None:
        with suppress(PersistenceError):
            self._selections.clear_failure()

    def _limits(
        self, descriptor: ProviderDescriptor, model: str
    ) -> tuple[int | None, int | None]:
        """What the provider says about this model, asked once at the moment of choosing.

        The only probe outside `catalog`, and it earns itself: these numbers are what keep a
        smaller model from inheriting a larger one's budgets, and asking here means never
        having to ask again while a review runs.
        """

        try:
            result = descriptor.probe(descriptor.defaults)
        except ConfigurationError:
            return None, None
        offered = next((item for item in result.models if item.name == model), None)
        return (
            (offered.input_token_limit, offered.output_token_limit)
            if offered
            else (None, None)
        )


def _clamped(authored: int, reported: int | None) -> int:
    return authored if reported is None else min(authored, reported)
