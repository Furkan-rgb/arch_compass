"""Providers that speak OpenAI's chat API, reached through one transport.

Groq, Cerebras, OpenRouter, vLLM and a dozen others answer the same three endpoints on
different hosts. Written as one provider each in the sense that matters to a chooser — they
have their own credentials, their own models and their own quotas — and as one transport in
the sense that matters to the code, because there is only one wire format between them.

Which is the whole reason this module exists rather than a `groq.py` beside a `cerebras.py`.
The parts that genuinely differ per vendor are data: an endpoint, a credential variable, a
list of models, a concurrency the free tier tolerates. Adding the next one is adding an
`OpenAICompatibleProvider` to `PROVIDERS`, and nothing here or in the factory changes.

The models are named rather than discovered, which is deliberate and is not about the
endpoint being unable to list them — it can, and the probe reads that listing. It is about
what judging needs. Every judgement is a structured call against a JSON schema, and an
endpoint's catalogue is full of models that will not honour one: transcription models,
embedding models, and chat models whose runtime answers `response_format` with prose. A
model that cannot hold a schema does not fail at selection time, it fails forty times in the
middle of a review. So the listing is intersected with a list somebody has actually judged
with, and a vendor renaming a model takes a row off the chooser instead of putting a broken
one on it — with `models_env` as the way out when that happens between releases.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Final, cast

import httpx

from archcompass.configuration import resolve_api_key
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.records import AvailableModel, ProbeResult

#: How long a listing may take before the chooser gives up on it. The same two seconds the
#: other probes allow: this answers a dropdown, not a review.
_PROBE_TIMEOUT: Final = 2.0


@dataclass(frozen=True, slots=True)
class ApprovedModel:
    """One model on a vendor's endpoint that this build is willing to judge with."""

    #: Exactly as the endpoint names it, because it is what the request carries.
    name: str
    label: str


@dataclass(frozen=True, slots=True)
class OpenAICompatibleProvider:
    """Everything that differs between two vendors of the same API.

    Held beside the descriptor rather than inside `ProviderDefaults` because these are facts
    about a vendor's catalogue, and the defaults are facts about reaching a host. The probe
    needs both; the transport needs only the second, which is why `build_chat_model` can
    treat every provider here identically without knowing which one it has.
    """

    name: str
    #: How a person writes it: `Groq`, not `groq`. The chooser groups by provider, and a
    #: heading is a name rather than a key.
    label: str
    base_url: str
    api_key_env: str
    models: tuple[ApprovedModel, ...]
    #: Names an environment variable holding a comma-separated list of model ids to offer
    #: instead of `models`. The escape hatch for a vendor that renamed something after this
    #: was released: the alternative is waiting for a new version to reach a model the key
    #: already pays for. Still intersected with the live listing, so a typo shows up as an
    #: absent row rather than as a request that fails mid-review.
    models_env: str
    #: What the free tier tolerates in flight. Hosted fleets answer several at once, but
    #: these are metered per minute rather than per fleet, so the number is chosen against
    #: the quota rather than against the hardware.
    concurrent_requests: int = 4
    #: Deliberately at or below the smallest window in `models` — under-stating refuses an
    #: oversize request by name, over-stating lets one through to be truncated.
    context_window_tokens: int = 131_072


GROQ = OpenAICompatibleProvider(
    name="groq",
    label="Groq",
    base_url="https://api.groq.com/openai/v1",
    api_key_env="GROQ_API_KEY",
    models_env="ARCHCOMPASS_GROQ_MODELS",
    models=(
        ApprovedModel(name="openai/gpt-oss-120b", label="GPT-OSS 120B"),
        ApprovedModel(name="openai/gpt-oss-20b", label="GPT-OSS 20B"),
        ApprovedModel(name="moonshotai/kimi-k2-instruct-0905", label="Kimi K2 Instruct"),
        ApprovedModel(name="llama-3.3-70b-versatile", label="Llama 3.3 70B"),
    ),
)

CEREBRAS = OpenAICompatibleProvider(
    name="cerebras",
    label="Cerebras",
    base_url="https://api.cerebras.ai/v1",
    api_key_env="CEREBRAS_API_KEY",
    models_env="ARCHCOMPASS_CEREBRAS_MODELS",
    models=(
        ApprovedModel(name="gpt-oss-120b", label="GPT-OSS 120B"),
        ApprovedModel(
            name="qwen-3-235b-a22b-instruct-2507", label="Qwen 3 235B Instruct"
        ),
        ApprovedModel(name="llama-3.3-70b", label="Llama 3.3 70B"),
    ),
    # Several of these are served with a shorter window than the same weights elsewhere,
    # and the budget check is the one place where guessing high is the expensive mistake.
    context_window_tokens=65_536,
)

