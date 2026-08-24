"""The one hosted boundary: what it offers, and what it puts on the wire.

Nothing here talks to OpenRouter. What is worth testing is the part that is ours — which
catalogue rows become choices, and the request contract, which is the whole reason this
provider is not a row in `openai_compatible.py`.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from archcompass.configuration import ReasoningModelConfig
from archcompass.reasoning.adapters import openrouter
from archcompass.reasoning.adapters.factory import build_chat_model


def _entry(identifier: str, *, parameters: list[str] | None = None, **rest: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": rest.pop("name", identifier),
        "supported_parameters": (
            ["structured_outputs", "tools", "max_tokens"]
            if parameters is None
            else parameters
        ),
        **rest,
    }


def _offered(entries: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "_catalogue", lambda path, key: entries)
    result = openrouter.probe(openrouter.DESCRIPTOR.defaults)
    return [model.name for model in result.models]


def test_a_model_is_offered_for_declaring_what_a_review_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The filter is the capability, not a name somebody checked once.

    Every other vendor here is offered a hand-approved list, because their catalogues are
    full of models that will not honour a JSON schema and the only way to know is to have
    judged with them. OpenRouter publishes the fact, so there is no list here to go stale
    when somebody ships a better model on a Tuesday.
    """

    offered = _offered(
        [
            _entry("vendor/judges-fine"),
            _entry("vendor/no-schema", parameters=["tools"]),
            _entry("vendor/no-tools", parameters=["structured_outputs"]),
            _entry("vendor/nothing", parameters=[]),
        ],
        monkeypatch,
    )

    assert offered == ["vendor/judges-fine"]


@pytest.mark.parametrize(
    ("identifier", "why"),
    [
        ("openrouter/free", "a router resolves to a different model per request"),
        ("~vendor/model-latest", "a moving pointer is a different model next quarter"),
        ("vendor/model:batch", "batch-only models refuse an ordinary call"),
    ],
)
def test_a_catalogue_row_that_is_not_one_model_is_never_offered(
    identifier: str, why: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`model_identity` promises that one string means one model produced the finding.

    The finding cache is keyed on that promise. A router or a moving pointer would file two
    models under one name and report no change when everything had changed; a batch-only id
    would put a row on the chooser that fails on the first judgement.
    """

    offered = _offered([_entry(identifier), _entry("vendor/real")], monkeypatch)

    assert offered == ["vendor/real"], why


def test_a_models_own_window_reaches_the_chooser(monkeypatch: pytest.MonkeyPatch) -> None:
    """The catalogue knows more than any descriptor could, so it is asked.

    A single `context_window_tokens` on the descriptor cannot describe 222 models spanning
    four thousand tokens to two million. Reporting each model's own is what lets
    `ModelCatalogService` clamp an authored budget down to the model actually chosen.
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(
        openrouter,
        "_catalogue",
        lambda path, key: [
            _entry(
                "vendor/small",
                name="Vendor: Small",
                context_length=4_096,
                top_provider={"max_completion_tokens": 1_024},
            )
        ],
    )

    model = openrouter.probe(openrouter.DESCRIPTOR.defaults).models[0]

    assert model.label == "Vendor: Small"
    assert model.input_token_limit == 4_096
    assert model.output_token_limit == 1_024


def test_a_catalogue_with_nothing_judgeable_reads_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "_catalogue", lambda path, key: [_entry("v/m", parameters=[])])

    result = openrouter.probe(openrouter.DESCRIPTOR.defaults)

    assert not result.available
    assert "structured output" in result.detail


def test_a_missing_credential_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chooser asks every provider whether it is reachable; one without a key is a row."""

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    result = openrouter.probe(openrouter.DESCRIPTOR.defaults)

    assert not result.available
    assert "OPENROUTER_API_KEY" in result.detail


def test_the_request_carries_the_ceiling_openrouter_can_route_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`max_tokens`, and never `max_completion_tokens`, and this is not a preference.

    `provider.require_parameters` is matched against every parameter in the body, and no
    endpoint of `google/gemini-3.5-flash-lite` declares `max_completion_tokens` while all
    seven declare `max_tokens`. `ChatOpenAI`'s own field normalises to the first whichever
    name it is given, so the ceiling goes through `extra_body`, which the SDK passes
    verbatim. The two together were a 404 on every request.
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = ReasoningModelConfig(
        provider="openrouter",
        model="vendor/model",
        base_url=openrouter.BASE_URL,
        api_key_env="OPENROUTER_API_KEY",
        timeout_seconds=30.0,
        max_output_tokens=8_000,
        context_window_tokens=128_000,
    )

    built = cast("Any", build_chat_model(config))
    body = cast("dict[str, Any]", built.extra_body)

    assert body == {"max_tokens": 8_000, "provider": {"require_parameters": True}}


def test_the_route_is_required_to_support_what_was_asked_for() -> None:
    """The difference between "this route probably honours a schema" and "this route does".

    OpenRouter's default is a soft preference that never removes a candidate endpoint, and
    a model's catalogue capabilities are a union across its endpoints — five of twenty on
    `openai/gpt-oss-120b` do not support structured output. Without this the review looks
    fine and is not.
    """

    assert openrouter.request_body(1)["provider"] == {"require_parameters": True}
