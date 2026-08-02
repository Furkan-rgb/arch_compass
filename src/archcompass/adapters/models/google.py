"""Google AI Studio transport: Gemini structured output over the `google-genai` SDK.

Only the vendor-specific half lives here. Which stage runs, what it may reference, and
what shape its answer must take are decided in `structured`, above this boundary.

Two properties of this API shape the code below and have no counterpart in a local
Ollama server:

* Thinking tokens are drawn from `max_output_tokens`, so a request can end in
  `MAX_TOKENS` having produced only reasoning and no JSON. That is detected and named
  rather than surfaced as unparseable output.
* The free tier rejects with 429 once a per-minute or per-day quota is spent, which is
  worth retrying with backoff in the first case and not in the second. Both arrive as
  the same status, so the retry cap keeps a spent daily quota from stalling a run.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Final, cast

import httpx
from google import genai
from google.genai import errors, types

from archcompass.adapters.models.structured import (
    ChatMessage,
    StructuredReasoningProvider,
    ThinkLevel,
)
from archcompass.configuration import (
    ReasoningModelConfig,
    resolve_api_key,
)
from archcompass.domain.errors import ConfigurationError, ProviderError
from archcompass.domain.model_catalog import AvailableModel, ProbeResult
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.ports.reasoning import ReasoningTask

# ─────────────────────────────────────────────────────────────────────────────────────────
# The Gemini models this advisor offers, most preferred first. Edit this list to change what
# the model chooser puts in front of a reader; nothing else in this file needs touching.
#
# Named rather than filtered, because no property of a listing separates the models worth
# judging with from the rest. One key reaches forty-two: text-to-speech, image generation,
# music, an embedding model, half a dozen preview variants and several superseded
# generations of flash. All but one report `generateContent`, so a capability filter — which
# is what stood here — let almost every one of them through. Offering forty choices where
# one is defensible is not a chooser, it is a quiz.
#
# The cost is that a new Gemini release needs a line here. That is the intended cost: which
# model a review runs against decides what it costs, how long it takes and how good the
# judgement is, so it is a decision to make deliberately rather than to inherit from
# whatever the vendor shipped this week.
#
# Three things deliberately absent:
#
# * The `-latest` aliases. They would never need editing, which is exactly the problem: a
#   review records `reasoning_model` as provenance, and an alias makes two reviews claim the
#   same model while having run different ones. A judgement someone has to trust cannot have
#   a moving name on it.
# * The 3.x previews, newer than `gemini-2.5-pro` though they are. Previews get withdrawn,
#   and a withdrawn name here is a permanently unavailable row until somebody notices.
# * The whole 2.0 line, which reports no thinking support and caps output at 8192.
#
# Which models are offered stays an authored decision; whether each of them can think is not.
# `models.list` answers that itself, in a `thinking` field on every entry, and the probe pays
# for that listing already — so a model's modes are read from the same response that found
# it rather than declared beside its name and left to drift. Declaring them here got
# `gemini-3.5-flash-lite` wrong: the listing reports it as thinking.
#
# One edge is unverified: a model reported as thinking that cannot be talked *down*. Whether
# `gemini-2.5-pro` accepts `MINIMAL` is unmeasured — the quota was spent before the attempt
# finished — so it is offered both ways on the provider's word. The philosophy already
# covers it: if the provider refuses, the refusal arrives named at run time and is recorded
# against the selection, which is where every other thing a listing cannot promise shows up.
# ─────────────────────────────────────────────────────────────────────────────────────────
OFFERED_MODELS: Final[tuple[str, ...]] = (
    #: The default: newest flash, 1M in / 65k out. Reasons by default and answers well
    #: without it.
    "gemini-3.6-flash",
    #: The only pro that is not a preview — there is no 3.6 pro — for a harder judgement.
    "gemini-2.5-pro",
    #: Somewhere to go when the free-tier quota is spent, which this adapter's whole 429
    #: backoff exists for and which the chip now reports against the selection.
    "gemini-3.5-flash-lite",
)

PROVIDER_NAME: Final = "google"

#: Higher than the Ollama transport's cap because the failure being waited out is
#: different in kind: a free-tier per-minute quota, which recovers on a clock rather
#: than on chance.
_MAX_TRANSPORT_ATTEMPTS: Final = 6
_BACKOFF_BASE_SECONDS: Final = 0.5
#: A rate limit is waited out on a different scale from a blip. The free tier meters per
#: minute, so a wait has to be able to reach that long; starting at half a second merely
#: spends every attempt inside the window that is already known to be closed. The
#: server's own `RetryInfo` is used as a floor rather than as the answer, because it
#: reports when the next single unit of quota frees up - observed as 232ms while a
#: 50-input batch still could not be served.
_RATE_LIMIT_BACKOFF_BASE_SECONDS: Final = 8.0
#: Bounds how long one attempt may stall, so an exhausted per-day quota fails the run
#: with the server's own message instead of parking it for hours.
_MAX_RETRY_DELAY_SECONDS: Final = 70.0
_TRANSIENT_TRANSPORT_ERRORS: Final = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
    httpx.ProxyError,
)
#: 429 is included because the free tier spends its per-minute quota routinely and a
#: short wait clears it. A per-day quota returns the same status and will exhaust the
#: attempt cap instead, which is the intended outcome: fail with the server's own
#: message rather than block the run.
_TRANSIENT_STATUS_CODES: Final = frozenset({408, 429, 500, 502, 503, 504})

_THINKING_LEVELS: Final[dict[str, types.ThinkingLevel]] = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}


def _is_transient(error: Exception) -> bool:
    """Whether a later identical request might survive this failure.

    An `APIError` carries the HTTP status, so a 400 for a malformed schema is separated
    from a 503 for an overloaded model. Anything the SDK raises before a response
    exists arrives as an httpx error or a builtin `ConnectionError`.
    """

    if isinstance(error, errors.APIError):
        return error.code in _TRANSIENT_STATUS_CODES
    return isinstance(error, (ConnectionError, *_TRANSIENT_TRANSPORT_ERRORS))


def _for_gemini(value: object) -> object:
    """Rewrite a JSON Schema into the dialect `response_json_schema` accepts.

    Gemini takes the schema almost verbatim - `$defs`, `$ref`, enums, `minLength` and
    even `maxItems: 0` all survive, which is what keeps the enumerated handles and
    evidence allowlists enforceable. Two keywords do not, and both come from the same
    place: a pydantic discriminated union emits OpenAPI's `discriminator` alongside
    `oneOf`, and the atlas query plan is built from one. That schema is rejected with
    HTTP 400 while every other stage's is accepted.

    `oneOf` becomes `anyOf` and `discriminator` is dropped. The result is strictly more
    permissive - `anyOf` allows a value matching several variants where `oneOf` demands
    exactly one - but not meaningfully so here: every variant pins `kind` to its own
    disjoint values and forbids extra properties, so no object can satisfy two. The
    union is in any case re-imposed after the response arrives, when pydantic validates
    it against the real discriminated model, so a violation cannot reach the domain.
    """

    if isinstance(value, Mapping):
        source = cast(Mapping[str, object], value)
        rewritten: dict[str, object] = {}
        for key, item in source.items():
            if key == "discriminator":
                continue
            rewritten["anyOf" if key == "oneOf" else key] = _for_gemini(item)
        return rewritten
    if isinstance(value, list):
        return [_for_gemini(item) for item in cast(list[object], value)]
    return value


def _is_rate_limited(error: Exception) -> bool:
    return isinstance(error, errors.APIError) and error.code == 429


def _retry_delay(error: Exception) -> float | None:
    """The wait the server itself asked for, in seconds, if it named one.

    A quota response carries a `google.rpc.RetryInfo` saying exactly when the window
    reopens. Guessing instead is wrong in both directions: a doubling backoff starting
    at half a second retries long before an eight-second window has passed, burning
    attempts, while a fixed long sleep would stall failures that need no wait at all.
    """

    if not isinstance(error, errors.APIError):
        return None
    # `details` is the decoded response body, so every step down it is untyped and has
    # to be narrowed rather than assumed.
    details = cast("object", error.details)
    if not isinstance(details, Mapping):
        return None
    inner: object = cast(Mapping[str, object], details).get("error")
    if not isinstance(inner, Mapping):
        return None
    entries: object = cast(Mapping[str, object], inner).get("details")
    if not isinstance(entries, list):
        return None
    for entry in cast(list[object], entries):
        if not isinstance(entry, Mapping):
            continue
        item = cast(Mapping[str, object], entry)
        if not str(item.get("@type", "")).endswith("RetryInfo"):
            continue
        raw = str(item.get("retryDelay", "")).removesuffix("s")
        try:
            return float(raw)
        except ValueError:
            return None
    return None


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
            base = (
                _RATE_LIMIT_BACKOFF_BASE_SECONDS
                if _is_rate_limited(error)
                else _BACKOFF_BASE_SECONDS
            )
            requested = _retry_delay(error) or 0.0
            delay = min(
                max(requested, base * (2 ** (attempt - 1))),
                _MAX_RETRY_DELAY_SECONDS,
            )
        time.sleep(delay)
    raise ProviderError(  # pragma: no cover - the loop always returns or raises
        f"Google AI Studio request failed after {_MAX_TRANSPORT_ATTEMPTS} attempts"
    )


def _client(api_key: str, base_url: str | None, timeout: float) -> genai.Client:
    """A client whose timeout is fixed at construction, as the Ollama clients are.

    `HttpOptions.timeout` is milliseconds; the rest of this codebase counts seconds.
    """

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            base_url=base_url or None,
            timeout=int(timeout * 1000),
        ),
    )


def _describe(error: errors.APIError) -> str:
    detail = (error.message or "").strip()
    if len(detail) > 1000:
        detail = detail[:999].rstrip() + "…"
    suffix = f": {detail}" if detail else ""
    return f"HTTP {error.code}{suffix}"


#: See the Ollama adapter's constant of the same name: a probe answers a dropdown, and the
#: configured timeout answers a judgement.
PROBE_TIMEOUT_SECONDS: Final = 2.0
#: One page, one request. `models.list` returns a `Pager` that fetches further pages as it
#: is iterated, and a probe that walks a paginated list is not a two-second probe. AI Studio
#: offers well under this many base models, so the first page is all of them.
_PROBE_PAGE_SIZE: Final = 200
#: What a failed listing may raise once the SDK has done its own mapping. `errors.APIError`
#: is handled separately, because it is the one that carries a message worth repeating.
_PROBE_FAILURES: Final = (httpx.HTTPError, ConnectionError, KeyError, TypeError, ValueError)


def _offered(model: types.Model) -> AvailableModel | None:
    """One listed model, where it is one this advisor offers.

    `thinking` is the provider's own answer to whether reasoning can be asked for, and it
    decides the modes: a model that can think is offered both ways, and one that cannot is
    offered as the single row that sends no thinking instruction at all — not as `False`,
    because forbidding reasoning is a request, and there is nothing here to ask.
    """

    name = (model.name or "").removeprefix("models/")
    if name not in OFFERED_MODELS:
        return None
    return AvailableModel(
        name=name,
        label=model.display_name or "",
        input_token_limit=model.input_token_limit,
        output_token_limit=model.output_token_limit,
        thinking_modes=(True, False) if model.thinking else (None,),
    )


def probe_google(defaults: ProviderDefaults) -> ProbeResult:
    """Whether the key works and which models it reaches, in one request.

    `models.list` is the whole check: it authenticates and enumerates in the same breath, so
    a missing or rejected key — the single most likely reason this provider is unusable — is
    reported here as a value instead of raising at the first boundary of a review.

    What it cannot report is how much free-tier quota is left: a key with a spent daily quota
    probes as available and fails on the next request, which is why a failure is recorded
    against the selection rather than inferred from a probe.
    """

    try:
        api_key = resolve_api_key(defaults.api_key_env, provider=PROVIDER_NAME)
    except ConfigurationError as error:
        return ProbeResult(available=False, detail=str(error))
    # Held in a name for the length of the call, deliberately. Written as one chained
    # expression, the client is unreferenced the moment `.models` is read, and CPython
    # finalizes it — closing the HTTP connection — before `list` gets to use it. The request
    # then fails with "Cannot send a request, as the client has been closed", which says
    # nothing about a probe and appears only against a real server.
    client = _client(api_key, defaults.resolved_base_url(), PROBE_TIMEOUT_SECONDS)
    try:
        page = client.models.list(
            # `query_base` already defaults to true, and is passed anyway: false lists
            # tuned models instead, so a change of default would silently empty this.
            config=types.ListModelsConfig(query_base=True, page_size=_PROBE_PAGE_SIZE)
        ).page
    except errors.APIError as error:
        return ProbeResult(available=False, detail=_describe(error))
    except _PROBE_FAILURES as error:
        return ProbeResult(available=False, detail=str(error))
    found = {model.name: model for model in (_offered(item) for item in page) if model}
    if not found:
        # The key works and the request succeeded — this provider simply reaches none of the
        # models this advisor offers, which is a different fault from being unreachable and
        # has a different cure. Reported as unavailable because that is what it is here: an
        # empty group under a heading saying "google" explains nothing at all.
        return ProbeResult(
            available=False,
            detail=(
                f"this key reaches {len(page)} models, none of them "
                f"{' or '.join(OFFERED_MODELS)}"
            ),
        )
    # Ordered by preference rather than by whatever order the listing arrived in, so the
    # model at the top of the chooser is the one this advisor would pick for itself.
    return ProbeResult(
        available=True,
        models=[found[name] for name in OFFERED_MODELS if name in found],
    )


class GoogleChatTransport:
    """Encodes one already-assembled request for the Gemini `generateContent` API."""

    provider_label = "Google AI Studio"

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        api_key = resolve_api_key(config.api_key_env, provider=PROVIDER_NAME)
        self._client = _client(api_key, config.base_url, config.timeout_seconds)

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        think: ThinkLevel,
        temperature: float | None,
    ) -> str:
        system_instruction, contents = _split_system_prompt(messages)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction or None,
            # `response_json_schema` takes the JSON Schema as written, including `$defs`
            # and `$ref`. The narrower `response_schema` would force the enumerated
            # handles and evidence allowlists through a lossy OpenAPI subset, which is
            # exactly the constraint that must survive.
            response_mime_type="application/json",
            response_json_schema=_for_gemini(dict(schema)),
            max_output_tokens=self._config.max_output_tokens,
            temperature=temperature,
            thinking_config=_thinking_config(think),
        )
        client = self._client
        try:
            response = _with_retry(
                lambda: client.models.generate_content(
                    model=self._config.model,
                    contents=contents,  # pyright: ignore[reportArgumentType]
                    config=config,
                )
            )
            return _response_text(response, task=task, config=self._config)
        except errors.APIError as error:
            raise ProviderError(
                f"Google AI Studio reasoning request failed with {_describe(error)}"
            ) from error
        except (
            httpx.HTTPError,
            ConnectionError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProviderError(f"Google AI Studio reasoning request failed: {error}") from error


def _split_system_prompt(messages: list[ChatMessage]) -> tuple[str, list[types.Content]]:
    """Separate the system prompt, which Gemini takes as its own field, from the turns.

    A repair round replays the prior assistant turn, so the roles must survive the
    translation: Gemini names the assistant role `model`.
    """

    system_parts: list[str] = []
    contents: list[types.Content] = []
    for message in messages:
        role = message["role"]
        content = message["content"]
        if role == "system":
            system_parts.append(content)
            continue
        contents.append(
            types.Content(
                role="model" if role == "assistant" else "user",
                parts=[types.Part(text=content)],
            )
        )
    return "\n\n".join(system_parts), contents


def _thinking_config(think: ThinkLevel) -> types.ThinkingConfig | None:
    """Map the port's reasoning-effort control onto Gemini's `thinking_level`.

    `thinking_level` is used throughout rather than the older `thinking_budget=0`,
    because it is the spelling every currently reachable model accepts: probing this
    key found `gemini-flash-latest` and `gemini-3.6-flash` reject a zero budget with
    HTTP 400 while accepting `MINIMAL`, and no reachable model accepts the budget but
    not the level.

    `MINIMAL` rather than off is deliberate and is as far down as the 3-series goes:
    the stages that pass `think=False` want a short structured decision, and Gemini
    spends thinking tokens from the same allowance as the answer.

    `True` names a level rather than leaving the field out, and the difference is not
    academic. Sending nothing leaves the model's own default in place, and that default
    is not a property of the API — it is a property of the model. Measured against this
    key on one fixed prompt, `gemini-3.6-flash` spends 831 thinking tokens with the field
    absent and `gemini-3.5-flash-lite` spends none at all: the same configuration saying
    "reasoning is required" turned reasoning off on the smaller model. It showed up as a
    review that asked no questions — every verdict came back declaring it stood either
    way, which is the answer the judging prompt names as the ordinary one and the answer a
    model that is not thinking will take — and the run went straight to its summary.

    `MEDIUM` because it is what the absent field already meant on the model this
    configuration was written for: 861 thinking tokens against 831 on the same prompt. So
    the model that was reasoning goes on reasoning as it did, and the model that was not
    starts. A stage that wants less than the configuration asks for still names its own
    level and keeps it.
    """

    if think is False:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    if think is True:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MEDIUM)
    if isinstance(think, str):
        return types.ThinkingConfig(thinking_level=_THINKING_LEVELS[think])
    return None


def _response_text(
    response: types.GenerateContentResponse,
    *,
    task: ReasoningTask,
    config: ReasoningModelConfig,
) -> str:
    candidates: Sequence[types.Candidate] = response.candidates or []
    if not candidates:
        feedback = response.prompt_feedback
        reason = feedback.block_reason if feedback is not None else None
        raise ProviderError(
            f"Google AI Studio returned no candidate for {task.value}"
            + (f": the prompt was blocked ({reason})" if reason is not None else "")
        )
    finish_reason = candidates[0].finish_reason
    if finish_reason == types.FinishReason.MAX_TOKENS:
        # Thinking tokens are spent from the same allowance, so this is reachable with
        # a schema the model could otherwise satisfy. Name the knob that fixes it.
        raise ProviderError(
            f"Google AI Studio truncated the {task.value} response at "
            f"{config.max_output_tokens} output tokens. Gemini spends thinking tokens "
            "from that same allowance; choose the same model without thinking, or raise "
            "this provider's output budget."
        )
    if finish_reason is not None and finish_reason != types.FinishReason.STOP:
        raise ProviderError(
            f"Google AI Studio stopped the {task.value} response early ({finish_reason})"
        )
    text = response.text
    if not text:
        raise ProviderError(f"Google AI Studio returned an empty {task.value} response")
    return text


class GoogleReasoningProvider(StructuredReasoningProvider):
    def __init__(self, config: ReasoningModelConfig) -> None:
        super().__init__(config, GoogleChatTransport(config))


#: How this build reaches Google AI Studio, stated once and read by the composition root.
#:
#: No `base_url`: the SDK knows its own endpoint, and the only reason to override it is a
#: test that patches the transport instead.
DESCRIPTOR: Final = ProviderDescriptor(
    name=PROVIDER_NAME,
    build=GoogleReasoningProvider,
    probe=probe_google,
    defaults=ProviderDefaults(api_key_env="GOOGLE_API_KEY"),
)
