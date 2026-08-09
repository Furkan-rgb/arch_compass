"""Ollama transport: schema-constrained structured output from a local Ollama server.

Only the vendor-specific half lives here. Which stage runs, what it may reference, and
what shape its answer must take are decided in `structured`, above this boundary.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Final

import httpx
from ollama import Client, ResponseError

from archcompass.adapters.models.structured import (
    AssistantToolTurn,
    ChatMessage,
    InvestigationMessage,
    StreamingChatTransport,
    StructuredReasoningProvider,
    ThinkLevel,
    ToolCall,
    ToolCallingChatTransport,
    ToolExchange,
    ToolResultTurn,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ProviderError
from archcompass.domain.model_catalog import AvailableModel, ProbeResult
from archcompass.ports.investigation import ToolSpec
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.ports.reasoning import ReasoningTask

PROVIDER_NAME: Final = "ollama"

# ─────────────────────────────────────────────────────────────────────────────────────────
# The local models this advisor offers, most preferred first. Edit this list to change what
# the model chooser puts in front of a reader; nothing else in this file needs touching.
#
# A pulled model is not a model that can judge a boundary. `/api/tags` lists everything the
# server holds and says nothing about what any of it does, so an embedding model appears
# beside a reasoning one and reads exactly the same — `embeddinggemma:latest` was offered,
# and chosen, and would have failed at the first boundary of a review.
#
# The cost here is sharper than on a hosted provider: these are models somebody pulled
# deliberately, so pulling a new one and not seeing it in the chooser is a surprise the file
# has to explain. It is still the right trade — a chooser that lists whatever happens to be
# on disk is not offering a choice, it is showing an inventory — but a name missing from
# this list is the first thing to check when a pulled model does not appear.
#
# Which models are offered stays an authored decision; whether each of them can think is the
# server's answer, not this file's. `/api/tags` reports no capability, but `/api/show` does —
# a `capabilities` list carrying "thinking" — and that is what decides the modes. It is not
# cosmetic: Ollama rejects `think` outright for a model without the capability, so a model
# offered as "not thinking" that cannot think would fail at the first boundary of a review
# rather than quietly ignore the request. Declaring the modes here got `gemma4:26b` wrong in
# exactly that direction, which is why they are now asked for.
# ─────────────────────────────────────────────────────────────────────────────────────────
OFFERED_MODELS: Final[tuple[str, ...]] = (
    "gemma4:26b",
    "gemma4:31b",
    "gemma4:12b",
    "qwen3.6:35b",
    "qwen3.6:27b",
)

_MAX_TRANSPORT_ATTEMPTS: Final = 3
_BACKOFF_BASE_SECONDS: Final = 0.5
#: Retryable by construction: the request never reached a model, or the server failed
#: in a way a later identical request may not. `LocalProtocolError` and
#: `UnsupportedProtocol` are deliberately absent - they are configuration faults that
#: fail identically every time.
_TRANSIENT_TRANSPORT_ERRORS: Final = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    httpx.ProxyError,
)
_TRANSIENT_STATUS_CODES: Final = frozenset({408, 429, 500, 502, 503, 504})


def _is_transient(error: Exception) -> bool:
    """Whether a later identical request might survive this failure.

    The client converts `httpx.ConnectError` into a builtin `ConnectionError` and
    `httpx.HTTPStatusError` into `ResponseError`, so both shapes appear here; other
    httpx errors reach us unwrapped. A 4xx other than 408/429 is a request the server
    rejects identically every time and is never retried.
    """

    if isinstance(error, ResponseError):
        return error.status_code in _TRANSIENT_STATUS_CODES
    return isinstance(error, (ConnectionError, *_TRANSIENT_TRANSPORT_ERRORS))


def _with_retry[Result](operation: Callable[[], Result]) -> Result:
    """Run one model request, retrying only transient transport failures.

    A structured-output validation failure is never retried here: it is raised by the
    caller after this returns, so the single sanctioned repair round stays the only
    second attempt at content.
    """

    for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as error:
            if not _is_transient(error) or attempt == _MAX_TRANSPORT_ATTEMPTS:
                raise
        time.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
    raise ProviderError(  # pragma: no cover - the loop always returns or raises
        f"Ollama request failed after {_MAX_TRANSPORT_ATTEMPTS} attempts"
    )


#: What a failed request may raise once the client has done its own mapping. Listed rather
#: than caught as `Exception`, so a fault in this package surfaces as itself.
_REQUEST_FAILURES: Final = (
    ResponseError,
    httpx.HTTPError,
    ConnectionError,
    KeyError,
    TypeError,
    ValueError,
)


def _as_provider_error(error: Exception) -> ProviderError:
    """One message for a failed reasoning request, streamed or not.

    The client turns an HTTP error into `ResponseError`, keeping the body and the status.
    Preserve both, bounded, so a failed run records why.
    """

    if isinstance(error, ResponseError):
        detail = error.error.strip()
        if len(detail) > 1000:
            detail = detail[:999].rstrip() + "…"
        suffix = f": {detail}" if detail else ""
        return ProviderError(
            f"Ollama reasoning request failed with HTTP {error.status_code}{suffix}"
        )
    return ProviderError(f"Ollama reasoning request failed: {error}")


#: What a liveness check may spend. `timeout_seconds` is 360, which is right for a judgement
#: and absurd for a question a dropdown is waiting on: a firewalled host would hold the
#: picker open for six minutes before admitting nothing is there.
PROBE_TIMEOUT_SECONDS: Final = 2.0


def _probe_detail(base_url: str, error: Exception) -> str:
    """Why the server could not be asked, as something a reader can act on.

    A sentence rather than an exception's `str`: "nothing is listening at
    http://127.0.0.1:11434" names the cure and "ConnectionError" does not.
    """

    if isinstance(error, ResponseError):
        detail = error.error.strip()
        if len(detail) > 200:
            detail = detail[:199].rstrip() + "…"
        suffix = f": {detail}" if detail else ""
        return f"HTTP {error.status_code}{suffix}"
    if isinstance(error, httpx.TimeoutException):
        return f"{base_url} did not answer within {PROBE_TIMEOUT_SECONDS:g}s"
    if isinstance(error, ConnectionError):
        return f"nothing is listening at {base_url}"
    return str(error)


def _thinking_modes(client: Client, model: str | None) -> tuple[bool | None, ...]:
    """Whether this server will accept `think` for this model, asked model by model.

    `/api/show` is the only endpoint that says so — `capabilities` carries "thinking" — and
    it is one request per model found. That fits the two-second budget because these are
    local reads of a manifest the server already holds: sub-millisecond each, against at
    most as many models as this file names, on a host that has just answered `/api/tags`.
    The alternative is what stood here, a declared list that was wrong about `gemma4:26b`.

    A `show` that fails takes only its own model's modes with it. The model is listed, it
    was found, and the honest thing to say about a capability nobody answered for is
    nothing — which is what `(None,)` sends.
    """

    if model is None:  # pragma: no cover - a listing entry always names its model
        return (None,)
    try:
        capabilities = client.show(model).capabilities or []
    except _REQUEST_FAILURES:
        return (None,)
    return (True, False) if "thinking" in capabilities else (None,)


def probe_ollama(defaults: ProviderDefaults) -> ProbeResult:
    """Which of the offered models this Ollama server has pulled, or why it could not be asked.

    Never raises. Unavailability is the answer to the question, not a failure to answer it:
    a picker has to be able to show "Ollama is not running" beside the providers that are,
    and an exception here would take the whole listing down with it.

    Deliberately without `_with_retry`. This is a liveness check, and a server that is not
    running is not going to start during three attempts with backoff — all that buys is six
    seconds of a reader waiting to be told something already known after the first.
    """

    base_url = defaults.resolved_base_url()
    if not base_url:
        return ProbeResult(available=False, detail="this provider sets no base_url")
    client = Client(host=base_url, timeout=PROBE_TIMEOUT_SECONDS)
    try:
        listed = client.list()
    except _REQUEST_FAILURES as error:
        return ProbeResult(available=False, detail=_probe_detail(base_url, error))
    found = {
        entry.model: AvailableModel(
            name=entry.model,
            # Ollama offers no display name, so the size is the most useful thing it knows
            # that the tag does not already say.
            label=(entry.details.parameter_size or "") if entry.details else "",
            thinking_modes=_thinking_modes(client, entry.model),
        )
        for entry in listed.models
        if entry.model in OFFERED_MODELS
    }
    if not found:
        # The server is running and answered — it simply holds none of the models this
        # advisor offers, which is a different fault from being unreachable and has its own
        # cure: pull one, or add what is already here to the list at the top of this file.
        return ProbeResult(
            available=False,
            detail=(
                f"{base_url} is running but has pulled none of "
                f"{', '.join(OFFERED_MODELS)}"
            ),
        )
    # Ordered by preference rather than by whatever order the server listed them in, so the
    # model at the top of the chooser is the one this advisor would pick for itself.
    return ProbeResult(
        available=True,
        models=[found[name] for name in OFFERED_MODELS if name in found],
    )


def _investigation_messages(
    messages: list[InvestigationMessage],
) -> list[Mapping[str, object]]:
    """The history as Ollama's chat endpoint wants it, calls and results included.

    Three shapes, and only two of them need translating. A plain chat message already is what
    this API takes, role and content and nothing else. An assistant turn becomes that same
    message with its calls attached under `tool_calls`, in the order they were made, because
    a server given results without the calls they answer has no way to pair them. A result is
    its own `tool` message, naming the tool that produced it.

    The name on a result is what this vendor asks for in place of a call id, and it does not
    make the pairing: two calls of one tool in a turn are told apart by their order and by
    nothing else, exactly as they were sent.
    """

    translated: list[Mapping[str, object]] = []
    for message in messages:
        if isinstance(message, AssistantToolTurn):
            translated.append(
                {
                    "role": "assistant",
                    "content": message.text,
                    "tool_calls": [
                        {
                            "function": {
                                "name": call.name,
                                # Already parsed on the way in — this client hands over a
                                # mapping rather than the JSON string some vendors send —
                                # so the arguments go back the way they arrived.
                                "arguments": dict(call.arguments),
                            }
                        }
                        for call in message.calls
                    ],
                }
            )
            continue
        if isinstance(message, ToolResultTurn):
            translated.append(
                {
                    "role": "tool",
                    "content": message.content,
                    "tool_name": message.call_name,
                }
            )
            continue
        translated.append(message)
    return translated


class OllamaChatTransport:
    """Encodes one already-assembled request for the Ollama chat endpoint."""

    provider_label = "Ollama"

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        if not config.base_url:
            raise ProviderError("The ollama provider requires a base_url")
        self._client = Client(host=config.base_url, timeout=config.timeout_seconds)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        del task
        client = self._client
        try:
            # `format` carries the full JSON Schema, not the generic "json" flag: that
            # constrains generation to the exact shape rather than merely to valid JSON,
            # which is what makes enumerated handles and dispositions unrepresentable.
            response = _with_retry(
                lambda: client.chat(
                    model=self._config.model,
                    messages=messages,
                    format=dict(schema),
                    options=self._options(temperature),
                    think=think,
                )
            )
            content = response.message.content
            if not isinstance(content, str):
                raise TypeError("Ollama response content is not text")
            return content
        except _REQUEST_FAILURES as error:
            raise _as_provider_error(error) from error

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> Iterator[str]:
        """The same request with `stream=True`, which the client already yields chunk by chunk.

        Nothing here reassembles or re-times anything: the library returns an iterator of
        chat responses, and this hands their text on in order. `format` still carries the whole
        schema, so what may be generated is exactly what a non-streamed call could produce —
        only when it arrives differs, and the concatenated text is validated as one document
        above this boundary.

        No retry, unlike `complete`. A stream that failed part-way has already shown text, and
        a second attempt would repeat it.
        """

        del task
        try:
            for part in self._client.chat(
                model=self._config.model,
                messages=messages,
                format=dict(schema),
                options=self._options(temperature),
                think=think,
                stream=True,
            ):
                if part.message.content:
                    yield part.message.content
        except _REQUEST_FAILURES as error:
            raise _as_provider_error(error) from error

    def complete_with_tools(
        self,
        messages: list[InvestigationMessage],
        *,
        tools: Sequence[ToolSpec],
        require_call: bool,
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> ToolExchange:
        """One turn of an investigation: the history, the tools, and what came back.

        Everything vendor-shaped about this request is shared with `complete` — the same
        retry policy, the same error mapping, the same options — and what differs is stated
        rather than inherited. There is no `format`, because an investigation turn is prose
        and calls rather than a document with a grammar; the schema-constrained call that
        composes the questions happens afterwards and is untouched by this.

        `require_call` is accepted and cannot be honoured. `/api/chat` has no counterpart to
        Gemini's must-call mode — the request carries tools and nothing that says the reply
        has to use them — so on this vendor the forced first look degrades to what the stage
        prompt already asks for. Simulating it by refusing a reply with no calls was
        considered and rejected: that turns a model's honest "nothing here needs checking"
        into a failed turn, and the loop above reads a failed turn as an abandoned
        investigation.
        """

        del require_call
        client = self._client
        try:
            response = _with_retry(
                lambda: client.chat(
                    model=self._config.model,
                    messages=_investigation_messages(messages),
                    tools=[
                        {
                            "type": "function",
                            "function": {
                                "name": spec.name,
                                "description": spec.description,
                                # Passed through as JSON Schema, which is as far as it
                                # travels: the client validates every tool into its own
                                # typed `Tool` model, whose parameter shape is a subset of
                                # the dialect — `minimum` and `additionalProperties` are
                                # dropped on the way to the wire. Nothing enforceable is
                                # lost, because a tool's arguments are checked by the
                                # investigator that runs the call and answered in text the
                                # model reads, never by the schema.
                                "parameters": dict(spec.parameters),
                            },
                        }
                        for spec in tools
                    ],
                    options=self._options(temperature),
                    think=think,
                )
            )
        except _REQUEST_FAILURES as error:
            raise _as_provider_error(error) from error
        message = response.message
        calls = tuple(
            ToolCall(name=item.function.name, arguments=dict(item.function.arguments))
            for item in message.tool_calls or ()
        )
        # `content` only. Ollama reports reasoning in its own `thinking` field, so the rule
        # the Gemini transport enforces by skipping thought parts holds here by not reading
        # that field: the model's private reasoning is not addressed to the stage that reads
        # this, and carried through it would be rendered into the transcript as though it
        # were a finding about the repository.
        text = (message.content or "").strip()
        if not text and not calls:
            raise ProviderError(
                f"Ollama returned neither text nor a tool call for {task.value}"
            )
        # No `vendor_state`. Ollama's protocol carries nothing private back with a call —
        # there is no signature to replay — so a turn rebuilt from its name and arguments is
        # the whole of what the server sent.
        return ToolExchange(text=text, calls=calls)

    def _options(self, temperature: float | None) -> dict[str, object]:
        """The generation options both calls send, derived from the configured window."""

        options: dict[str, object] = {
            "num_ctx": self._config.context_window_tokens,
            "num_predict": self._config.max_output_tokens,
        }
        if temperature is not None:
            options["temperature"] = temperature
        return options


class OllamaReasoningProvider(StructuredReasoningProvider):
    def __init__(self, config: ReasoningModelConfig) -> None:
        super().__init__(config, OllamaChatTransport(config))


#: How this build reaches a local Ollama server, stated once and read by the composition
#: root.
#:
#: The endpoint is overridable from the environment because it is the one field here a
#: deployment genuinely varies: the loopback default is right for the machine the models are
#: pulled on and wrong for a server reaching one over a network.
DESCRIPTOR: Final = ProviderDescriptor(
    name=PROVIDER_NAME,
    build=OllamaReasoningProvider,
    probe=probe_ollama,
    defaults=ProviderDefaults(
        base_url="http://127.0.0.1:11434",
        base_url_env="ARCHCOMPASS_OLLAMA_URL",
    ),
)


#: `ChatTransport` is already checked by handing this to `StructuredReasoningProvider` above.
#: `StreamingChatTransport` is not: it is reached by `isinstance`, which compares method names
#: alone, and a transport is held as a `ChatTransport` everywhere else. This states the
#: signature so `stream` cannot drift from what the streaming path calls.
_conforms: type[StreamingChatTransport] = OllamaChatTransport

#: And the same statement for the tool-calling capability, which is reached the same way and
#: for which drift would be quieter still: the loop treats a failed turn as an investigation
#: to abandon, so a `complete_with_tools` that no longer matched what the loop calls would
#: show up as stages that quietly stopped looking things up.
_conforms_with_tools: type[ToolCallingChatTransport] = OllamaChatTransport
