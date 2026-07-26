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

import math
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
    timeout_seconds,
)
from archcompass.configuration import (
    EmbeddingModelConfig,
    ReasoningModelConfig,
    resolve_api_key,
)
from archcompass.domain.errors import ProviderError
from archcompass.ports.reasoning import ReasoningTask

PROVIDER_NAME: Final = "google"

#: Higher than the Ollama transport's cap because the failure being waited out is
#: different in kind: a free-tier per-minute quota, which recovers on a clock rather
#: than on chance. Indexing the policy corpus spends that quota in a single call.
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

#: Requests are chunked because the policy corpus is larger than one call may carry.
#: 50 rather than the API's own ceiling because the free tier meters `embed_content`
#: per input rather than per call, at 100 per minute: a batch that spends the entire
#: window guarantees the next one is rejected, while a half-window batch leaves the
#: quota room to refill between calls.
_MAX_EMBEDDING_BATCH: Final = 50

#: One `embed` serves both indexing and querying, so the task type must be symmetric.
#: RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY are a matched asymmetric pair and would need
#: the port to say which side it is on.
_EMBEDDING_TASK_TYPE: Final = "SEMANTIC_SIMILARITY"

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


class GoogleEmbeddingProvider:
    def __init__(self, config: EmbeddingModelConfig) -> None:
        self._config = config
        self._client = _client(
            resolve_api_key(config.api_key_env, provider=PROVIDER_NAME),
            config.base_url,
            config.timeout_seconds,
        )

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self._config.provider, self._config.model, self._config.dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(texts), _MAX_EMBEDDING_BATCH):
                batch = texts[start : start + _MAX_EMBEDDING_BATCH]
                response = _with_retry(
                    lambda batch=batch: self._client.models.embed_content(  # type: ignore[misc]
                        model=self._config.model,
                        contents=batch,  # pyright: ignore[reportArgumentType]
                        config=types.EmbedContentConfig(
                            task_type=_EMBEDDING_TASK_TYPE,
                            output_dimensionality=self._config.dimensions,
                        ),
                    )
                )
                vectors.extend(self._vectors(response, expected=len(batch)))
            if len(vectors) != len(texts):
                raise ValueError(
                    f"Google AI Studio returned {len(vectors)} embeddings "
                    f"for {len(texts)} inputs"
                )
            return vectors
        except errors.APIError as error:
            raise ProviderError(
                f"Google AI Studio embedding request failed with {_describe(error)}"
            ) from error
        except (
            httpx.HTTPError,
            ConnectionError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProviderError(f"Google AI Studio embedding request failed: {error}") from error

    def _vectors(
        self,
        response: types.EmbedContentResponse,
        *,
        expected: int,
    ) -> list[list[float]]:
        embeddings = response.embeddings or []
        if len(embeddings) != expected:
            raise ValueError(
                f"Google AI Studio returned {len(embeddings)} embeddings for {expected} inputs"
            )
        resolved: list[list[float]] = []
        for index, embedding in enumerate(embeddings):
            values = list(embedding.values or [])
            if len(values) != self._config.dimensions:
                raise ValueError(
                    f"Google AI Studio embedding {index} has {len(values)} dimensions; "
                    f"expected {self._config.dimensions}"
                )
            if any(not math.isfinite(value) for value in values):
                raise ValueError(
                    f"Google AI Studio embedding {index} contains a non-finite value"
                )
            resolved.append(_unit(values, index=index))
        return resolved


def _unit(values: list[float], *, index: int) -> list[float]:
    """Scale a vector to unit length.

    Gemini truncates its native embedding to the requested dimensionality and does not
    renormalise, so a 768-dimension vector from `gemini-embedding-001` has a norm well
    below 1. The policy index is a sqlite-vec table queried by L2 distance, where the
    magnitude of a vector changes its ranking; normalising here makes L2 order the same
    as cosine order, which is what the retrieval code means by nearest.
    """

    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        raise ValueError(f"Google AI Studio embedding {index} is the zero vector")
    return [value / norm for value in values]


class GoogleChatTransport:
    """Encodes one already-assembled request for the Gemini `generateContent` API."""

    provider_label = "Google AI Studio"

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        api_key = resolve_api_key(config.api_key_env, provider=PROVIDER_NAME)
        # One client per timeout class, matching the Ollama transport: the timeout is
        # fixed when the client is built, and two classes are the whole set.
        self._clients: dict[bool, genai.Client] = {
            is_fast: _client(
                api_key,
                config.base_url,
                timeout_seconds(config, is_fast=is_fast),
            )
            for is_fast in (True, False)
        }

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        schema: Mapping[str, object],
        task: ReasoningTask,
        is_fast: bool,
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
        client = self._clients[is_fast]
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
    spends thinking tokens from the same allowance as the answer. `None` and `True`
    leave the model's own default in place.
    """

    if think is False:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
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
            "from that same allowance; raise max_output_tokens in models.yaml."
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
