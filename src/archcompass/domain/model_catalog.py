"""What this workspace could reason with, and what it has chosen to.

Named `model_catalog` rather than `models`, because `adapters/models/` already means "the
vendor transports" and a `domain/models.py` beside it would read as the same thing. Nothing
here knows how to reach a provider; these are the shapes an adapter fills in and the
interface reads back.

The distinction the whole module turns on: a *profile* is a configuration file this
workspace holds, and a *candidate* is one model a live provider says that profile can
actually run. The file supplies the credentials, the timeouts and the thinking setting —
all of them hand-authored and none of them discoverable — and the provider supplies the
only thing a file cannot know, which is what is installed or licensed right now. Neither
alone is enough to choose from, which is why a candidate is the product of the two.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from archcompass.domain.base import DomainModel, utc_now


class AvailableModel(DomainModel):
    """One model a provider says it has, as the provider names it."""

    #: Verbatim what goes into `ReasoningModelConfig.model`. Vendor-shaped — `gemma4:26b`,
    #: `gemini-3.6-flash` — because that is the string the request has to carry.
    name: str
    #: A human-facing word beside the name where the vendor offers one: a display name from
    #: Google, a parameter size from Ollama. Empty rather than repeating `name`, so a caller
    #: can tell "no better label exists" from "the label is the name".
    label: str = ""
    #: What the provider reports the model can hold and produce. Advisory, and deliberately
    #: not authoritative over the profile: see `ReasoningModelSelection` for why these are
    #: only ever applied downwards.
    input_token_limit: int | None = None
    output_token_limit: int | None = None


class ProbeResult(DomainModel):
    """One adapter's answer to "are you there, and what do you have".

    Unavailability is a value here, never an exception. The reason is the picker: "Google is
    unavailable because GOOGLE_API_KEY is unset" has to be something a dropdown can render
    beside the other choices, and an adapter that raised it instead would take the whole
    listing down with it — including the providers that are working.
    """

    available: bool
    #: Why not, in a sentence naming the cure where there is one. Empty when available.
    detail: str = ""
    models: list[AvailableModel] = Field(default_factory=list[AvailableModel])


class ModelProfile(DomainModel):
    """One `models.*.yaml` this workspace holds, summarised for a chooser."""

    #: The file's basename — `models.google.yaml`. A basename rather than a path because
    #: this is what a selection stores: a workspace that moves keeps its choice, and no
    #: absolute path from one machine ends up in another's database.
    profile_id: str
    path: str
    provider: str
    #: The model this profile's own file names, which is the sensible default within it.
    configured_model: str


class ProviderAvailability(DomainModel):
    """A profile's probe result, once the application has said which profile it was."""

    profile_id: str
    provider: str
    available: bool
    detail: str = ""
    probed_at: datetime = Field(default_factory=utc_now)


class ModelCandidate(DomainModel):
    """A profile crossed with a model its provider currently offers.

    The unit the picker lists and a selection names. Two of them can carry the same `model`
    from different profiles — the same Gemini reachable through two keys, say — which is why
    a selection is identified by the pair and never by the model name alone.
    """

    profile_id: str
    provider: str
    model: str
    label: str = ""
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    #: The model this candidate's own profile names. Worth marking rather than sorting to
    #: the top: it is the choice whose timeouts and thinking setting were written for it.
    is_configured_default: bool = False
    is_selected: bool = False


class ModelCatalog(DomainModel):
    """Everything a chooser needs, in one answer.

    The providers are carried alongside the candidates rather than being inferable from
    them, because an unavailable provider contributes no candidates and is the single most
    useful row on the screen: it is the one that says what to fix.
    """

    providers: list[ProviderAvailability] = Field(
        default_factory=list[ProviderAvailability]
    )
    candidates: list[ModelCandidate] = Field(default_factory=list[ModelCandidate])


class ReasoningModelSelection(DomainModel):
    """The choice this workspace has made, and what the last run made of it.

    Stored beside the configuration files rather than inside one. A `models.*.yaml` is
    hand-authored, comment-rich and committed; rewriting one to record a click would destroy
    the prose explaining every number in it. So the file stays the source of everything that
    was reasoned about, and this record is the source of the one thing that was chosen.
    """

    profile_id: str
    provider: str
    model: str
    selected_at: datetime = Field(default_factory=utc_now)
    #: When a run against this selection last failed, and what the provider said. A probe
    #: cannot discover this — it only asks whether the model is listed, and an exhausted
    #: quota lists perfectly well — so it is recorded on the way past the failure itself.
    #: Cleared by the next successful probe, which is the evidence that it has passed.
    failed_at: datetime | None = None
    failure_detail: str = ""
    #: What the provider said about this model when it was chosen. Kept because resolving a
    #: selection must not cost a probe, and because a profile's budgets were written for the
    #: model its file names: choosing a smaller one through the same profile leaves those
    #: numbers generous, which is the direction that truncates a request instead of refusing
    #: it. Applied downwards only. Null where the provider reports no limit.
    input_token_limit: int | None = None
    output_token_limit: int | None = None


class ReasoningModelStatus(DomainModel):
    """What the model is right now, answered without asking any provider anything.

    Separate from `ModelCatalog` because it is read on every page load and the catalog costs
    a round trip to each provider. This one costs a single row.
    """

    selection: ReasoningModelSelection | None = None
    provider: str = ""
    model: str = ""
    #: True where the effective model came from a configuration file rather than from a
    #: choice made here — a CLI run, or a workspace holding exactly one profile and no
    #: stored selection. Still changeable; it just was not chosen.
    from_configuration: bool = False
    #: True where this run was pointed at a configuration explicitly, by `--models-config`
    #: or `ARCHCOMPASS_MODELS_CONFIG`. Then the choice is not the workspace's to make: the
    #: command said which provider to run against, and a stored selection quietly overriding
    #: it would make `--models-config` mean nothing.
    pinned: bool = False
    #: The stored selection names a profile this workspace no longer holds. Distinct from
    #: having chosen nothing, because the cure is different: a file came back or went away,
    #: and saying so beats reporting the workspace as simply unconfigured.
    unresolvable: bool = False

    @property
    def identity(self) -> str:
        """`provider:model`, or empty where nothing is selected."""

        return f"{self.provider}:{self.model}" if self.provider and self.model else ""

    @property
    def selection_profile(self) -> str:
        """Which profile the stored choice names, or empty where there is no stored choice.

        Empty for a model in force by configuration rather than by choice, which is what
        keeps a chooser from marking a row as selected that nobody selected.
        """

        return self.selection.profile_id if self.selection else ""
