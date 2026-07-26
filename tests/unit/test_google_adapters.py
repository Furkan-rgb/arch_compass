from __future__ import annotations

import json
import math
from typing import Annotated, Literal

import httpx
import pytest
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field, RootModel
from tests.reasoning_support import candidate as _candidate
from tests.reasoning_support import case as _case
from tests.reasoning_support import policies as _policies
from tests.reasoning_support import verdict_json

from archcompass.adapters.models import google as google_adapters
from archcompass.adapters.models.google import (
    GoogleChatTransport,
    GoogleEmbeddingProvider,
    GoogleReasoningProvider,
    _for_gemini,
    _response_text,
    _split_system_prompt,
    _thinking_config,
)
from archcompass.adapters.models.structured import (
    ProposedCandidateVerdict,
)
from archcompass.configuration import EmbeddingModelConfig, ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError, ProviderError
from archcompass.ports.reasoning import ReasoningTask

_KEY_VARIABLE = "ARCHCOMPASS_TEST_GOOGLE_KEY"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_VARIABLE, "test-key")


def _embedding_config(*, dimensions: int = 3) -> EmbeddingModelConfig:
    return EmbeddingModelConfig(
        provider="google",
        model="embedding-test",
        api_key_env=_KEY_VARIABLE,
        dimensions=dimensions,
        timeout_seconds=5,
    )


def _reasoning_config() -> ReasoningModelConfig:
    return ReasoningModelConfig(
        provider="google",
        model="reasoning-test",
        api_key_env=_KEY_VARIABLE,
        timeout_seconds=10,
    )


def _candidate_response(text: str, *, status_code: int = 200) -> httpx.Response:
    return _raw_response(
        {
            "candidates": [
                {
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "finishReason": "STOP",
                }
            ]
        },
        status_code=status_code,
    )


def _raw_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/")
    return httpx.Response(status_code, json=payload, request=request)


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler: object) -> None:
    """Stub the HTTP layer beneath the real `google-genai` client.

    The SDK's sync path builds a request and calls `httpx.Client.send`, so patching
    `send` keeps its own request building, response parsing and status-to-`APIError`
    mapping in the path. These tests therefore exercise the transport we ship.
    """

    def send(_self: object, request: httpx.Request, **kwargs: object) -> httpx.Response:
        del kwargs
        return handler(request)  # type: ignore[operator]

    monkeypatch.setattr(httpx.Client, "send", send)


def test_missing_api_key_names_the_variable_and_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_KEY_VARIABLE, raising=False)

    with pytest.raises(ConfigurationError, match=rf"{_KEY_VARIABLE}.*\.env"):
        GoogleReasoningProvider(_reasoning_config())


def test_unconfigured_api_key_variable_is_refused() -> None:
    config = _reasoning_config().model_copy(update={"api_key_env": None})

    with pytest.raises(ConfigurationError, match="api_key_env"):
        GoogleReasoningProvider(config)


def test_system_prompt_is_split_out_and_assistant_becomes_model() -> None:
    system, contents = _split_system_prompt(
        [
            {"role": "system", "content": "Be exact."},
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Prior answer"},
            {"role": "user", "content": "Fix it"},
        ]
    )

    assert system == "Be exact."
    assert [item.role for item in contents] == ["user", "model", "user"]
    assert [part.text for item in contents for part in (item.parts or [])] == [
        "First",
        "Prior answer",
        "Fix it",
    ]


def test_thinking_is_held_down_for_the_short_decision_stages() -> None:
    """`thinking_level` is the spelling every reachable model accepts.

    `thinking_budget=0` is rejected with HTTP 400 by `gemini-flash-latest` and
    `gemini-3.6-flash`, so the level is used even where the budget would also work.
    """

    assert _thinking_config(False) == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MINIMAL
    )
    assert _thinking_config(None) is None
    assert _thinking_config(True) is None
    assert _thinking_config("high") == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.HIGH
    )


def test_reasoning_request_carries_the_schema_and_the_system_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _candidate_response(
            verdict_json(bearings=2)
        )

    _patch_transport(monkeypatch, send)
    provider = GoogleReasoningProvider(_reasoning_config())

    verdict = provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

    assert verdict.rationale
    assert len(captured) == 1
    payload = json.loads(captured[0].content)
    # The full JSON Schema goes as `responseJsonSchema`, keeping `$defs` and `$ref`
    # intact; `responseSchema` would flatten them through an OpenAPI subset.
    schema = payload["generationConfig"]["responseJsonSchema"]
    assert "$defs" in schema
    # The narrowed constraint is the thing that must survive the wire: it is what makes a
    # bearing array of the wrong length unrepresentable rather than merely discouraged.
    assert schema["properties"]["policy_bearings"]["minItems"] == 2
    assert schema["properties"]["policy_bearings"]["maxItems"] == 2
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert "Provider-specific capabilities leak" in json.dumps(payload["contents"])
    assert payload["systemInstruction"]["parts"][0]["text"]


