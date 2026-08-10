"""Ollama's hosted models: the probe, the credential, and where the descriptor sits.

The request half is not retested here. The cloud descriptor builds the very transport the
local one does — same client, same retries, same error mapping — and that is covered in
`test_ollama_adapters`. What is new is everything around it: a key that has to reach the
wire, a probe that has to authenticate before it can enumerate, and a registry position the
chooser reads as "offered by default".

`httpx.Client.request` is patched rather than a module-level function, which keeps the
library's own request building, response parsing and error mapping in the path — the same
reason the local adapter's tests patch there.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from archcompass.adapters.models import ollama_cloud as cloud_adapters
from archcompass.adapters.models.ollama import OllamaChatTransport
from archcompass.bootstrap import enabled_providers
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.model_catalog import ProviderDefaults
from archcompass.ports.reasoning import ReasoningTask

_KEY_VARIABLE = "ARCHCOMPASS_TEST_OLLAMA_CLOUD_KEY"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A key in the variable this test names, and none in the one the SDK reads itself.

    `ollama.Client` picks `OLLAMA_API_KEY` out of the environment on its own when no
    `authorization` header is passed, so a machine that happens to have one exported would
    otherwise make the "no key configured" test pass for the wrong reason.
    """

    monkeypatch.setenv(_KEY_VARIABLE, "test-key")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)


def _probe_defaults(**overrides: object) -> ProviderDefaults:
    values: dict[str, object] = {
        "base_url": "https://ollama.test",
        "api_key_env": _KEY_VARIABLE,
    }
    values.update(overrides)
    return ProviderDefaults(**values)  # pyright: ignore[reportArgumentType]


def _reasoning_config(**overrides: object) -> ReasoningModelConfig:
    values: dict[str, object] = {
        "provider": cloud_adapters.PROVIDER_NAME,
        "model": "gpt-oss:20b",
        "base_url": "https://ollama.test",
        "api_key_env": _KEY_VARIABLE,
        "timeout_seconds": 10,
    }
    values.update(overrides)
    return ReasoningModelConfig.model_validate(values)


def _http_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://ollama.test/api")
    return httpx.Response(status_code, json=payload, request=request)


def _shown(*capabilities: str, parameter_size: str = "20B") -> httpx.Response:
    """What `/api/show` answers for a model the cloud serves.

    `model_info` is required by the client's own response model, so a fake omitting it fails
    validation rather than reporting no capability.
    """

    return _http_response(
        {
            "model_info": {},
            "details": {"parameter_size": parameter_size},
            "capabilities": list(capabilities),
        }
    )


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[..., httpx.Response],
) -> dict[str, object]:
    """Answer every request from `handler`, keeping the headers the client would have sent."""

    seen: dict[str, object] = {}

    def request(
        client: httpx.Client, _method: str, url: str, **kwargs: object
    ) -> httpx.Response:
        seen["headers"] = httpx.Headers(client.headers)
        seen["base_url"] = str(client.base_url)
        seen["timeout"] = client.timeout.connect
        return handler(url, **kwargs)

    monkeypatch.setattr(httpx.Client, "request", request)
    return seen


def test_a_missing_api_key_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The most likely reason this provider is unusable, and the picker has to render it.

    Named variable, named file: "unavailable" alone leaves a reader nothing to do.
    """

    monkeypatch.delenv(_KEY_VARIABLE, raising=False)

    def never(_url: str, **_kwargs: object) -> httpx.Response:
        raise AssertionError("a probe with no key has nothing to ask")

    _patch_transport(monkeypatch, never)
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert _KEY_VARIABLE in result.detail
    assert ".env" in result.detail


def test_the_probe_offers_the_models_this_advisor_names_with_the_modes_the_cloud_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One authenticated `/api/show` per offered model: it proves the key and reads the modes.

    A model that can think is offered both ways, exactly as on a local server, and the
    capability is asked for rather than declared here.
    """

    asked: list[object] = []

    def handler(url: str, **kwargs: object) -> httpx.Response:
        assert url.endswith("/api/show")
        body = kwargs["json"]
        assert isinstance(body, dict)
        asked.append(body["model"])
        return _shown("completion", "tools", "thinking")

    _patch_transport(monkeypatch, handler)
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert asked == list(cloud_adapters.OFFERED_MODELS)
    assert result.available
    assert [(model.name, model.label, model.thinking_modes) for model in result.models] == [
        ("gpt-oss:20b", "20B", (True, False))
    ]


