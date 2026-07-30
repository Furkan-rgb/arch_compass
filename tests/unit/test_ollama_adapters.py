"""The Ollama transport, exercised through the stages that actually ship.

`judge_finding_candidate` drives most of these: its contract is the most demanding one —
a positional array whose length the response schema fixes — so a transport that carries it
faithfully carries the answer stage too.

`httpx.Client.request` is patched rather than a module-level function, which keeps the
library's own request building, response parsing and error mapping in the path. What is
under test is the transport as shipped, not a stub standing in for it.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from tests.reasoning_support import candidate, case, policies, verdict_json

from archcompass.adapters.models import ollama as ollama_adapters
from archcompass.adapters.models.ollama import OllamaReasoningProvider
from archcompass.adapters.models.structured import StreamingChatTransport
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import (
    ModelOutputValidationError,
    PromptBudgetExceededError,
    ProviderError,
)
from archcompass.ports.reasoning import ReasoningTask


def _reasoning_config(**overrides: object) -> ReasoningModelConfig:
    values: dict[str, object] = {
        "provider": "ollama",
        "model": "reasoning-test",
        "base_url": "http://ollama.test/",
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return ReasoningModelConfig.model_validate(values)


def _http_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://ollama.test/api")
    if isinstance(payload, bytes):
        return httpx.Response(status_code, content=payload, request=request)
    return httpx.Response(status_code, json=payload, request=request)


def _chat_response(content: str) -> httpx.Response:
    return _http_response({"message": {"role": "assistant", "content": content}})


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., httpx.Response],
) -> None:
    def request(_self: object, _method: str, url: str, **kwargs: object) -> httpx.Response:
        return handler(url, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", request)


def _judge(provider: OllamaReasoningProvider, *, count: int = 2) -> object:
    return provider.judge_finding_candidate(case(), candidate(), policies(count))


def test_a_reasoning_request_carries_the_narrowed_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`format` takes the whole JSON Schema, not the generic "json" flag.

    That is what makes the positional bearing array unrepresentable at the wrong length,
    rather than merely discouraged in prose.
    """

    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _chat_response(verdict_json(bearings=3))

    _patch_transport(monkeypatch, post)

    _judge(OllamaReasoningProvider(_reasoning_config()), count=3)

    body = captured["json"]
    assert isinstance(body, dict)
    schema = body["format"]
    assert schema["properties"]["policy_bearings"]["minItems"] == 3
    assert schema["properties"]["policy_bearings"]["maxItems"] == 3
    # Field order is the reasoning order, and the wire schema has to preserve it.
    assert list(schema["properties"]).index("rationale") < list(schema["properties"]).index(
        "verdict"
    )


def test_structured_output_is_parsed_into_the_domain_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(monkeypatch, lambda url, **_: _chat_response(verdict_json(material=True)))

    verdict = OllamaReasoningProvider(_reasoning_config()).judge_finding_candidate(
        case(), candidate(), policies(2)
    )

    assert verdict.material is True
    assert verdict.rationale


def test_an_invalid_reply_is_repaired_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    replies = [verdict_json(bearings=1), verdict_json(bearings=2)]
    calls: list[object] = []

    def post(url: str, **kwargs: object) -> httpx.Response:
        calls.append(url)
        return _chat_response(replies[len(calls) - 1])

    _patch_transport(monkeypatch, post)

    _judge(OllamaReasoningProvider(_reasoning_config()))

    assert len(calls) == 2


def test_a_reply_that_stays_invalid_is_distinguished_from_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong answer and an unreachable service need different responses from a caller."""

    _patch_transport(monkeypatch, lambda url, **_: _chat_response(verdict_json(bearings=1)))

    with pytest.raises(ModelOutputValidationError):
        _judge(OllamaReasoningProvider(_reasoning_config()))


def test_an_oversize_prompt_is_refused_before_it_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ollama truncates from the front, discarding the system prompt silently.

    The degraded reply then fails validation with no attributable cause, so the request
    has to be refused here with both sizes named.
    """

    sent: list[str] = []
    _patch_transport(monkeypatch, lambda url, **_: (sent.append(url), _chat_response("{}"))[1])
    provider = OllamaReasoningProvider(
        _reasoning_config(context_window_tokens=600, max_output_tokens=512)
    )

    with pytest.raises(PromptBudgetExceededError, match="judge_finding_candidate"):
        _judge(provider)
    assert sent == []