class _Left(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["left"]
    value: str


class _Right(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["right"]
    count: int


# A discriminated union defined here rather than borrowed from a shipped schema. Tying
# this test to whichever production type currently happens to use one means the coverage
# disappears silently the day that type does. Deliberately no docstring: Pydantic copies
# it into the schema description, where its words would satisfy the assertions below.
class _Union(RootModel[list[Annotated[_Left | _Right, Field(discriminator="kind")]]]):
    pass


def test_a_discriminated_union_is_translated_into_the_accepted_dialect() -> None:
    """Gemini rejects `oneOf`/`discriminator` with HTTP 400."""

    original = _Union.model_json_schema()
    assert "oneOf" in json.dumps(original)
    assert "discriminator" in json.dumps(original)

    translated = json.dumps(_for_gemini(original))

    assert "oneOf" not in translated
    assert "discriminator" not in translated
    assert "anyOf" in translated
    # The constraints that make handles and allowlists enforceable must survive intact.
    assert "$defs" in translated
    assert "$ref" in translated


def test_translation_leaves_a_schema_without_unions_untouched() -> None:
    original = ProposedCandidateVerdict.model_json_schema()

    assert _for_gemini(original) == original


def test_query_variants_are_disjoint_so_anyof_admits_no_more_than_oneof() -> None:
    """`anyOf` is looser than `oneOf`, and this is why that is harmless here.

    Every variant pins `kind` to its own values and forbids extra properties, so no
    object can satisfy two of them and the looser keyword accepts nothing extra.
    """

    definitions = _Union.model_json_schema()["$defs"]
    seen: set[str] = set()
    variants = 0
    for _name, definition in definitions.items():
        variants += 1
        assert definition["additionalProperties"] is False
        kind = definition["properties"]["kind"]
        values = set(kind["enum"]) if "enum" in kind else {kind["const"]}
        assert values
        assert not (values & seen), "two variants share a kind"
        seen |= values
    assert variants > 1


def test_truncated_response_names_the_thinking_budget_overlap() -> None:
    response = types.GenerateContentResponse(
        candidates=[types.Candidate(finish_reason=types.FinishReason.MAX_TOKENS)]
    )

    with pytest.raises(ProviderError, match="max_output_tokens"):
        _response_text(
            response,
            task=ReasoningTask.JUDGE_FINDING_CANDIDATE,
            config=_reasoning_config(),
        )


def test_blocked_prompt_is_reported_rather_than_parsed() -> None:
    response = types.GenerateContentResponse(
        prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.SAFETY
        )
    )

    with pytest.raises(ProviderError, match="no candidate"):
        _response_text(
            response,
            task=ReasoningTask.JUDGE_FINDING_CANDIDATE,
            config=_reasoning_config(),
        )


def test_api_error_is_wrapped_with_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response(
            {"error": {"code": 400, "message": "Invalid schema", "status": "INVALID_ARGUMENT"}},
            status_code=400,
        )

    _patch_transport(monkeypatch, send)
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError, match=r"HTTP 400.*Invalid schema"):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))


def test_rate_limited_request_is_retried_to_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The free tier spends its per-minute quota routinely, and a short wait clears it."""

    attempts = 0

    def send(request: httpx.Request) -> httpx.Response:
        del request
        nonlocal attempts
        attempts += 1
        return _raw_response(
            {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}},
            status_code=429,
        )

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", lambda _seconds: None)
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError, match="HTTP 429"):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

    assert attempts == google_adapters._MAX_TRANSPORT_ATTEMPTS


def test_a_rate_limit_waits_on_the_scale_of_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The server's `RetryInfo` is a floor, not the answer.

    It reports when the next single unit of quota frees up - observed as 232ms while a
    50-input batch still could not be served - so waiting exactly that long spends every
    attempt inside a window already known to be closed.
    """

    slept: list[float] = []

    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response(
            {
                "error": {
                    "code": 429,
                    "message": "Quota exceeded",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "0.232752802s",
                        }
                    ],
                }
            },
            status_code=429,
        )

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", slept.append)
    provider = GoogleEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match="HTTP 429"):
        provider.embed(["one"])

    assert slept == [8.0, 16.0, 32.0, 64.0, 70.0]


