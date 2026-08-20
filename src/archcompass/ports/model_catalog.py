"""The boundaries around choosing a reasoning model: probing, storing, resolving.

None of these are `runtime_checkable`, and none of them carry the `_conforms` line the
streaming protocols do. That idiom exists for protocols reached by `isinstance`, which
compares method names alone. Everything here is passed by name into a typed parameter, so
the signature is already checked at each call site.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.records import (
    EmbeddingModelCatalog,
    EmbeddingModelSelection,
    ProbeResult,
    ReasoningModelSelection,
)

#: How many judgements a run may have in flight, overriding whatever the chosen provider's
#: descriptor says. Read where a resolved configuration is built, so it reaches a local run
#: and a hosted one by the same path — the pin a command line asks for and the selection a
#: workspace stores are both assembled by `reasoning_config`.
#:
#: `1` restores sequential judging exactly, which is what makes this the knob to reach for
#: when a provider starts refusing parallel requests: there is nothing to redeploy.
CONCURRENT_REQUESTS_VARIABLE: Final = "ARCHCOMPASS_MODEL_CONCURRENT_REQUESTS"

#: The ceiling on that, wherever the number comes from. A review is tens of boundaries, so
#: past a handful in flight the wait is bounded by the slowest single judgement rather than
#: by how many are running, and every further request is one more way to meet a rate limit.
MAX_CONCURRENT_REQUESTS: Final = 16


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
    #: Deliberately well below what a vendor advertises. This number only feeds the
    #: pre-flight budget check, where under-stating refuses an oversize request with an
    #: explicit message and over-stating lets one through to be truncated.
    context_window_tokens: int = 131072
    #: Output budget for a non-thinking selection.
    max_output_tokens: int = 16384
    #: Output budget for a thinking selection — larger because thinking tokens are spent
    #: from the same allowance on both providers, so a stage needs noticeably more headroom
    #: here than the response JSON alone would suggest.
    max_output_tokens_thinking: int = 32768
    chars_per_token: float = 4.0
    #: How many judgements this provider will answer at once. A property of the provider and
    #: not of the review: a hosted API serves parallel requests from a fleet, while a local
    #: Ollama serves one model on one GPU, where parallel requests queue behind each other
    #: and time out rather than finish sooner. One is therefore the only safe default, and a
    #: provider that can do better says so.
    concurrent_requests: int = 1

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

    def resolved_concurrent_requests(self) -> int:
        """How many judgements to run at once, letting an operator override the descriptor.

        Read at every use for the same reason the endpoint is: whoever starts the process
        sets it, and a value baked in at import time is one a deployment cannot change. An
        empty value counts as unset, so `FOO=` in a `.env` is how the knob gets commented
        out rather than a way to set it to nothing.

        The variable is one knob for the whole run rather than one per provider. It exists
        for the two answers an operator actually needs — "stop parallelising" and "this
        endpoint can take more than the descriptor assumes" — and neither is a sentence
        about a provider they are not using.
        """

        raw = os.environ.get(CONCURRENT_REQUESTS_VARIABLE, "").strip()
        if not raw:
            return self.concurrent_requests
        try:
            requested = int(raw)
        except ValueError as error:
            raise ConfigurationError(
                f"{CONCURRENT_REQUESTS_VARIABLE} must be a whole number, not {raw!r}."
            ) from error
        if requested < 1:
            raise ConfigurationError(
                f"{CONCURRENT_REQUESTS_VARIABLE} must be at least 1, not {requested}. "
                "One is sequential judging, which is the behaviour this replaces."
            )
        # Clamped rather than refused at the top end: the ceiling is a judgement about what
        # is worth having in flight against any provider, not about what the operator was
        # allowed to ask for, and refusing the run over it would be the more surprising of
        # the two answers.
        return min(requested, MAX_CONCURRENT_REQUESTS)


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
    #: How the name is written for a reader: `Google`, `Groq`, `Ollama`. Empty where the
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