def test_the_budget_guard_counts_the_response_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The schema is part of the request; ignoring it under-counts every prompt."""

    _patch_transport(monkeypatch, lambda url, **_: _chat_response(verdict_json()))
    provider = OllamaReasoningProvider(
        _reasoning_config(context_window_tokens=2200, max_output_tokens=512)
    )

    with pytest.raises(PromptBudgetExceededError) as failure:
        _judge(provider)
    assert "schema" in str(failure.value).casefold()


def test_a_transport_error_is_wrapped_as_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(url: str, **_: object) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    _patch_transport(monkeypatch, fail)

    with pytest.raises(ProviderError, match="Ollama"):
        _judge(OllamaReasoningProvider(_reasoning_config()))


def test_a_retryable_status_is_retried_and_a_terminal_one_is_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ollama_adapters.time, "sleep", lambda _seconds: None)

    attempts: list[int] = []

    def flaky(url: str, **_: object) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            return _http_response({"error": "busy"}, status_code=503)
        return _chat_response(verdict_json())

    _patch_transport(monkeypatch, flaky)
    _judge(OllamaReasoningProvider(_reasoning_config()))
    assert len(attempts) == 3

    terminal: list[int] = []

    def rejected(url: str, **_: object) -> httpx.Response:
        terminal.append(1)
        return _http_response({"error": "no such model"}, status_code=404)

    _patch_transport(monkeypatch, rejected)
    with pytest.raises(ProviderError):
        _judge(OllamaReasoningProvider(_reasoning_config()))
    assert len(terminal) == 1, "a configuration fault must not be retried"


def _patch_stream(monkeypatch: pytest.MonkeyPatch, *lines: str) -> dict[str, object]:
    """Stand in for the streaming half of the client, keeping its own NDJSON reading.

    The client streams through `httpx.Client.stream` as a context manager and parses one JSON
    object per line out of `iter_lines()`, so patching there leaves its line splitting and
    error handling in the path — the same reason the non-streaming tests patch `request`.
    """

    captured: dict[str, object] = {}

    class _Stream:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def __enter__(self) -> httpx.Response:
            body = "".join(f"{line}\n" for line in lines).encode("utf-8")
            return _http_response(body)

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(
        httpx.Client, "stream", lambda _self, _method, url, **kwargs: _Stream(url=url, **kwargs)
    )
    return captured


def _chat_chunk(content: str) -> str:
    return json.dumps({"message": {"role": "assistant", "content": content}, "done": False})


def test_a_streamed_reply_arrives_in_fragments_under_the_same_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Streaming changes when the text arrives, not what may be generated.

    The schema still goes as `format`, so a reply that a non-streamed call could not have
    produced cannot be produced here either — which is what makes the accumulated text safe to
    validate as one document afterwards.
    """

    captured = _patch_stream(
        monkeypatch,
        _chat_chunk('{"answer": "The Formatter '),
        _chat_chunk('boundary holds."'),
        _chat_chunk(', "supported_by": [true, false]}'),
    )
    transport = ollama_adapters.OllamaChatTransport(_reasoning_config())

    fragments = list(
        transport.stream(
            [{"role": "user", "content": "Formatter?"}],
            schema={"type": "object", "properties": {"answer": {"type": "string"}}},
            task=ReasoningTask.ANSWER_REVIEW_QUESTION,
            is_fast=False,
            think=None,
            temperature=None,
        )
    )

    assert len(fragments) == 3
    assert "".join(fragments) == (
        '{"answer": "The Formatter boundary holds.", "supported_by": [true, false]}'
    )
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["stream"] is True
    assert body["format"] == {"type": "object", "properties": {"answer": {"type": "string"}}}


def test_the_transport_declares_the_streaming_capability() -> None:
    """The application asks with `isinstance`, so the shape has to actually satisfy it."""

    assert isinstance(
        ollama_adapters.OllamaChatTransport(_reasoning_config()), StreamingChatTransport
    )


def test_every_reasoning_task_has_a_declared_timeout_class() -> None:
    """A task absent from the timeout map would fall back silently to the wrong budget."""

    provider = OllamaReasoningProvider(
        _reasoning_config(fast_timeout_seconds=5, deep_timeout_seconds=90)
    )

    for task in ReasoningTask:
        assert provider._timeout_for(task) in {5, 90}
