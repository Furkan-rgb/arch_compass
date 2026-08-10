"""Ollama's hosted models: the same API as a local server, behind a key.

A second descriptor rather than a mode on the first, because the two answer the same
question differently. "Ollama" today means the server on this machine, and a visitor
without one sees nothing from it — correctly, since there is nothing there. The cloud is
reachable from anywhere a key is, so it is offered by default and listed first, and the
local descriptor goes on appearing exactly when a local server does.

Nothing about the request differs, which is why nothing about it is written here: the
transport, its retries and its error mapping are `ollama`'s, and this module contributes an
endpoint, a credential and the list of models the cloud is asked for.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from typing import Final

from ollama import Client, ResponseError

from archcompass.adapters.models.ollama import (
    PROBE_TIMEOUT_SECONDS,
    REQUEST_FAILURES,
    OllamaChatTransport,
    client_for,
    probe_detail,
    thinking_modes_for,
)
from archcompass.adapters.models.structured import (
    ChatMessage,
    StreamingChatTransport,
    StructuredReasoningProvider,
    ThinkLevel,
    ToolCallingChatTransport,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.domain.model_catalog import AvailableModel, ProbeResult
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.ports.reasoning import ReasoningTask

PROVIDER_NAME: Final = "ollama-cloud"

# ─────────────────────────────────────────────────────────────────────────────────────────
# The hosted models this advisor offers, most preferred first. Edit this list to change what
# the model chooser puts in front of a reader; nothing else in this file needs touching.
#
# Authored for the reason the Google list is: which model a review runs against decides what
# it costs, how long it takes and how good the judgement is. There is the further reason the
# local list gives — Ollama reports nothing that separates a model worth judging with from an
# embedding model — and here it bites harder, because a hosted catalog is the vendor's to
# grow without asking.
#
# One name to begin with. `gpt-oss:20b` is the small open-weights reasoning model this cloud
# serves, it thinks by default, and it is the one that has been tried. A second cloud model
# is a line here and a probe run.
# ─────────────────────────────────────────────────────────────────────────────────────────
#: Whether ollama.com enforces the `format` grammar. It does not — measured 2026-08-10
#: on both its native and OpenAI-compatible endpoints (a closed two-field schema with a
#: trap invitation came back as fenced markdown with invented keys), and its own
#: documentation says the cloud does not support structured outputs. Without enforcement
#: the judge's reply cannot hold: one bearing per policy, 54 of them, bound by position —
#: gpt-oss:20b answered 19 and gpt-oss:120b answered 67, through the repair round, because
#: words cannot make a model count. The transport below already states the schema in the
#: prompt and unwraps fences, which took the failure from unparseable to a near miss; the
#: day Ollama ships cloud enforcement, flipping this single value is the whole of enabling
#: the provider, and every test of the probing path runs with it flipped.
CLOUD_ENFORCES_FORMAT: Final = False

OFFERED_MODELS: Final[tuple[str, ...]] = (
    #: The owner's opener: free tier, thinking and tools per its own capability report,
    #: and it held a stated schema exactly when the trap prompt invited it not to.
    "gpt-oss:20b",
    #: The same family with more room to think, same free tier, same measured conformance.
    "gpt-oss:120b",
)

#: Where the hosted models are. Ollama's own client speaks to this host with exactly the
#: protocol it speaks to a local server with, which is what makes the transport shared.
CLOUD_BASE_URL: Final = "https://ollama.com"

#: A rejected key is not a fact about the model that happened to be asked for. These two
#: statuses end the probe rather than narrowing its list, so the reader is told to fix the
#: credential instead of being told the cloud serves none of the models it plainly serves.
_AUTH_STATUS_CODES: Final = frozenset({401, 403})


def _offered(client: Client, model: str) -> AvailableModel:
    """One model the cloud was asked for, as the chooser will render it.

    `/api/show` is the request: it authenticates, it says whether this key reaches this exact
    model, and it reports the `capabilities` that decide the thinking modes — the same list
    the local probe reads, so the modes stay the server's answer rather than this file's.
    """

    shown = client.show(model)
    return AvailableModel(
        name=model,
        # As on a local server, Ollama offers no display name and the size is the most useful
        # thing it knows that the tag does not already say.
        label=(shown.details.parameter_size or "") if shown.details else "",
        thinking_modes=thinking_modes_for(shown.capabilities),
    )


def probe_ollama_cloud(defaults: ProviderDefaults) -> ProbeResult:
    """Whether the key works and which of the offered models it reaches.

    Never raises, for the reason `probe_ollama` does not: unavailability is the answer to the
    question, and a probe that raised would take the listing of every other provider with it.

    One `/api/show` per offered model rather than one `/api/tags` for all of them. The
    listing endpoint is what a local server is asked, because it reports what has been
    pulled; a hosted catalog has no such notion, and asking each name directly answers the
    question this probe actually has — does this key reach *this* model — for every catalog
    the cloud might grow. It costs one request per name in this file, which is the same
    budget the local probe already spends on capabilities.

    Deliberately without `_with_retry`, again as the local probe is: a dropdown is waiting.
    """

    if not CLOUD_ENFORCES_FORMAT:
        return ProbeResult(
            available=False,
            detail=(
                "ollama.com serves these models but does not yet enforce structured "
                "outputs, so a review's verdicts cannot be validated against it. The "
                "adapter is ready; see CLOUD_ENFORCES_FORMAT in its source."
            ),
        )
    base_url = defaults.resolved_base_url() or CLOUD_BASE_URL
    try:
        client = client_for(
            base_url=base_url,
            timeout=PROBE_TIMEOUT_SECONDS,
            api_key_env=defaults.api_key_env,
            provider=PROVIDER_NAME,
        )
    except ConfigurationError:
        # No key is not "no catalog". ollama.com answers `/api/show` anonymously — measured,
        # not assumed — so the models are listed from an uncredentialed client and the key
        # is owed where it is actually spent: the first judgement, which fails named
        # (`OLLAMA_API_KEY`, `.env`) and is recorded against the selection. That is the
        # registry's standing rule for what a listing cannot promise, and a chooser hiding
        # the whole cloud behind a variable nobody has heard of was the failure being fixed.
        # Should the cloud ever stop answering anonymously, the 401 below reports it with
        # the same cure in its detail.
        client = client_for(
            base_url=base_url,
            timeout=PROBE_TIMEOUT_SECONDS,
            api_key_env=None,
            provider=PROVIDER_NAME,
        )
    found: list[AvailableModel] = []
    for name in OFFERED_MODELS:
        try:
            found.append(_offered(client, name))
        except ResponseError as error:
            if error.status_code in _AUTH_STATUS_CODES:
                detail = probe_detail(base_url, error)
                if defaults.api_key_env:
                    detail = (
                        f"{detail} — set {defaults.api_key_env} in .env at the workspace "
                        "root, or export it."
                    )
                return ProbeResult(available=False, detail=detail)
            # Any other answer is about this model — a 404 for a name this cloud has
            # retired or never served — and costs it its row, not the provider's.
            continue
        except REQUEST_FAILURES as error:
            # No answer at all: the host is unreachable or the request never completed, which
            # is a fact about the provider rather than about one name.
            return ProbeResult(available=False, detail=probe_detail(base_url, error))
    if not found:
        # The key works and the requests arrived — this cloud simply serves none of the
        # models this advisor offers, which has its own cure: change the list at the top of
        # this file to a name it does serve.
        return ProbeResult(
            available=False,
            detail=(
                f"{base_url} answered but serves none of {', '.join(OFFERED_MODELS)}"
            ),
        )
    return ProbeResult(available=True, models=found)




def _stated_schema(messages: list[ChatMessage], schema: Mapping[str, object]) -> list[ChatMessage]:
    """The schema, appended to the request's last user turn as text.

    ollama.com accepts `format` and does not enforce it — measured, twice: told to sneak
    extra fields past a closed schema, gpt-oss and gemma alike answered fenced markdown
    with invented keys, which means the grammar never reached the sampler and the model
    never saw the shape at all. Stated in the prompt, both gpt-oss models answered the
    exact object and nothing else. So on this transport the schema travels as words, the
    way every provider without grammar support takes it, and validation plus the one
    repair round stay what they always were: the contract's real enforcement.

    `format` is still sent. The day the cloud starts compiling it, enforcement arrives
    for free and this instruction becomes harmless repetition.
    """

    stated = list(messages)
    for index in range(len(stated) - 1, -1, -1):
        if stated[index]["role"] == "user":
            stated[index] = {
                "role": "user",
                "content": (
                    f"{stated[index]['content']}\n\n"
                    "Reply with exactly one JSON object conforming to this JSON Schema — "
                    "no markdown fences, no extra keys, nothing outside the object:\n"
                    + json.dumps(dict(schema), sort_keys=True)
                ),
            }
            break
    return stated


def _unfenced(content: str) -> str:
    """The reply without the markdown fence a cloud model may still wrap it in.

    Tolerated at the transport rather than repaired by the model, because it is transport
    residue and not content: the object inside is unchanged, and spending the one repair
    round on punctuation would leave nothing for a reply that is actually wrong.
    """

    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


class OllamaCloudChatTransport(OllamaChatTransport):
    """The local transport against ollama.com, with the schema stated instead of assumed.

    Everything else — retries, options, thinking, the tool loop (which never carries a
    format) — is inherited unchanged.
    """

    provider_label = "Ollama cloud"

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        return _unfenced(
            super().complete(
                _stated_schema(messages, schema),
                schema=schema,
                task=task,
                think=think,
                temperature=temperature,
            )
        )

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]:
        """The inherited stream, with any leading fence withheld and any trailing one cut.

        A fence arrives split across chunks, so the guard buffers until it has seen either
        the fence's own newline or proof there is none, and holds the last few characters
        back until the stream ends — the accumulated whole must be the same text
        `complete` would have returned, or validation would judge a reply nobody sent.
        """

        chunks = super().stream(
            _stated_schema(messages, schema),
            schema=schema,
            task=task,
            think=think,
            temperature=temperature,
        )
        buffer = ""
        opened = False
        for chunk in chunks:
            buffer += chunk
            if not opened:
                probe = buffer.lstrip()
                if not probe:
                    continue
                if probe.startswith("`") and len(probe) <= 3:
                    continue
                if probe.startswith("```"):
                    if "\n" not in probe:
                        continue
                    buffer = probe.split("\n", 1)[1]
                opened = True
            # Held back so a trailing fence can be cut before anyone reads it.
            if len(buffer) > 4:
                yield buffer[:-4]
                buffer = buffer[-4:]
        tail = buffer.rstrip()
        if tail.endswith("```"):
            tail = tail[:-3].rstrip()
        yield tail


#: See the local adapter's statements of the same name: conformance said where the class
#: is defined, so an isinstance by method name cannot drift.
_conforms_streaming: type[StreamingChatTransport] = OllamaCloudChatTransport
_conforms_tools: type[ToolCallingChatTransport] = OllamaCloudChatTransport


class OllamaCloudReasoningProvider(StructuredReasoningProvider):
    def __init__(self, config: ReasoningModelConfig) -> None:
        super().__init__(config, OllamaCloudChatTransport(config))


#: How this build reaches Ollama's hosted models, stated once and read by the composition
#: root.
#:
#: No `base_url_env`. The local descriptor has one because the machine holding the models is
#: the thing a deployment varies; there is one ollama.com.
DESCRIPTOR: Final = ProviderDescriptor(
    name=PROVIDER_NAME,
    build=OllamaCloudReasoningProvider,
    probe=probe_ollama_cloud,
    defaults=ProviderDefaults(
        base_url=CLOUD_BASE_URL,
        api_key_env="OLLAMA_API_KEY",
        # The variable the vendor's own client and CLI already read, so a machine signed in
        # to ollama.com needs nothing new set for this to work.
        #
        # `gpt-oss:20b` publishes a 131072-token context window (ollama.com/library/gpt-oss),
        # which is what the generic default already assumes; it is stated rather than
        # inherited so that a second model with a different window is a visible decision. The
        # output budgets stay the shared ones for the reason they are shared: they size a
        # stage's answer, not the model's ceiling, and the catalog clamps them downward to
        # whatever a probe reports.
        context_window_tokens=131072,
        # A fleet, not a GPU. The local descriptor's one-at-a-time default exists because a
        # local server runs one model on one card, where parallel judgements queue behind
        # each other and time out rather than finish sooner; hosted requests are served side
        # by side. Four rather than as many as the review has boundaries, because a hosted
        # account meters requests and a burst of forty meets the limit instead of the answers.
        concurrent_requests=4,
    ),
)
