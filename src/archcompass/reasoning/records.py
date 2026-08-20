"""Validated model catalog and selection records.

Nothing here knows how to reach a provider — that is `adapters/`, and the split is what
lets a catalogue be constructed in a test without a network. These are the shapes an
adapter fills in and the interface reads back.

The distinction the whole module turns on: a *provider* is something this build knows how
to reach, and a *candidate* is one way of reasoning that a live provider says it can
actually offer — a model, and one of the thinking modes that model genuinely has. The
provider's descriptor supplies the endpoint, the credential variable and the budgets, none
of them discoverable, and the provider itself supplies the only thing code cannot know,
which is what is installed or licensed right now. Neither alone is enough to choose from,
which is why a candidate is the product of the two.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from archcompass.records import BoundaryDTO, utc_now


class AvailableModel(BoundaryDTO):
    """One model a provider says it has, as the provider names it."""

    #: Verbatim what goes into `ReasoningModelConfig.model`. Vendor-shaped — `gemma4:26b`,
    #: `gemini-3.6-flash` — because that is the string the request has to carry.
    name: str
    #: A human-facing word beside the name where the vendor offers one: a display name from
    #: Google, a parameter size from Ollama. Empty rather than repeating `name`, so a caller
    #: can tell "no better label exists" from "the label is the name".
    label: str = ""
    #: What the provider reports the model can hold and produce. Advisory, and deliberately
    #: not authoritative over the provider's own budgets: see `ReasoningModelSelection` for
    #: why these are only ever applied downwards.
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    #: The thinking modes this model genuinely offers, as the provider reported them —
    #: `True` requires reasoning, `False` forbids it, `None` leaves the model to its own
    #: default. A model that can think is offered both ways; one that cannot is offered as
    #: the single `None` row, because forbidding reasoning is still a request and there is
    #: nothing there to ask. Which models are offered at all is the adapter's own decision;
    #: this is not, and was wrong in both directions while it was declared by hand.
    thinking_modes: tuple[bool | None, ...] = (None,)


class ProbeResult(BoundaryDTO):
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


class ProviderAvailability(BoundaryDTO):
    """One provider's probe result, once the application has said which provider it was."""

    provider: str
    available: bool
    detail: str = ""
    #: The provider's name written for a reader — `Google`, `Groq`. Empty where the key
    #: already reads as one, so a caller can tell "no better name exists" from "the name is
    #: the key". Carried here because the chooser groups by provider and a group needs a
    #: heading; deriving one by capitalising the key gives `Openai` and `Cerebras` equal
    #: confidence, and only one of them is right.
    label: str = ""
    probed_at: datetime = Field(default_factory=utc_now)


class ModelCandidate(BoundaryDTO):
    """One model a provider currently offers, in one of the thinking modes it has.

    The unit the picker lists and a selection names. A model appearing twice — once
    thinking, once not — is two candidates rather than one with a switch beside it, because
    they cost differently, answer differently, and are chosen the same way everything else
    here is chosen: by picking the row that says what it does.
    """

    provider: str
    model: str
    #: `True` requires reasoning, `False` forbids it, `None` leaves the model to its own
    #: default. Part of the identity: a candidate is (provider, model, thinking).
    thinking: bool | None = None
    label: str = ""
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    is_selected: bool = False


class ModelCatalog(BoundaryDTO):
    """Everything a chooser needs, in one answer.

    The providers are carried alongside the candidates rather than being inferable from
    them, because an unavailable provider contributes no candidates and is the single most
    useful row on the screen: it is the one that says what to fix.
    """

    providers: list[ProviderAvailability] = Field(
        default_factory=list[ProviderAvailability]
    )
    candidates: list[ModelCandidate] = Field(default_factory=list[ModelCandidate])


class ReasoningModelSelection(BoundaryDTO):
    """The choice this workspace has made, and what the last run made of it.

    Three fields make the choice, because three things vary between two runs that are
    otherwise identical: which provider is reached, which model it is asked, and whether
    that model reasons first. Everything else about reaching the provider is a property of
    the provider, lives in its descriptor, and is not a workspace's to choose.
    """

    provider: str
    model: str
    #: `True` requires reasoning, `False` forbids it, `None` leaves the model to its own
    #: default. Stored rather than derived: it is part of what was picked, and the same
    #: model offers it both ways where the model supports both.
    thinking: bool | None = None
    selected_at: datetime = Field(default_factory=utc_now)
    #: When a run against this selection last failed, and what the provider said. A probe
    #: cannot discover this — it only asks whether the model is listed, and an exhausted
    #: quota lists perfectly well — so it is recorded on the way past the failure itself.
    #: Cleared by the next successful probe, which is the evidence that it has passed.
    failed_at: datetime | None = None
    failure_detail: str = ""
    #: What the provider said about this model when it was chosen. Kept because resolving a
    #: selection must not cost a probe, and because a provider's budgets are written for the
    #: models it usually reaches: choosing a smaller one leaves those numbers generous,
    #: which is the direction that truncates a request instead of refusing it. Applied
    #: downwards only. Null where the provider reports no limit.
    input_token_limit: int | None = None
    output_token_limit: int | None = None


class ReasoningModelStatus(BoundaryDTO):
    """What the model is right now, answered without asking any provider anything.

    Separate from `ModelCatalog` because it is read on every page load and the catalog costs
    a round trip to each provider. This one costs a single row.
    """

    selection: ReasoningModelSelection | None = None
    provider: str = ""
    model: str = ""
    thinking: bool | None = None
    #: True where this process was told which model to use, by `--provider` and `--model`.
    #: Then the choice is not the workspace's to make: the command said which provider this
    #: run costs against, and a stored selection quietly overriding it would make the flags
    #: mean nothing — `make demo` would run whichever model was last clicked.
    pinned: bool = False

    @property
    def identity(self) -> str:
        """`provider:model`, or empty where nothing is selected."""

        return f"{self.provider}:{self.model}" if self.provider and self.model else ""


class EmbeddingModelSelection(BoundaryDTO):
    """The embedding model chosen for this workspace's policy index."""

    provider: str
    model: str
    dimensions: int = Field(ge=1)
    selected_at: datetime = Field(default_factory=utc_now)

    @property
    def identity(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}"


class EmbeddingModelCandidate(BoundaryDTO):
    provider: str
    model: str
    dimensions: int = Field(ge=1)
    label: str = ""
    is_selected: bool = False


class EmbeddingModelCatalog(BoundaryDTO):
    providers: list[ProviderAvailability] = Field(
        default_factory=list[ProviderAvailability]
    )
    candidates: list[EmbeddingModelCandidate] = Field(
        default_factory=list[EmbeddingModelCandidate]
    )


class EmbeddingModelStatus(BoundaryDTO):
    selection: EmbeddingModelSelection | None = None
    pinned: bool = False
