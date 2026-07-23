from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from archcompass.adapters.models.ollama import (
    AlternativeList,
    OllamaEmbeddingProvider,
    OllamaReasoningProvider,
    ScenarioList,
)
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.consultation import GlobalContext
from archcompass.domain.errors import ModelOutputValidationError, ProviderError


def _embedding_config(*, dimensions: int = 3) -> EmbeddingModelConfig:
    return EmbeddingModelConfig(
        provider="ollama",
        model="embedding-test",
        base_url="http://ollama.test/",
        dimensions=dimensions,
        timeout_seconds=5,
    )


def _reasoning_config() -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="ollama",
        model="reasoning-test",
        base_url="http://ollama.test/",
        temperature=0,
        timeout_seconds=10,
    )


def _context() -> GlobalContext:
    return GlobalContext(
        case_id="case-test",
        revision=1,
        title="Provider ownership",
        problem="Provider-specific capabilities leak into orchestration.",
        desired_outcome="Keep orchestration provider-neutral.",
        goals=["Clear ownership"],
        constraints=["Local-first"],
        future_changes=["A second provider"],
        non_goals=["A universal plugin platform"],
        confirmed_facts=["One provider exists"],
        assumptions=[],
    )


def _http_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "http://ollama.test/api")
    if isinstance(payload, bytes):
        return httpx.Response(status_code, content=payload, request=request)
    return httpx.Response(status_code, json=payload, request=request)


def test_embedding_provider_sends_batch_and_validates_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _http_response({"embeddings": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]})

    monkeypatch.setattr(httpx, "post", post)
    provider = OllamaEmbeddingProvider(_embedding_config())

    vectors = provider.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert captured["url"] == "http://ollama.test/api/embed"
    assert captured["json"] == {
        "model": "embedding-test",
        "input": ["first", "second"],
    }
    assert captured["timeout"] == 5


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"embeddings": [[1.0, 0.0, 0.0]]}, "1 embeddings for 2 inputs"),
        (
            {"embeddings": [[1.0, 0.0], [0.0, 1.0, 0.0]]},
            "embedding 0 has 2 dimensions",
        ),
        (
            b'{"embeddings":[[NaN,0.0,0.0],[0.0,1.0,0.0]]}',
            "embedding 0 contains a non-finite value",
        ),
    ],
)
def test_embedding_provider_rejects_contract_violations(
    monkeypatch: pytest.MonkeyPatch,
    payload: object,
    message: str,
) -> None:
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _http_response(payload))
    provider = OllamaEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match=message):
        provider.embed(["first", "second"])


def test_reasoning_provider_sends_schema_and_parses_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    content = json.dumps(
        [
            {
                "force_id": "force-test",
                "title": "Provider ownership",
                "description": "Changing capability knowledge needs one owner.",
                "importance": "high",
            }
        ]
    )

    def post(url: str, **kwargs: object) -> httpx.Response:
        captured.update(url=url, **kwargs)
        return _http_response({"message": {"content": content}})

    monkeypatch.setattr(httpx, "post", post)
    provider = OllamaReasoningProvider(_reasoning_config())

    forces = provider.discover_design_forces(_context())

    assert [force.title for force in forces] == ["Provider ownership"]
    assert captured["url"] == "http://ollama.test/api/chat"
    request = captured["json"]
    assert isinstance(request, dict)
    assert request["model"] == "reasoning-test"
    assert request["stream"] is False
    assert isinstance(request["format"], dict)
    assert request["options"] == {"temperature": 0.0}


def test_reasoning_provider_distinguishes_invalid_model_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *args, **kwargs: _http_response({"message": {"content": "{}"}}),
    )
    provider = OllamaReasoningProvider(_reasoning_config())

    with pytest.raises(ModelOutputValidationError, match="invalid structured output"):
        provider.discover_design_forces(_context())


def test_scenario_contract_requires_at_least_one_evaluation() -> None:
    with pytest.raises(ValidationError):
        ScenarioList.model_validate([])


def test_alternative_contract_requires_multiple_candidates() -> None:
    with pytest.raises(ValidationError):
        AlternativeList.model_validate([])
    with pytest.raises(ValidationError):
        AlternativeList.model_validate(
            [{"id": "alt-test", "title": "Only option", "summary": "Not a comparison"}]
        )


@pytest.mark.parametrize(
    "provider_factory",
    [
        lambda: OllamaEmbeddingProvider(_embedding_config()),
        lambda: OllamaReasoningProvider(_reasoning_config()),
    ],
)
def test_ollama_providers_wrap_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
    provider_factory: Callable[[], OllamaEmbeddingProvider | OllamaReasoningProvider],
) -> None:
    def post(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", post)
    provider = provider_factory()

    with pytest.raises(ProviderError, match=r"Ollama .* request failed: offline"):
        if isinstance(provider, OllamaEmbeddingProvider):
            provider.embed(["test"])
        else:
            provider.discover_design_forces(_context())
