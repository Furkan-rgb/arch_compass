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

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final, Literal

from pydantic import Field

from archcompass.configuration import ReasoningModelConfig
from archcompass.records import BoundaryDTO, ThinkingMode, utc_now

# What a judgement was produced by, and what it was produced from. Both are compared
# against themselves — `CachingArchitectureJudge` keys a cached finding on them, and
# `DeterministicRevisionCalculator` asks whether the stamp on a stored finding still matches
# what this process would produce. So they must be one value each, computed in one place.
#
# There is one prompt identity per judge rather than one for the product, because there are
# genuinely three prompts: the deep judge opens with `JUDGEMENT_TOOL_CONTRACT` and a set of
# tool descriptions the plain judge never sends, and the deterministic stand-in sends nothing
# at all. A single shared constant would make three different questions report as the same
# question, and a prompt that moved under one of them would move nothing here.
#
# "One place" is therefore not a constant but the code that chooses between them:
# `SelectedLangChainJudge.selection` names the judge class it would build for the model in
# force right now, and the identity is read off that class rather than carried beside it, so
# the choosing and the stamping are one act. `bootstrap` hands *that method* to the cache and
# to the revision calculator rather than deriving the answer a second time.
#
# The indirection is the fix for the failure this comment used to only predict. These were
# three literals and two f-strings across four modules; nothing made the two sides agree, and
# when the deep judge arrived they stopped agreeing — every finding inside every stored review
# was stamped `judge:deep-v2` while `bootstrap` reported `judge:v3`. Inside a stored review,
# which is what the delta reads: the finding cache also holds older rows stamped `judge:v2`,
# and those are honest, because the plain judge produced them under that name before the deep
# judge existed. `analysis/delta.py` records what the disagreement costs: every candidate of
# every review reports `ChangeCause.PROMPT` for ever, and the comment there says the corpus
# fingerprint had already done exactly that once. Measured on the workspace that found it:
# 148 stored findings, not one of them reused, and three
# consecutive revisions of a commit nobody had touched each reporting `changed=7, unchanged=0`
# and re-rolling every candidate through the tool loop.
#
# Which of the two values to keep was decided by what is already written down. Reviews are
# immutable — see `docs/charter.md` — so whatever this reports has to be read against stamps
# nobody may rewrite, and every stamp on a finding in a stored review says `judge:deep-v2`.
# Teaching the deep judge to stamp `judge:v3` instead would have agreed with itself and
# disagreed with all 148 of them, buying one more full re-judgement of every candidate for
# nothing. Reporting the identity of the judge actually selected costs none: the stored stamps
# read as unmoved on the next review, and the verdicts carry forward.

#: Each identity is followed immediately by the digest of everything that judge sends a
#: model, as `reasoning/adapters/prompt_inventory.py` assembles it. They are written as one
#: pair, on adjacent lines, because they are one decision: `scripts/judge_prompt_check.py`
#: fails `make check` when the digest stops answering for the prompt, and its message tells
#: whoever reads it to bump the two together. The failure had to name a place to edit, and a
#: reader sent to two places thirty lines apart is a reader who edits one of them.
#:
#: `make check` recomputes these offline. It re-judges nothing and reaches no provider — the
#: cost of a moved prompt is a build failure and one edit here, not a re-run of every stored
#: finding, which is the price the rejected content-hash-as-identity design would have made
#: the user pay.
#:
#: The exclusions the digests are computed under are argued in `prompt_inventory`'s own
#: docstring. They narrow the check; they do not narrow what these identities claim.

#: The judge that makes one structured call and is offered nothing to look at.
JUDGE_PROMPT_IDENTITY: Final = "judge:v3"
_JUDGE_PROMPT_DIGEST: Final = "182d0bcb8297b560deb223a1a7c6a933a25080d4a9b9dc62d95dcbdd29b1ae57"

#: The judge that may read the reviewed repository while it decides. Bumped whenever the model
#: is shown something different, because a stored finding carries this and
#: `DeterministicRevisionCalculator` asks whether the stamp still matches what this process
#: would produce.
#:
#: `v2` adds `review_tools.FILESYSTEM_ROOT_NOTE`, which is not part of the judgement contract
#: but is part of what the model reads — and it changed behaviour, which is the whole test of
#: whether an identity should move. Everything judged under `v1` re-judges once.
#:
#: It lives here beside the other two, rather than beside the prompt it names, so that the set
#: a judgement can be stamped with is enumerable in one screen. That is what the dispatcher
#: above chooses from, and what a reader checking the invariant has to be able to see whole.
DEEP_JUDGE_PROMPT_IDENTITY: Final = "judge:deep-v2"
_DEEP_JUDGE_PROMPT_DIGEST: Final = (
    "25c7b503a2ee829d2d92495be838e37ce441953f4f92fe57fee387e59a870ee7"
)

