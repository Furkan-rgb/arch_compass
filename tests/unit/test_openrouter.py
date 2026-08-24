"""The one hosted boundary: what it offers, and what it puts on the wire.

Nothing here talks to OpenRouter. What is worth testing is the part that is ours — which
catalogue rows become choices, and the request contract, which is the whole reason this
provider is not a row in `openai_compatible.py`.
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ProviderError
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


class _Response:
    def __init__(self, status: int, body: Any) -> None:
        self.status_code = status
        self._body = body
        self.text = str(body)

    def json(self) -> Any:
        return self._body


def _embeddings(
    monkeypatch: pytest.MonkeyPatch, response: _Response
) -> openrouter.OpenRouterEmbeddings:
    sent: dict[str, Any] = {}

    def _post(url: str, **kwargs: Any) -> _Response:
        sent["url"] = url
        sent["json"] = kwargs.get("json")
        return response

    monkeypatch.setattr(openrouter.httpx, "post", _post)
    embedder = openrouter.OpenRouterEmbeddings(
        api_key="k", model="vendor/embed", dimensions=8
    )
    embedder._sent = sent
    return embedder


def test_the_width_the_index_keys_on_is_sent_with_every_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`embedding_identity` is `provider:model:dimensions`, so the width is not advisory.

    A namespace whose vectors do not compare is a silently wrong answer rather than a
    failure, which is why the number goes on the request and is validated upstream.
    """

    embedder = _embeddings(
        monkeypatch,
        _Response(200, {"data": [{"index": 0, "embedding": [0.5] * 8}]}),
    )

    embedder.embed_query("one question")

    sent = cast("dict[str, Any]", embedder._sent)
    assert sent["json"]["dimensions"] == 8
    assert sent["json"]["input"] == ["one question"]


def test_vectors_are_paired_by_index_and_never_by_arrival(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The join the deleted Google batch path got wrong, done the other way here.

    The caller pairs these back onto its own list of chunks, so a response that arrived
    out of order would file every chunk under its neighbour's text — and the index would
    be wrong in a way nothing downstream could see.
    """

    embedder = _embeddings(
        monkeypatch,
        _Response(
            200,
            {
                "data": [
                    {"index": 1, "embedding": [2.0] * 8},
                    {"index": 0, "embedding": [1.0] * 8},
                ]
            },
        ),
    )

    vectors = embedder.embed_documents(["first", "second"])

    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 2.0


def test_a_short_answer_is_refused_rather_than_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing vector reads as an unrelated one once it is in the index."""

    embedder = _embeddings(
        monkeypatch, _Response(200, {"data": [{"index": 0, "embedding": [1.0] * 8}]})
    )

    with pytest.raises(ProviderError, match="1 of 2"):
        embedder.embed_documents(["first", "second"])


def test_a_refused_request_is_a_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """So `call_with_retry` at the call site can decide whether waiting would help."""

    embedder = _embeddings(monkeypatch, _Response(429, {"error": {"message": "slow down"}}))

    with pytest.raises(ProviderError, match="429"):
        embedder.embed_query("one question")
