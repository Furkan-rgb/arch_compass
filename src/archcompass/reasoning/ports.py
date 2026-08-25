"""What reasoning asks the outside world for: a model, a repository, a reader.

Three boundaries, in the order a review meets them.

**Choosing a model** — `ProviderDescriptor` and the selection repositories. What a provider
offers, what it defaults to, and which one this workspace picked. None of these are
`runtime_checkable` and none carry the `_conforms` line the streaming protocols do: that
idiom is for protocols reached by `isinstance`, which compares method names alone, and
everything here is passed by name into a typed parameter.

**Looking things up** — `SourceInvestigator` and `InvestigatorSource`. The one boundary in
the codebase where the model chooses what to look at, and it exists because of a failure
that has no other cure. A judgement sees pinned excerpts and nothing else, so when its
verdict turns on a fact those excerpts do not carry it emits a hinge — and a hinge stops the
review to ask a person. Many of them are questions for the repository: how a symbol is used,
whether anything implements a port, whether a seam has tests. The judgement contract already
forbids asking a person one of those, while giving the judgement no way to find out.

The split that lookup lives under is deliberate and narrow. Verdict evidence stays
application-chosen: the detector picks the spans, the application reads them, and nothing a
model asks for is pinned as evidence. What is allowed is *investigation* — finding out,
before interrupting somebody, whether the interruption is warranted — and it is allowed only
because every lookup is recorded. A finding nobody can trace back to a call is the
unverifiable evidence the charter refuses; a transcript of exactly what was asked and
exactly what came back is not. It is surface-agnostic on purpose: a hinge investigation and
a reader asking "where else is this used?" have the same problem, and a second toolbox for
the second one would have been a second set of bounds to get wrong.

**Answering a reader** — `ReviewConversation` and the store behind it, for the chat held
against a review that has already been written."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain import (
    RecordedInvestigation,
    RepositoryAtlas,
    RepositoryRef,
    Review,
    Termination,
)
from archcompass.reasoning.records import (
    EmbeddingModelCatalog,
    EmbeddingModelSelection,
    ProbeResult,
    ReasoningModelSelection,
)


@dataclass(frozen=True)
class ProviderDefaults:
    """Everything about reaching one provider that is not the model's name.

    These numbers were hand-authored in a `models.*.yaml` per workspace, which asked every
    reader to maintain a file whose every field but one was the same in every copy of it.
    They are properties of the provider — what its endpoint is, which variable carries its
    credential, how generous a budget check may be — so they belong beside the transport
    that has to satisfy them.
    """

    #: Where the provider is reached. Required by a self-hosted provider such as Ollama; a
    #: hosted SDK that knows its own endpoint leaves it unset.
    base_url: str | None = None
    #: Env var that overrides `base_url` at resolution time, so a deployment can move a
    #: self-hosted provider without a code change.
    base_url_env: str | None = None
    #: Names the environment variable holding this provider's API key - never the key.
    api_key_env: str | None = None
    timeout_seconds: float = 360.0
    #: How much the model is given to work in. On a hosted provider it is a sanity bound on
    #: what this deployment will ask for; on a self-hosted one it is `num_ctx`, and the
    #: runner allocates it before answering anything — see `OLLAMA_DESCRIPTOR`, which sets
    #: its own from what this product actually sends.
    #:
    #: Deliberately well below what a vendor advertises. Nothing measures a prompt against
    #: it: there was a pre-flight budget check that did, and the estimate it read, the error
    #: it raised and the check itself were all removed together once it turned out that none
    #: of the three had ever run.
    context_window_tokens: int = 131072
    #: Output budget for a non-thinking selection.
    max_output_tokens: int = 16384
    #: Output budget for a thinking selection — larger because thinking tokens are spent
    #: from the same allowance on both providers, so a stage needs noticeably more headroom
    #: here than the response JSON alone would suggest.
    max_output_tokens_thinking: int = 32768
    #: How many judgements this provider will be asked for at once.
    #:
    #: A review fans every selected candidate out at once — forty-six branches on this
    #: repository — and each branch is one request. That is a description of the work, not
    #: of what a provider can take, and nothing used to stand between the two: the requests
    #: were all sent, and whoever was on the other end decided what to do with them.
    #:
    #: A hosted API answers them in parallel and the fan-out is the point. A local runner
    #: has one slot and answers them one at a time, so the other forty-five sit in its queue
    #: spending a deadline that started when they were sent rather than when they were
    #: served — and a queue deeper than `timeout_seconds` divided by the time one judgement
    #: takes cannot drain before the tail of it times out. That is not a slow review, it is
    #: a review that fails after paying for most of itself; see `OLLAMA_DESCRIPTOR`.
    #:
    #: Eight rather than unbounded for the hosted default, because a burst of forty-six is
    #: not something a rate limit reads kindly either.
    max_parallel_requests: int = 8

    def resolved_base_url(self) -> str | None:
        """The endpoint to use now, letting the environment move a self-hosted provider.

        Read at every use rather than resolved once at import, because the variable is set
        by whoever starts the process and a value baked in at import time is one a
        deployment cannot change. An empty value counts as unset: `FOO=` in a `.env` is how
        a variable gets commented out in practice, and it must not blank the endpoint.
        """

        if self.base_url_env:
            override = os.environ.get(self.base_url_env, "").strip()
            if override:
                return override
        return self.base_url


#: Whether a provider is reachable and what it currently offers.
#:
#: A plain function rather than a method on the reasoner, and that is the whole design.
#: Constructing a provider is exactly what fails when a provider is unavailable — the Google
#: transport resolves its API key in `__init__` — so a probe reached through a constructed
#: reasoner could never report the most common reason for unavailability. It also lets the
#: probe set its own timeout: a transport bakes in `timeout_seconds`, which is 360 and is
#: right for a judgement, not for a dropdown.
#:
#: Takes the defaults rather than a resolved `ReasoningModelConfig`: a probe asks what a
#: provider has, which is a question with no model in it, and the only fields one ever read
#: were the endpoint and the credential variable.
type ReasoningModelProbe = Callable[[ProviderDefaults], ProbeResult]

@dataclass(frozen=True)
class ProviderDescriptor:
    """One provider this application can reach, registered by the module that implements it.

    Exported as `DESCRIPTOR` from each adapter module, so adding a provider is adding a
    module and naming it once in the composition root rather than editing three parallel
    tables that drift.
    """

    name: str
    probe: ReasoningModelProbe
    defaults: ProviderDefaults
    #: How the name is written for a reader: `Google`, `OpenRouter`, `Ollama`. Empty where the
    #: name already reads as one. Held here rather than in the interface because a chooser
    #: that titled its own sections would need a table of every provider this build can
    #: reach — the second copy of `_ALL_PROVIDERS`, kept in another language.
    label: str = ""


class ReasoningModelSelectionRepository(Protocol):
    """The one row a workspace keeps about which model it reasons with."""

    def get(self) -> ReasoningModelSelection | None: ...

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection: ...

    def clear(self) -> None: ...

    def record_failure(self, detail: str) -> None: ...

    def clear_failure(self) -> None: ...


class EmbeddingModelSelectionRepository(Protocol):
    def get(self) -> EmbeddingModelSelection | None: ...

    def set(self, selection: EmbeddingModelSelection) -> EmbeddingModelSelection: ...

    def clear(self) -> None: ...


class EmbeddingModelDiscovery(Protocol):
    def discover(self, providers: tuple[ProviderDescriptor, ...]) -> EmbeddingModelCatalog: ...


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


@dataclass(frozen=True)
class ToolSpec:
    """One tool as a model is offered it: what it is called, what it does, what it takes.

    `parameters` is JSON Schema for the arguments object, and it is carried as plain data
    rather than as a Pydantic model for the same reason a response schema is: a transport
    hands it to a vendor that wants JSON Schema, and a shape assembled above the transport
    boundary must not need translating on the way down.
    """

    name: str
    description: str
    parameters: Mapping[str, object]


@dataclass(frozen=True)
class RecordedLookup:
    """One call and its answer, kept whether or not the answer was any use.

    The failures matter most. A pass that asked four times and was refused four times kept
    its hinge from nothing, and without the refused calls the record would show an
    investigation that never happened as one that found nothing to say.
    """

    tool: str
    arguments: Mapping[str, object]
    result: str


class SourceInvestigator(Protocol):
    """A repository, as a small set of read-only questions a pass may put to it."""

    @property
    def tools(self) -> Sequence[ToolSpec]:
        """Everything this investigator can be asked, in the order a model is shown them."""
        ...

    def call(self, name: str, arguments: Mapping[str, object]) -> str:
        """Run one lookup and return what it found, as text the model reads.

        **This never raises.** An unknown tool, an argument of the wrong type, a node id
        that does not exist, a repository that has moved — each comes back as a sentence
        saying so. That is not leniency: the alternative is a review that fails because a
        model guessed at an identifier, and a hinge that had to be kept is a far better
        outcome than a run that produced nothing at all.

        Every call is appended to `transcript` before this returns, including the ones that
        answered nothing.
        """
        ...

    @property
    def transcript(self) -> Sequence[RecordedLookup]:
        """Every call made through this investigator, in the order they were made."""
        ...

    def conclude(self, closing: str, termination: Termination) -> None:
        """Close the record: what the pass said, and why its execution ended.

        Called once, by the loop that drove the investigation, on every way out of it.
        Neither half can be recovered from the transcript: `closing` is the model's own
        prose, which carries no authority over a verdict and is kept for a human reader,
        and `termination` is the loop's account of why it stopped.

        `termination` is not optional, because every way out is a reason. It used to be a
        sentence that two of the four exits wrote and the other two left blank — so a run
        that exhausted its turns was stored identically to one that had finished asking, and
        nothing downstream could tell a partial investigation from a complete one.

        Here rather than returned to the caller because the transcript is here. A record
        assembled from a return value and a property read separately is one a later exit
        path can leave half-written, and the half that would go missing is the reason the
        looking ended.
        """
        ...

    @property
    def closing(self) -> str:
        """What the pass said it made of its findings, or "" until it has said anything."""
        ...

    @property
    def termination(self) -> Termination | None:
        """Why execution ended, or None until it has ended."""
        ...


@dataclass(frozen=True)
class OfferedInvestigator:
    """A toolbox, or the application's own sentence about why there is none.

    One value rather than two reads, because the two facts are produced together and must
    not be readable apart: a caller that found `investigator is None` and never looked for
    the reason would report an investigation that found nothing, when what happened is that
    nothing could look. That sentence is shown to a reader verbatim, so it names the way
    back — re-index this repository — rather than describing a fault.
    """

    investigator: SourceInvestigator | None = None
    withheld: str = ""


class InvestigatorSource(Protocol):
    """Where a toolbox over one review's own atlas comes from."""

    def for_review(
        self, repository: RepositoryRef, atlas: RepositoryAtlas
    ) -> OfferedInvestigator:
        """A toolbox answering about exactly the atlas this review judged.

        The atlas is passed in rather than looked up. A review analyses a repository into an
        atlas it never persists, so a toolbox that fetched the latest *indexed* atlas would
        answer about a different snapshot than the verdicts were reached against — which is
        the one failure the recording exists to make impossible.
        """
        ...


@dataclass(frozen=True, slots=True)
class ConversationAnswer:
    text: str
    supporting_candidate_ids: tuple[str, ...] = ()
    #: What the answer looked up in the repository before it was written, where anything
    #: was. Carried inline rather than by identity, unlike a finding's: a conversation
    #: holds a handful of messages that are read together, not a docket of forty rows
    #: that are scanned.
    investigation: RecordedInvestigation | None = None


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    question: str
    answer: ConversationAnswer
    asked_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewConversation:
    id: str
    review_id: str
    messages: tuple[ConversationMessage, ...] = ()


class ConversationStore(Protocol):
    def record(self, conversation: ReviewConversation) -> ReviewConversation: ...

    def get(self, conversation_id: str) -> ReviewConversation: ...

    def list_for_review(self, review_id: str) -> tuple[ReviewConversation, ...]: ...

    def delete(self, conversation_id: str) -> None: ...


class ReviewAnswerer(Protocol):
    def answer(
        self,
        review: Review,
        history: tuple[ConversationMessage, ...],
        question: str,
    ) -> ConversationAnswer: ...
