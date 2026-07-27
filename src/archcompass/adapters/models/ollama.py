"""Ollama transport: schema-constrained structured output from a local Ollama server.

Only the vendor-specific half lives here. Which stage runs, what it may reference, and
what shape its answer must take are decided in `structured`, above this boundary.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator, Mapping
from typing import Final

import httpx
from ollama import Client, ResponseError
from pydantic import BaseModel

from archcompass.adapters.models.structured import (
    ChatMessage,
    StreamingChatTransport,
    StructuredReasoningProvider,
    ThinkLevel,
    timeout_seconds,
)
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.errors import ProviderError
from archcompass.ports.reasoning import ReasoningTask

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


class EmbeddingResponse(BaseModel):
    embeddings: list[list[float]]


class OllamaEmbeddingProvider:
    def __init__(self, config: EmbeddingModelConfig) -> None:
        self._config = config
        self._client = Client(host=config.base_url, timeout=config.timeout_seconds)

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self._config.provider, self._config.model, self._config.dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            response = _with_retry(
                lambda: self._client.embed(model=self._config.model, input=texts)
            )
            payload = EmbeddingResponse(
                embeddings=[list(vector) for vector in response.embeddings]
            )
            if len(payload.embeddings) != len(texts):
                raise ValueError(
                    f"Ollama returned {len(payload.embeddings)} embeddings for {len(texts)} inputs"
                )
            for index, vector in enumerate(payload.embeddings):
                if len(vector) != self._config.dimensions:
                    raise ValueError(
                        f"Ollama embedding {index} has {len(vector)} dimensions; "
                        f"expected {self._config.dimensions}"
                    )
                if any(not math.isfinite(value) for value in vector):
                    raise ValueError(f"Ollama embedding {index} contains a non-finite value")
            return payload.embeddings
        except (
            httpx.HTTPError,
            ResponseError,
            ConnectionError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise ProviderError(f"Ollama embedding request failed: {error}") from error


class OllamaChatTransport:
    """Encodes one already-assembled request for the Ollama chat endpoint."""

    provider_label = "Ollama"

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config
        if not config.base_url:
            raise ProviderError("The ollama provider requires base_url in models.yaml")
        # The client fixes its timeout at construction, so a timeout class is a client.
        # Two is the whole set, and building them once keeps connection reuse.
        self._clients: dict[bool, Client] = {
            is_fast: Client(
                host=config.base_url,
                timeout=timeout_seconds(config, is_fast=is_fast),
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
        del task  # The budget class is the only stage property this transport needs.
        client = self._clients[is_fast]
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
        is_fast: bool,
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
            for part in self._clients[is_fast].chat(
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


#: `ChatTransport` is already checked by handing this to `StructuredReasoningProvider` above.
#: `StreamingChatTransport` is not: it is reached by `isinstance`, which compares method names
#: alone, and a transport is held as a `ChatTransport` everywhere else. This states the
#: signature so `stream` cannot drift from what the streaming path calls.
_conforms: type[StreamingChatTransport] = OllamaChatTransport