def test_a_longer_named_delay_is_honoured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the server asks for longer than the backoff would wait, it is obeyed."""

    slept: list[float] = []
    attempts = 0

    def send(request: httpx.Request) -> httpx.Response:
        del request
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return _raw_response(
                {
                    "error": {
                        "code": 429,
                        "message": "Quota exceeded",
                        "status": "RESOURCE_EXHAUSTED",
                        "details": [
                            {
                                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                                "retryDelay": "23.5s",
                            }
                        ],
                    }
                },
                status_code=429,
            )
        return _raw_response({"embeddings": [{"values": [1.0, 0.0, 0.0]}]})

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", slept.append)
    provider = GoogleEmbeddingProvider(_embedding_config())

    assert provider.embed(["one"]) == [[1.0, 0.0, 0.0]]
    assert slept == [pytest.approx(23.5)]


def test_a_named_retry_delay_is_capped(monkeypatch: pytest.MonkeyPatch) -> None:
    """An exhausted per-day quota must not park a run for hours."""

    slept: list[float] = []

    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response(
            {
                "error": {
                    "code": 429,
                    "message": "Quota exceeded",
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "86400s",
                        }
                    ],
                }
            },
            status_code=429,
        )

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", slept.append)
    provider = GoogleEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match="HTTP 429"):
        provider.embed(["one"])

    assert slept
    assert all(delay == google_adapters._MAX_RETRY_DELAY_SECONDS for delay in slept)


def test_a_failure_without_a_named_delay_backs_off_exponentially(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept: list[float] = []

    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response(
            {"error": {"code": 503, "message": "Overloaded", "status": "UNAVAILABLE"}},
            status_code=503,
        )

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", slept.append)
    provider = GoogleEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match="HTTP 503"):
        provider.embed(["one"])

    assert slept == [0.5, 1.0, 2.0, 4.0, 8.0]


def test_a_rejected_request_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 400 fails identically every time; retrying it only wastes free-tier quota."""

    attempts = 0

    def send(request: httpx.Request) -> httpx.Response:
        del request
        nonlocal attempts
        attempts += 1
        return _raw_response(
            {"error": {"code": 400, "message": "Bad request", "status": "INVALID_ARGUMENT"}},
            status_code=400,
        )

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", lambda _seconds: None)
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

    assert attempts == 1


def test_embeddings_are_normalised_to_unit_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gemini truncates without renormalising, and the policy index ranks by L2."""

    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response({"embeddings": [{"values": [3.0, 4.0, 0.0]}]})

    _patch_transport(monkeypatch, send)
    provider = GoogleEmbeddingProvider(_embedding_config())

    [vector] = provider.embed(["one"])

    assert math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
    assert vector == pytest.approx([0.6, 0.8, 0.0])


def test_embedding_requests_are_chunked_to_the_batch_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The policy corpus is larger than one call may carry."""

    batch_sizes: list[int] = []

    def send(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        size = len(payload["requests"])
        batch_sizes.append(size)
        return _raw_response({"embeddings": [{"values": [1.0, 0.0, 0.0]}] * size})

    _patch_transport(monkeypatch, send)
    provider = GoogleEmbeddingProvider(_embedding_config())

    vectors = provider.embed([f"chunk-{index}" for index in range(120)])

    assert len(vectors) == 120
    # Half the per-minute window, so the quota can refill between calls rather than
    # being spent entirely by the first one.
    assert batch_sizes == [50, 50, 20]


def test_embedding_dimension_mismatch_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def send(request: httpx.Request) -> httpx.Response:
        del request
        return _raw_response({"embeddings": [{"values": [1.0, 0.0]}]})

    _patch_transport(monkeypatch, send)
    provider = GoogleEmbeddingProvider(_embedding_config())

    with pytest.raises(ProviderError, match="expected 3"):
        provider.embed(["one"])


def test_timeout_is_sent_to_the_sdk_in_milliseconds() -> None:
    transport = GoogleChatTransport(
        _reasoning_config().model_copy(
            update={"fast_timeout_seconds": 12.0, "deep_timeout_seconds": 34.0}
        )
    )

    options = {
        is_fast: client._api_client._http_options  # pyright: ignore[reportPrivateUsage]
        for is_fast, client in transport._clients.items()  # pyright: ignore[reportPrivateUsage]
    }

    assert options[True].timeout == 12_000
    assert options[False].timeout == 34_000


def test_model_identity_names_the_provider_and_model() -> None:
    assert GoogleReasoningProvider(_reasoning_config()).model_identity == (
        "google:reasoning-test"
    )
