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
from archcompass.ports.model_catalog import ProviderDefaults
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


def _probe_defaults(**overrides: object) -> ProviderDefaults:
    """What a probe is handed: an endpoint, and nothing about any model."""

    values: dict[str, object] = {"base_url": "http://ollama.test/"}
    values.update(overrides)
    return ProviderDefaults(**values)  # pyright: ignore[reportArgumentType]


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


@pytest.mark.parametrize(
    ("configured", "sent"),
    [(True, True), (False, False), (None, None)],
)
def test_the_configured_thinking_setting_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
    configured: bool | None,
    sent: bool | None,
) -> None:
    """`thinking: true` has to arrive as a request that requires thinking.

    On the wire rather than on the transport's argument, because that is where the same bug
    shipped in the Google adapter and only the body showed it. Ollama needs no translation —
    `think` is its own parameter and takes the same three values — which is exactly why this
    is worth pinning: a transport that has nothing to do is one whose job is easy to lose.
    """

    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _chat_response(verdict_json(bearings=2))

    _patch_transport(monkeypatch, post)

    _judge(OllamaReasoningProvider(_reasoning_config(thinking=configured)))

    body = captured["json"]
    assert isinstance(body, dict)
    # `.get`, because the client omits the field entirely rather than sending a null — and
    # over this API an absent `think` is precisely what "leave it to the model" means.
    assert body.get("think") is sent


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


def test_the_probe_offers_only_the_models_this_advisor_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`/api/tags` says what is on disk and nothing about what any of it can do.

    An embedding model lists exactly like a reasoning one, so the set worth judging with is
    named rather than inferred. Ordered by preference, not by however the server listed them.
    """

    def tags(url: str, **_: object) -> httpx.Response:
        assert url.endswith("/api/tags")
        return _http_response(
            {
                "models": [
                    {"model": "embeddinggemma:latest", "details": {"parameter_size": "300M"}},
                    {"model": "gemma4:12b", "details": {"parameter_size": "12B"}},
                    {
                        "model": "gemma4:26b",
                        "details": {"parameter_size": "26B", "family": "gemma4"},
                    },
                    {"model": "some-experiment:latest", "details": {"parameter_size": "8B"}},
                ]
            }
        )

    _patch_transport(monkeypatch, tags)
    result = ollama_adapters.probe_ollama(_probe_defaults())

    assert result.available
    assert result.detail == ""
    assert [(model.name, model.label) for model in result.models] == [
        ("gemma4:26b", "26B"),
        ("gemma4:12b", "12B"),
    ]


def test_a_running_server_holding_none_of_them_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Different from unreachable, and with its own cure: pull one, or widen the list."""

    _patch_transport(
        monkeypatch,
        lambda _url, **_kwargs: _http_response(
            {"models": [{"model": "embeddinggemma:latest", "details": {}}]}
        ),
    )
    result = ollama_adapters.probe_ollama(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert "gemma4:26b" in result.detail


def test_a_server_that_is_not_running_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailability is the answer to the question, not a failure to answer it.

    A raised probe would take down the listing of every other provider with it, which is
    the one thing a chooser cannot afford: the reader is there precisely because something
    is wrong, and the row naming what is wrong is the useful one.
    """

    def refused(_url: str, **_kwargs: object) -> httpx.Response:
        raise ConnectionError("connection refused")

    _patch_transport(monkeypatch, refused)
    result = ollama_adapters.probe_ollama(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert result.detail == "nothing is listening at http://ollama.test/"


def test_the_probe_does_not_wait_out_the_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """360s is right for a judgement and absurd for a dropdown.

    This is what the module-level shape buys: a probe reached through the transport would
    inherit the transport's client and could not lower its own budget.
    """

    seen: list[object] = []

    def request(client: httpx.Client, _method: str, _url: str, **_: object) -> httpx.Response:
        # The Ollama client fixes its budget on the HTTP client rather than per request,
        # so that is where the probe's own number has to show up.
        seen.append(client.timeout.connect)
        return _http_response({"models": []})

    monkeypatch.setattr(httpx.Client, "request", request)
    ollama_adapters.probe_ollama(_probe_defaults(timeout_seconds=360))

    assert seen == [ollama_adapters.PROBE_TIMEOUT_SECONDS]


def test_a_provider_without_a_base_url_says_so_instead_of_probing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The transport raises for this; the probe reports it, because the picker must render it."""

    def never(_url: str, **_kwargs: object) -> httpx.Response:
        raise AssertionError("a provider with no base_url has nothing to ask")

    _patch_transport(monkeypatch, never)
    result = ollama_adapters.probe_ollama(_probe_defaults(base_url=None))

    assert not result.available
    assert "base_url" in result.detail