def test_a_model_the_cloud_does_not_report_as_thinking_is_offered_the_one_way(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`False` would be a request Ollama rejects outright for a model without the capability."""

    _patch_transport(monkeypatch, lambda _url, **_kwargs: _shown("completion"))
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert [model.thinking_modes for model in result.models] == [(None,)]


def test_a_key_the_cloud_rejects_reports_the_status_rather_than_an_empty_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 401 is about the key, not about the model that happened to be asked for.

    Reported as the cure for a whole provider — the rest of the offered models would answer
    the same — rather than quietly narrowing the list to nothing.
    """

    _patch_transport(
        monkeypatch,
        lambda _url, **_kwargs: _http_response({"error": "unauthorized"}, status_code=401),
    )
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert "401" in result.detail
    assert "unauthorized" in result.detail


def test_a_cloud_that_does_not_serve_an_offered_model_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key works and the request arrived — a different fault, with a different cure."""

    _patch_transport(
        monkeypatch,
        lambda _url, **_kwargs: _http_response({"error": "model not found"}, status_code=404),
    )
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert "gpt-oss:20b" in result.detail


def test_a_cloud_that_cannot_be_reached_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raised probe would take the listing of every other provider down with it."""

    def refused(_url: str, **_kwargs: object) -> httpx.Response:
        raise ConnectionError("connection refused")

    _patch_transport(monkeypatch, refused)
    result = cloud_adapters.probe_ollama_cloud(_probe_defaults())

    assert not result.available
    assert result.detail == "nothing is listening at https://ollama.test"


def test_the_probe_carries_the_key_and_does_not_wait_out_a_judgement_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The credential goes on the wire as a bearer token, on the probe as on a judgement."""

    seen = _patch_transport(monkeypatch, lambda _url, **_kwargs: _shown("thinking"))
    cloud_adapters.probe_ollama_cloud(_probe_defaults(timeout_seconds=360))

    headers = seen["headers"]
    assert isinstance(headers, httpx.Headers)
    assert headers["authorization"] == "Bearer test-key"
    assert seen["timeout"] == cloud_adapters.PROBE_TIMEOUT_SECONDS


def _complete(transport: OllamaChatTransport) -> str:
    return transport.complete(
        [{"role": "user", "content": "Does the boundary hold?"}],
        schema={"type": "object", "properties": {"answer": {"type": "string"}}},
        task=ReasoningTask.ANSWER_REVIEW_QUESTION,
        think=None,
        temperature=None,
    )


def test_a_configured_key_reaches_the_wire_as_a_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cloud is the same API behind a credential, so the transport is the same transport."""

    seen = _patch_transport(
        monkeypatch,
        lambda _url, **_kwargs: _http_response(
            {"message": {"role": "assistant", "content": '{"answer": "yes"}'}}
        ),
    )

    assert _complete(OllamaChatTransport(_reasoning_config())) == '{"answer": "yes"}'
    headers = seen["headers"]
    assert isinstance(headers, httpx.Headers)
    assert headers["authorization"] == "Bearer test-key"


def test_a_provider_naming_no_key_variable_sends_no_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The local path stays what it was: nothing to resolve, so nothing is attached."""

    seen = _patch_transport(
        monkeypatch,
        lambda _url, **_kwargs: _http_response(
            {"message": {"role": "assistant", "content": '{"answer": "yes"}'}}
        ),
    )

    _complete(OllamaChatTransport(_reasoning_config(api_key_env=None)))

    headers = seen["headers"]
    assert isinstance(headers, httpx.Headers)
    assert "authorization" not in headers


def test_a_transport_configured_for_the_cloud_without_a_key_refuses_at_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named where the credential is missing, rather than as an HTTP 401 mid-review."""

    monkeypatch.delenv(_KEY_VARIABLE, raising=False)

    with pytest.raises(ConfigurationError, match=_KEY_VARIABLE):
        OllamaChatTransport(_reasoning_config())


def test_the_cloud_is_the_first_provider_the_chooser_is_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registry order is chooser order, and this one is offered without anything installed."""

    monkeypatch.delenv("ARCHCOMPASS_PROVIDERS", raising=False)

    assert next(iter(enabled_providers())) == cloud_adapters.PROVIDER_NAME


def test_a_deployment_can_still_narrow_the_registry_to_the_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hosted deployment has no local server to reach, and says so by name."""

    monkeypatch.setenv("ARCHCOMPASS_PROVIDERS", f"{cloud_adapters.PROVIDER_NAME},google")

    assert list(enabled_providers()) == [cloud_adapters.PROVIDER_NAME, "google"]


def test_the_descriptor_reaches_the_cloud_with_a_credential_and_a_fleet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three fields that separate this descriptor from the local one."""

    monkeypatch.delenv("ARCHCOMPASS_PROVIDERS", raising=False)
    defaults = enabled_providers()[cloud_adapters.PROVIDER_NAME].defaults

    assert defaults.base_url == "https://ollama.com"
    assert defaults.api_key_env == "OLLAMA_API_KEY"
    assert defaults.concurrent_requests > 1
