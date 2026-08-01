"""Choosing what this workspace reasons with.

Three questions, deliberately answered separately because they cost different things.
`status` reads one row and is asked on every page load. `catalog` asks every configured
provider what it has and is asked when someone opens the chooser. `current` resolves the
choice into a configuration and is asked before every model call, which is once per
boundary of a review — so it parses no YAML it has parsed before.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from archcompass.configuration import (
    AppConfig,
    ReasoningModelConfig,
    discover_model_profiles,
    load_config,
)
from archcompass.domain.errors import ConfigurationError, PersistenceError
from archcompass.domain.model_catalog import (
    ModelCandidate,
    ModelCatalog,
    ModelProfile,
    ProviderAvailability,
    ReasoningModelSelection,
    ReasoningModelStatus,
)
from archcompass.ports.model_catalog import (
    ReasoningModelProbe,
    ReasoningModelSelectionRepository,
)


class ModelCatalogService:
    """What this workspace could reason with, what it does, and how to change it."""

    def __init__(
        self,
        *,
        workspace: Path,
        explicit_config: Path | None,
        pinned: bool,
        selections: ReasoningModelSelectionRepository,
        probe: ReasoningModelProbe,
        configured: AppConfig | None,
    ) -> None:
        self._workspace = workspace
        self._explicit_config = explicit_config
        self._pinned = pinned
        self._selections = selections
        self._probe = probe
        self._configured = configured
        self._resolved: dict[str, ReasoningModelConfig] = {}

    def profiles(self) -> list[ModelProfile]:
        return discover_model_profiles(self._workspace, self._explicit_config)

    def status(self) -> ReasoningModelStatus:
        """Which model is in force, and how it came to be."""

        if self._pinned:
            reasoning = self._configured.models.reasoning if self._configured else None
            return ReasoningModelStatus(
                provider=reasoning.provider if reasoning else "",
                model=reasoning.model if reasoning else "",
                pinned=True,
                from_configuration=True,
            )
        stored = self._stored()
        if stored is not None:
            known = {profile.profile_id for profile in self.profiles()}
            if stored.profile_id not in known:
                return ReasoningModelStatus(selection=stored, unresolvable=True)
            return ReasoningModelStatus(
                selection=stored,
                provider=stored.provider,
                model=stored.model,
            )
        reasoning = self._configured.models.reasoning if self._configured else None
        if reasoning is None:
            return ReasoningModelStatus()
        return ReasoningModelStatus(
            provider=reasoning.provider,
            model=reasoning.model,
            from_configuration=True,
        )

    def catalog(self) -> ModelCatalog:
        """Every profile, whether its provider answered, and what it offered.

        A profile that is unreachable still appears, carrying why — see `ModelCatalog`.

        A successful probe clears any failure recorded against the current selection: the
        provider has just answered, so a note about a call that failed earlier is now a
        claim nothing supports.
        """

        status = self.status()
        providers: list[ProviderAvailability] = []
        candidates: list[ModelCandidate] = []
        healthy = False
        for profile in self.profiles():
            result = self._probe(self._profile_reasoning(profile))
            providers.append(
                ProviderAvailability(
                    profile_id=profile.profile_id,
                    provider=profile.provider,
                    available=result.available,
                    detail=result.detail,
                )
            )
            if result.available and profile.profile_id == status.selection_profile:
                healthy = True
            candidates.extend(
                ModelCandidate(
                    profile_id=profile.profile_id,
                    provider=profile.provider,
                    model=offered.name,
                    label=offered.label,
                    input_token_limit=offered.input_token_limit,
                    output_token_limit=offered.output_token_limit,
                    is_configured_default=offered.name == profile.configured_model,
                    is_selected=(
                        profile.profile_id == status.selection_profile
                        and offered.name == status.model
                    ),
                )
                for offered in result.models
            )
        if healthy:
            self._forget_failure()
        return ModelCatalog(providers=providers, candidates=candidates)

    def select(self, profile_id: str, model: str) -> ReasoningModelStatus:
        """Record which model this workspace reasons with.

        The model is not checked against the last probe. A listing is a snapshot, and a
        candidate can go stale between the chooser opening and a row being clicked; refusing
        a choice on that basis trades a working selection for a confusing refusal, when the
        failure it prevents would arrive named and retryable from the run itself.
        """

        if self._pinned:
            raise ConfigurationError(
                "This run was pointed at a model configuration with --models-config or "
                "ARCHCOMPASS_MODELS_CONFIG, so the model is not this workspace's to choose. "
                "Restart without it to choose here."
            )
        profile = next(
            (item for item in self.profiles() if item.profile_id == profile_id), None
        )
        if profile is None:
            raise ConfigurationError(
                f"This workspace holds no model configuration called {profile_id}."
            )
        if not model.strip():
            raise ConfigurationError("A selection has to name a model.")
        limits = self._limits(profile, model)
        self._selections.set(
            ReasoningModelSelection(
                profile_id=profile.profile_id,
                provider=profile.provider,
                model=model,
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

        Asked before every model call, so the parsed result is kept: a review judges each
        boundary in its own call, and re-reading the same YAML for each of them would be
        work done forty times to reach the same answer.
        """

        status = self.status()
        if status.pinned or (status.from_configuration and self._configured is not None):
            return self._configured.models.reasoning if self._configured else None
        stored = status.selection
        if stored is None or status.unresolvable:
            return None
        # Keyed by profile as well as model: the same provider and model reached through two
        # profiles are two different configurations, with different credentials and budgets.
        key = f"{stored.profile_id}\0{stored.model}"
        cached = self._resolved.get(key)
        if cached is not None:
            return cached
        profile = next(
            (item for item in self.profiles() if item.profile_id == stored.profile_id),
            None,
        )
        if profile is None:
            return None
        try:
            base = load_config(Path(profile.path)).models.reasoning
        except ConfigurationError:
            return None
        resolved = base.model_copy(
            update={
                "model": stored.model,
                # Downwards only. The authored numbers are already deliberately below what a
                # vendor advertises — they feed a budget check where under-stating refuses a
                # borderline request and over-stating lets one through to be truncated — so
                # a provider's larger figure is never an improvement on them.
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

    def _profile_reasoning(self, profile: ModelProfile) -> ReasoningModelConfig:
        return load_config(Path(profile.path)).models.reasoning

    def _limits(self, profile: ModelProfile, model: str) -> tuple[int | None, int | None]:
        """What the provider says about this model, asked once at the moment of choosing.

        The only probe outside `catalog`, and it earns itself: these numbers are what keep a
        smaller model from inheriting a larger one's budgets, and asking here means never
        having to ask again while a review runs.
        """

        try:
            result = self._probe(self._profile_reasoning(profile))
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