#: The stand-in that reaches no provider at all, and so sends no prompt. Its digest is the
#: digest of the empty string, and that is the correct value rather than a placeholder: what
#: this judge sends a model is nothing.
DETERMINISTIC_JUDGE_PROMPT_IDENTITY: Final = "judge:deterministic-v1"
_DETERMINISTIC_JUDGE_PROMPT_DIGEST: Final = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

#: The three pairs above as one mapping, which is the shape the check reads. Assembled from
#: the names rather than restating either half, so there is nowhere for a fourth spelling of
#: an identity to appear.
JUDGE_PROMPT_DIGESTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        JUDGE_PROMPT_IDENTITY: _JUDGE_PROMPT_DIGEST,
        DEEP_JUDGE_PROMPT_IDENTITY: _DEEP_JUDGE_PROMPT_DIGEST,
        DETERMINISTIC_JUDGE_PROMPT_IDENTITY: _DETERMINISTIC_JUDGE_PROMPT_DIGEST,
    }
)


def model_identity(config: ReasoningModelConfig) -> str:
    """Which model produced a judgement, including how hard it was asked to think.

    Thinking is part of the identity because it changes the answer: a finding judged with it
    on is not the finding the same model gives with it off, and a cache that ignored the
    difference would hand back the wrong one.
    """

    return f"{config.provider}:{config.model}:thinking={config.thinking}"

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
    #: The thinking modes this model genuinely offers, as the provider reported them.
    #: `None` leaves the model to its own default; a bool is a switch; a level is a dial.
    #: Which of the two a provider gets is the provider's business — Ollama has a switch and
    #: Gemini 3 has `minimal`/`low`/`medium`/`high` and no switch — and a model that cannot
    #: think at all is offered as the single `None` row, because forbidding reasoning is
    #: still a request and there is nothing there to ask. Which models are offered at all is
    #: the adapter's own decision; this is not, and was wrong in both directions while it was
    #: declared by hand.
    thinking_modes: tuple[ThinkingMode, ...] = (None,)


class ProbeResult(BoundaryDTO):
    """One adapter's answer to "are you there, and what do you have".

    Unavailability is a value here, never an exception. The reason is the picker: "Google is
    unavailable because OPENROUTER_API_KEY is unset" has to be something a dropdown can render
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
    #: The provider's name written for a reader — `Google`, `OpenRouter`. Empty where the key
    #: already reads as one, so a caller can tell "no better name exists" from "the name is
    #: the key". Carried here because the chooser groups by provider and a group needs a
    #: heading; deriving one by capitalising the key gives `Openai` and `Openrouter` equal
    #: confidence, and only one of them is right.
    label: str = ""
    probed_at: datetime = Field(default_factory=utc_now)


#: What is known about a model's fitness to judge, from having run it against the gate.
#:
#: `qualified` has held its invariants over repeated runs on a real repository.
#: `experimental` reached sound verdicts but has not been shown to do so reliably, or leaves
#: a repository-answerable premise unresolved often enough to matter.
#: `not_qualified` failed the gate: unsupported claims, one verdict for everything, or output
#: the contract could not use.
#: `unknown` is every model nobody has measured, which is most of them.
Qualification = Literal["qualified", "experimental", "not_qualified", "unknown"]


class ModelCandidate(BoundaryDTO):
    """One model a provider currently offers, in one of the thinking modes it has.

    The unit the picker lists and a selection names. A model appearing twice — once
    thinking, once not — is two candidates rather than one with a switch beside it, because
    they cost differently, answer differently, and are chosen the same way everything else
    here is chosen: by picking the row that says what it does.
    """

    provider: str
    model: str
    #: The depth this row asks for — a level, a switch, or `None` for the model's own
    #: default. Part of the identity: a candidate is (provider, model, thinking).
    thinking: ThinkingMode = None
    label: str = ""
    input_token_limit: int | None = None
    output_token_limit: int | None = None
    is_selected: bool = False
    #: How this model has fared on the judgement gate, where anybody has run it.
    #:
    #: A label on the row rather than a branch in the judge. Every model reaches the same
    #: `ArchitectureJudge` with the same tools, prompt and schema — what differs is how well
    #: it uses them, and that is something a person choosing a model should be able to read
    #: rather than something the code should route around.
    qualification: Qualification = "unknown"


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
    #: The depth this workspace picked — a level where the provider has levels, a switch
    #: where it has a switch, `None` for the model's own default. Stored rather than derived:
    #: it is part of what was picked, and one model is offered once per depth it has.
    thinking: ThinkingMode = None
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
    thinking: ThinkingMode = None
    #: True where this process was told which model to use, by `--provider` and `--model`.
    #: Then the choice is not the workspace's to make: the command said which provider this
    #: run costs against, and a stored selection quietly overriding it would make the flags
    #: mean nothing, and `--provider ollama --model qwen3.8:27b web` would judge on
    #: whichever model was last clicked.
    pinned: bool = False


class EmbeddingModelSelection(BoundaryDTO):
    """The embedding model chosen for this workspace's policy index."""

    provider: str
    model: str
    dimensions: int = Field(ge=1)
    selected_at: datetime = Field(default_factory=utc_now)


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
