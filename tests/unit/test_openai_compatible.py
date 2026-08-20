"""Reaching Groq, Cerebras and anything else that speaks OpenAI's chat API.

Nothing here talks to a vendor. What is worth testing is the part that is ours: which models
a listing is allowed to turn into choices, what happens when a vendor renames one, and that
the transport is built pointing at the right host with the right credential — because
getting that wrong produces a request that goes to OpenAI with a Groq key on it.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from archcompass.bootstrap import enabled_providers
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.adapters import openai_compatible
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.openai_compatible import (
    CEREBRAS,
    GROQ,
    OPENAI_COMPATIBLE_PROVIDERS,
    descriptors,
    probe_openai_compatible,
)


def _listing(*model_ids: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"object": "list", "data": [{"id": name} for name in model_ids]},
        request=httpx.Request("GET", "https://example.invalid/v1/models"),
    )


@pytest.fixture
def groq_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "not-a-real-key")
    monkeypatch.delenv(GROQ.models_env, raising=False)


def _serving(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> list[dict[str, Any]]:
    """Answer the listing with `response`, and keep what was asked for."""

    asked: list[dict[str, Any]] = []

    def get(url: str, **kwargs: Any) -> httpx.Response:
        asked.append({"url": url, **kwargs})
        return response

    monkeypatch.setattr(openai_compatible.httpx, "get", get)
    return asked


def test_a_vendor_offers_only_the_models_this_build_judges_with(
    monkeypatch: pytest.MonkeyPatch, groq_key: None
) -> None:
    """The endpoint's catalogue is an input, not the answer.

    A vendor lists everything it serves, including transcription and guard models that
    cannot hold a JSON schema. Judging is a schema call, so a model that cannot is not a
    choice — and it would not fail at selection, it would fail once per boundary.
    """

    asked = _serving(
        monkeypatch,
        _listing(
            "openai/gpt-oss-120b",
            "whisper-large-v3",
            "meta-llama/llama-guard-4-12b",
            "llama-3.3-70b-versatile",
        ),
    )
    descriptor = enabled_providers()["groq"]

    result = probe_openai_compatible(GROQ, descriptor.defaults)

    assert result.available
    assert [model.name for model in result.models] == [
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
    ]
    # Asked of the vendor's own host, with the vendor's own credential.
    assert asked[0]["url"] == "https://api.groq.com/openai/v1/models"
    assert asked[0]["headers"]["Authorization"] == "Bearer not-a-real-key"


def test_a_model_is_offered_in_one_mode_because_nothing_here_asks_for_reasoning(
    monkeypatch: pytest.MonkeyPatch, groq_key: None
) -> None:
    """Requiring reasoning has to reach the provider as an instruction or not be offered.

    These vendors spell it three incompatible ways and several of the models have no such
    setting at all, so the catalogue says `None` — the model does what it does by default —
    rather than offering a switch that would quietly do nothing.
    """

    _serving(monkeypatch, _listing("openai/gpt-oss-120b"))

    result = probe_openai_compatible(GROQ, enabled_providers()["groq"].defaults)

    assert [model.thinking_modes for model in result.models] == [(None,)]


def test_a_renamed_model_can_be_named_without_waiting_for_a_release(
    monkeypatch: pytest.MonkeyPatch, groq_key: None
) -> None:
    """The list is hand-maintained, so it needs a way to be wrong without being a dead end."""

    monkeypatch.setenv(GROQ.models_env, "moonshotai/kimi-k2-instruct-0999, llama-3.1-8b")
    _serving(monkeypatch, _listing("moonshotai/kimi-k2-instruct-0999", "whisper-large-v3"))

    result = probe_openai_compatible(GROQ, enabled_providers()["groq"].defaults)

    # Still intersected with what the endpoint has: a typo is an absent row here rather
    # than a request that fails in the middle of a review.
    assert [model.name for model in result.models] == ["moonshotai/kimi-k2-instruct-0999"]


def test_a_vendor_serving_none_of_them_says_what_to_do_about_it(
    monkeypatch: pytest.MonkeyPatch, groq_key: None
) -> None:
    _serving(monkeypatch, _listing("whisper-large-v3"))

    result = probe_openai_compatible(GROQ, enabled_providers()["groq"].defaults)

    assert not result.available
    assert GROQ.models_env in result.detail


def test_a_vendor_without_a_key_is_unavailable_rather_than_broken(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unavailability is a value the chooser renders, never an exception that hides it."""

    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)

    result = probe_openai_compatible(CEREBRAS, enabled_providers()["cerebras"].defaults)

    assert not result.available
    assert "CEREBRAS_API_KEY" in result.detail


def test_a_vendor_that_will_not_answer_is_unavailable_rather_than_broken(
    monkeypatch: pytest.MonkeyPatch, groq_key: None
) -> None:
    def refuse(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("nothing is listening")

    monkeypatch.setattr(openai_compatible.httpx, "get", refuse)

    result = probe_openai_compatible(GROQ, enabled_providers()["groq"].defaults)

    assert not result.available
    assert "nothing is listening" in result.detail


def test_every_vendor_of_this_api_is_a_provider_the_workspace_can_choose() -> None:
    """The registry and the transport's dispatch have to keep naming the same set."""

    registered = enabled_providers()
    for descriptor in descriptors():
        assert registered[descriptor.name] is not None
        assert descriptor.name in OPENAI_COMPATIBLE_PROVIDERS
        # A heading rather than a key, because the chooser groups by provider.
        assert descriptor.label and descriptor.label != descriptor.name


def test_the_transport_is_built_against_the_vendor_that_was_chosen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one mistake worth a test: the right key sent to the wrong host.

    Every vendor here shares a client class whose default endpoint is OpenAI's, so a branch
    that forgot the base URL would send a Groq key to `api.openai.com` and report a bad
    credential rather than a bad configuration.
    """

    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")
    descriptor = enabled_providers()["cerebras"]

    model = build_chat_model(
        ReasoningModelConfig(
            provider="cerebras",
            model="gpt-oss-120b",
            base_url=descriptor.defaults.resolved_base_url(),
            api_key_env=descriptor.defaults.api_key_env,
            timeout_seconds=30.0,
        )
    )

    assert str(model.openai_api_base) == "https://api.cerebras.ai/v1"
    assert model.openai_api_key is not None
    assert model.openai_api_key.get_secret_value() == "cerebras-key"
    # Retrying belongs to `archcompass.retrying`, which is the only layer that can wait for
    # a quota window, say so in the log, and fail as a `ProviderError`.
    assert model.max_retries == 0


def test_the_transport_refuses_without_the_credential_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    descriptor = enabled_providers()["groq"]

    with pytest.raises(ConfigurationError, match="GROQ_API_KEY"):
        build_chat_model(
            ReasoningModelConfig(
                provider="groq",
                model="openai/gpt-oss-120b",
                base_url=descriptor.defaults.resolved_base_url(),
                api_key_env=descriptor.defaults.api_key_env,
                timeout_seconds=30.0,
            )
        )