#: Every vendor of this API this build knows how to reach.
PROVIDERS: Final = (GROQ, CEREBRAS)

#: The names of them, for the one dispatch that has to recognise the family rather than the
#: vendor: constructing the chat model. A set rather than a chain of comparisons, because it
#: has to keep agreeing with `PROVIDERS` and a chain would not.
OPENAI_COMPATIBLE_PROVIDERS: Final = frozenset(
    provider.name for provider in PROVIDERS
)


def _offered(provider: OpenAICompatibleProvider) -> tuple[ApprovedModel, ...]:
    """The models to look for, letting the environment name them instead.

    Read at every probe rather than at import, for the reason every other override here is:
    the variable is set by whoever starts the process, and a value baked in is one a
    deployment cannot change. An override carries no labels, because nobody typing a model
    id into an environment variable also wants to type a display name for it.
    """

    raw = os.environ.get(provider.models_env, "").strip()
    if not raw:
        return provider.models
    named = [item.strip() for item in raw.split(",") if item.strip()]
    return tuple(ApprovedModel(name=item, label="") for item in named)


def _listed(base_url: str, api_key: str) -> set[str]:
    """Every model id the endpoint says it has."""

    response = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_PROBE_TIMEOUT,
    )
    response.raise_for_status()
    body = cast(object, response.json())
    if not isinstance(body, dict):
        return set()
    data = cast(Mapping[str, object], body).get("data")
    if not isinstance(data, list):
        return set()
    listed: set[str] = set()
    for entry in cast(list[object], data):
        if not isinstance(entry, dict):
            continue
        identifier = cast(Mapping[str, object], entry).get("id")
        if isinstance(identifier, str):
            listed.add(identifier)
    return listed


def probe_openai_compatible(
    provider: OpenAICompatibleProvider, defaults: ProviderDefaults
) -> ProbeResult:
    """Whether the key reaches this vendor, and which approved models it currently has.

    Takes the provider ahead of the defaults so it can be bound with `partial` into the
    single-argument shape the port asks for — the probe signature has no room for a vendor,
    on purpose, because the question "what do you have" is the same question everywhere.
    """

    try:
        api_key = resolve_api_key(defaults.api_key_env, provider=provider.name)
    except ConfigurationError as error:
        return ProbeResult(available=False, detail=str(error))
    base_url = defaults.resolved_base_url() or provider.base_url
    try:
        available = _listed(base_url, api_key)
    except (httpx.HTTPError, ConnectionError, KeyError, TypeError, ValueError) as error:
        return ProbeResult(available=False, detail=f"{base_url}: {error}")

    offered = [model for model in _offered(provider) if model.name in available]
    if not offered:
        return ProbeResult(
            available=False,
            detail=(
                f"the configured key reaches none of the models Arch Compass judges with "
                f"on {provider.label}. Name others with {provider.models_env} if they have "
                f"been renamed."
            ),
        )
    return ProbeResult(
        available=True,
        models=[
            AvailableModel(
                name=model.name,
                label=model.label,
                # Offered in one mode only, and that is a claim about the request rather
                # than about the models. Asking for reasoning has to reach a provider as an
                # instruction or not be offered at all, and this API spells it three
                # incompatible ways across these vendors — a `reasoning_effort` level here,
                # a field inside the model's own parameters there, nothing at all on the
                # non-reasoning models. `None` is the honest answer: the model does
                # whatever it does by default, and nothing here pretends to have asked.
                thinking_modes=(None,),
            )
            for model in offered
        ],
    )


def descriptors() -> tuple[ProviderDescriptor, ...]:
    """One descriptor per vendor, each with its own probe already bound to it."""

    return tuple(
        ProviderDescriptor(
            name=provider.name,
            label=provider.label,
            probe=partial(probe_openai_compatible, provider),
            defaults=ProviderDefaults(
                base_url=provider.base_url,
                # No `base_url_env`: these are hosted endpoints with one address, and a
                # variable that could point `groq` at somebody else's host would make the
                # provider's name stop describing where the request went.
                api_key_env=provider.api_key_env,
                context_window_tokens=provider.context_window_tokens,
                concurrent_requests=provider.concurrent_requests,
            ),
        )
        for provider in PROVIDERS
    )
