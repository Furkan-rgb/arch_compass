from __future__ import annotations

import base64
import json
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
    GoogleReasoningProvider,
    _for_gemini,
    _response_text,
    _split_system_prompt,
    _thinking_config,
)
from archcompass.adapters.models.structured import (
    AssistantToolTurn,
    InvestigationMessage,
    ProposedCandidateVerdict,
    ToolCall,
    ToolResultTurn,
)
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError, ProviderError
from archcompass.ports.investigation import ToolSpec
from archcompass.ports.model_catalog import ProviderDefaults
from archcompass.ports.reasoning import ReasoningTask

_KEY_VARIABLE = "ARCHCOMPASS_TEST_GOOGLE_KEY"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_KEY_VARIABLE, "test-key")


def _probe_defaults() -> ProviderDefaults:
    """What a probe is handed: a credential variable and, here, no endpoint of its own."""

    return ProviderDefaults(api_key_env=_KEY_VARIABLE)


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
    assert _thinking_config("high") == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.HIGH
    )


def test_required_reasoning_names_a_level_rather_than_omitting_the_field() -> None:
    """An absent `thinking_level` is the model's default, and defaults disagree.

    Measured against one key on one prompt: `gemini-3.6-flash` spends 831 thinking tokens
    with the field absent, `gemini-3.5-flash-lite` spends none. So a configuration saying
    reasoning is required has to name a level, or it turns reasoning off on exactly the
    models that most need it — which is what produced a review whose every verdict claimed
    to stand either way and which therefore asked nothing.
    """

    assert _thinking_config(True) == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.MEDIUM
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


@pytest.mark.parametrize(
    ("configured", "sent"),
    [(True, "MEDIUM"), (False, "MINIMAL"), (None, None)],
)
def test_the_configured_thinking_setting_reaches_the_request(
    monkeypatch: pytest.MonkeyPatch,
    configured: bool | None,
    sent: str | None,
) -> None:
    """`thinking: true` has to arrive as a request that requires thinking.

    The wire and not the argument, because the bug this guards against lived entirely
    between the two: `_thinking_config` accepted `true` and returned nothing, so the request
    carried no thinking instruction at all. Unlike Ollama, where `think` is a parameter of
    the same shape, this one is a translation — the setting is a bool and the API wants a
    level — and a translation is a place a value can go missing.
    """

    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _candidate_response(verdict_json(bearings=2))

    _patch_transport(monkeypatch, send)
    config = _reasoning_config().model_copy(update={"thinking": configured})

    GoogleReasoningProvider(config).judge_finding_candidate(_case(), _candidate(), _policies(2))

    thinking = json.loads(captured[0].content)["generationConfig"].get("thinkingConfig") or {}
    # Either spelling: the API takes both, and which one the SDK emits is its business
    # rather than the thing under test here.
    assert (thinking.get("thinkingLevel") or thinking.get("thinking_level")) == sent


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

    with pytest.raises(ProviderError, match="output tokens"):
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

    It reports when the next single unit of quota frees up — observed as 232ms while a
    request still could not be served — so waiting exactly that long spends every attempt
    inside a window already known to be closed.
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
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError, match="HTTP 429"):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

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
        return _candidate_response(verdict_json(bearings=2))

    _patch_transport(monkeypatch, send)
    monkeypatch.setattr(google_adapters.time, "sleep", slept.append)
    provider = GoogleReasoningProvider(_reasoning_config())

    assert provider.judge_finding_candidate(_case(), _candidate(), _policies(2)).rationale
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
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError, match="HTTP 429"):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

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
    provider = GoogleReasoningProvider(_reasoning_config())

    with pytest.raises(ProviderError, match="HTTP 503"):
        provider.judge_finding_candidate(_case(), _candidate(), _policies(2))

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


def test_timeout_is_sent_to_the_sdk_in_milliseconds() -> None:
    transport = GoogleChatTransport(
        _reasoning_config().model_copy(update={"timeout_seconds": 34.0})
    )

    options = transport._client._api_client._http_options  # pyright: ignore[reportPrivateUsage]

    assert options.timeout == 34_000


def test_model_identity_names_the_provider_and_model() -> None:
    assert GoogleReasoningProvider(_reasoning_config()).model_identity == (
        "google:reasoning-test"
    )


_TOOLS = (
    ToolSpec(
        name="search_source",
        description="Find text.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
)


def _investigation_request() -> list[InvestigationMessage]:
    """One investigation part-way through: a prompt, a call made, a result returned."""

    return [
        {"role": "system", "content": "Look before you ask."},
        {"role": "user", "content": "These are the verdicts."},
        AssistantToolTurn(
            text="Let me look.",
            calls=(ToolCall(name="search_source", arguments={"query": "AudioSink"}),),
        ),
        ToolResultTurn(call_name="search_source", content="audio/sink.py:12: write()"),
    ]


def _tool_response(*parts: dict[str, object]) -> httpx.Response:
    return _raw_response(
        {
            "candidates": [
                {"content": {"role": "model", "parts": list(parts)}, "finishReason": "STOP"}
            ]
        }
    )


def test_an_investigation_request_carries_the_tools_and_the_turns_that_led_to_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole translation in one request: declarations, a call, and its answer.

    The pairing is positional — result *n* answers call *n* of the turn before it — so both
    halves have to survive as their own parts. Folding either into prose would leave the
    model to re-read its own history out of a string.
    """

    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _tool_response({"text": "Enough."})

    _patch_transport(monkeypatch, send)
    transport = GoogleChatTransport(_reasoning_config())

    transport.complete_with_tools(
        _investigation_request(),
        tools=_TOOLS,
        require_call=True,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    payload = json.loads(captured[0].content)
    # The forced first turn rides as the vendor's own must-call mode, not as prompt text.
    config = payload.get("toolConfig") or payload["tool_config"]
    calling = config.get("functionCallingConfig") or config["function_calling_config"]
    assert calling["mode"] == "ANY"
    declaration = payload["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == "search_source"
    assert declaration["description"] == "Find text."
    # Plain JSON Schema, not the typed OpenAPI subset: the same reason the response schema
    # travels as `responseJsonSchema`. Either spelling — which one the SDK emits is its
    # business, and it emits this one uncamelized while camelizing everything around it.
    schema = declaration.get("parametersJsonSchema") or declaration["parameters_json_schema"]
    assert schema["properties"]["query"]["type"] == "string"
    assert "parameters" not in declaration
    # No response grammar at all on an investigation turn.
    assert "responseJsonSchema" not in payload.get("generationConfig", {})
    assert payload["systemInstruction"]["parts"][0]["text"] == "Look before you ask."

    contents = payload["contents"]
    assert [item["role"] for item in contents] == ["user", "model", "user"]
    assert contents[1]["parts"][0]["text"] == "Let me look."
    assert contents[1]["parts"][1]["functionCall"] == {
        "name": "search_source",
        "args": {"query": "AudioSink"},
    }
    answer = contents[2]["parts"][0]["functionResponse"]
    assert answer["name"] == "search_source"
    assert answer["response"] == {"result": "audio/sink.py:12: write()"}


def test_a_reply_asking_for_tools_comes_back_as_the_calls_it_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_transport(
        monkeypatch,
        lambda _request: _tool_response(
            {"text": "Two things to check."},
            {"functionCall": {"name": "search_source", "args": {"query": "AudioSink"}}},
            {"functionCall": {"name": "read_source", "args": {"path": "a.py"}}},
        ),
    )
    transport = GoogleChatTransport(_reasoning_config())

    exchange = transport.complete_with_tools(
        _investigation_request(),
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    assert exchange.text == "Two things to check."
    assert exchange.calls == (
        ToolCall(name="search_source", arguments={"query": "AudioSink"}),
        ToolCall(name="read_source", arguments={"path": "a.py"}),
    )


def test_a_decoded_turn_keeps_the_content_the_model_actually_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The decoded text and calls are what the loop reads; the content is what it replays.

    A 3-series function call carries a thought signature that no provider-neutral field has
    a place for, so the candidate's own `Content` rides back untouched and unread. Asserted
    on identity of the parts rather than on the signature here — that this is the object the
    reply arrived in is the whole property; what it carries is the vendor's business.
    """

    _patch_transport(
        monkeypatch,
        lambda _request: _tool_response(
            {
                "functionCall": {"name": "search_source", "args": {"query": "AudioSink"}},
                "thoughtSignature": base64.b64encode(b"signed").decode(),
            }
        ),
    )
    transport = GoogleChatTransport(_reasoning_config())

    exchange = transport.complete_with_tools(
        _investigation_request(),
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    assert exchange.calls == (ToolCall(name="search_source", arguments={"query": "AudioSink"}),)
    content = exchange.vendor_state
    assert isinstance(content, types.Content)
    assert content.parts is not None
    assert content.parts[0].thought_signature == b"signed"


def test_a_replayed_turn_sends_back_the_signature_the_model_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the vendor attached to a call has to come back with the history.

    Gemini 3 signs its function calls and reads the signature on the next request as proof
    that the reasoning behind the call is the reasoning it is being continued from. Rebuilt
    from a name and an argument mapping the call is unsigned, so the turn is replayed as the
    object it arrived as — and this asserts the signature on the wire, because that is the
    only place the difference shows.
    """

    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _tool_response({"text": "Enough."})

    _patch_transport(monkeypatch, send)
    transport = GoogleChatTransport(_reasoning_config())
    signed = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="search_source", args={"query": "AudioSink"}
                ),
                thought_signature=b"signed",
            )
        ],
    )

    transport.complete_with_tools(
        [
            {"role": "user", "content": "These are the verdicts."},
            AssistantToolTurn(
                text="",
                calls=(ToolCall(name="search_source", arguments={"query": "AudioSink"}),),
                vendor_state=signed,
            ),
            ToolResultTurn(call_name="search_source", content="audio/sink.py:12: write()"),
        ],
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    payload = json.loads(captured[0].content)
    replayed = payload["contents"][1]["parts"][0]
    assert replayed["functionCall"] == {"name": "search_source", "args": {"query": "AudioSink"}}
    assert base64.b64decode(replayed["thoughtSignature"]) == b"signed"


def test_a_turn_from_another_vendor_is_still_rebuilt_from_its_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No vendor state means no signature to replay, and the history still has to travel.

    A turn carrying `None` is the ordinary case everywhere but a Gemini investigation this
    transport itself produced — a fake, another provider's history — and reconstruction is
    what keeps this transport able to continue a conversation it did not start.
    """

    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _tool_response({"text": "Enough."})

    _patch_transport(monkeypatch, send)
    transport = GoogleChatTransport(_reasoning_config())

    transport.complete_with_tools(
        [
            {"role": "user", "content": "These are the verdicts."},
            AssistantToolTurn(
                text="Let me look.",
                calls=(ToolCall(name="search_source", arguments={"query": "AudioSink"}),),
            ),
        ],
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    parts = json.loads(captured[0].content)["contents"][1]["parts"]
    assert parts[0]["text"] == "Let me look."
    assert parts[1]["functionCall"] == {"name": "search_source", "args": {"query": "AudioSink"}}
    assert "thoughtSignature" not in parts[1]


def test_a_reply_with_no_calls_is_how_an_investigation_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty calls is the terminating answer, so text alone must decode cleanly."""

    _patch_transport(
        monkeypatch, lambda _request: _tool_response({"text": "Both sit in one module."})
    )
    transport = GoogleChatTransport(_reasoning_config())

    exchange = transport.complete_with_tools(
        _investigation_request(),
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    assert exchange.calls == ()
    assert exchange.text == "Both sit in one module."


def test_an_unforced_turn_sends_no_calling_mode_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent rather than AUTO: the default already means "the model decides", and a field
    stating the default is a field whose drift nobody would notice."""

    captured: list[httpx.Request] = []

    def send(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return _tool_response({"text": "Enough."})

    _patch_transport(monkeypatch, send)
    transport = GoogleChatTransport(_reasoning_config())

    transport.complete_with_tools(
        _investigation_request(),
        tools=_TOOLS,
        require_call=False,
        task=ReasoningTask.INVESTIGATE_USAGE,
        think=None,
        temperature=None,
    )

    payload = json.loads(captured[0].content)
    assert "toolConfig" not in payload
    assert "tool_config" not in payload


def test_a_reply_with_neither_text_nor_a_call_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read as "done", an empty reply would end an investigation that never happened.

    It surfaces as a `ProviderError` instead, which the loop above degrades into a note
    saying the investigation was abandoned — an honest answer, where a silent stop would
    have the stage report that it looked and found nothing.
    """

    _patch_transport(monkeypatch, lambda _request: _tool_response())
    transport = GoogleChatTransport(_reasoning_config())

    with pytest.raises(ProviderError, match="investigate_usage"):
        transport.complete_with_tools(
            _investigation_request(),
            tools=_TOOLS,
            require_call=False,
            task=ReasoningTask.INVESTIGATE_USAGE,
            think=None,
            temperature=None,
        )


def _models_response(*entries: dict[str, object]) -> httpx.Response:
    return _raw_response({"models": list(entries)})


def test_the_probe_offers_only_the_models_this_advisor_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One key reaches forty-two models and almost all of them report `generateContent`.

    Text-to-speech, image generation and three superseded generations of flash all pass a
    capability filter, which is why there is not one: the set worth judging with is named.
    """

    def listing(request: httpx.Request) -> httpx.Response:
        assert "models" in str(request.url)
        return _models_response(
            {
                "name": "models/gemini-3.6-flash",
                "displayName": "Gemini 3.6 Flash",
                "inputTokenLimit": 1048576,
                "outputTokenLimit": 65536,
                "supportedGenerationMethods": ["generateContent", "countTokens"],
                "thinking": True,
            },
            {
                "name": "models/gemini-2.0-flash",
                "displayName": "Gemini 2.0 Flash",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/gemini-3.1-flash-tts-preview",
                "displayName": "Gemini 3.1 Flash TTS",
                "supportedGenerationMethods": ["generateContent"],
            },
            {
                "name": "models/text-embedding-004",
                "supportedGenerationMethods": ["embedContent"],
            },
        )

    _patch_transport(monkeypatch, listing)
    result = google_adapters.probe_google(_probe_defaults())

    assert result.available
    assert [model.name for model in result.models] == ["gemini-3.6-flash"]
    offered = result.models[0]
    assert offered.label == "Gemini 3.6 Flash"
    assert (offered.input_token_limit, offered.output_token_limit) == (1048576, 65536)


def test_the_thinking_modes_come_from_what_the_listing_says_the_model_can_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`models.list` reports `thinking` per model, and it was declared by hand until it was wrong.

    `gemini-3.5-flash-lite` was offered as non-thinking while the listing reports it as
    thinking. A model the provider says can think is offered both ways; one it says cannot
    is offered as the single row that sends no thinking instruction — not as `False`, which
    would be asking a model that does not reason to stop.
    """

    _patch_transport(
        monkeypatch,
        lambda _request: _models_response(
            {"name": "models/gemini-3.6-flash", "thinking": True},
            {"name": "models/gemini-2.5-pro", "thinking": True},
            {"name": "models/gemini-3.5-flash-lite"},
        ),
    )
    result = google_adapters.probe_google(_probe_defaults())

    assert [(model.name, model.thinking_modes) for model in result.models] == [
        ("gemini-3.6-flash", (True, False)),
        ("gemini-2.5-pro", (True, False)),
        ("gemini-3.5-flash-lite", (None,)),
    ]


def test_a_key_reaching_none_of_the_named_models_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A working key without access to them is a different fault from an unreachable one.

    Reported rather than left as an empty group: a heading saying "google" with nothing
    under it names neither the problem nor the cure.
    """

    _patch_transport(
        monkeypatch,
        lambda _request: _models_response(
            {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]}
        ),
    )
    result = google_adapters.probe_google(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert "gemini-3.6-flash" in result.detail


def test_a_missing_api_key_is_reported_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reason this probe is a function and not a method on a constructed provider.

    Building the transport resolves the key and raises, so a probe reached through one
    could never report the single most likely reason this provider is unusable — and the
    chooser has to render it beside the providers that are working.
    """

    monkeypatch.delenv(_KEY_VARIABLE, raising=False)
    result = google_adapters.probe_google(_probe_defaults())

    assert not result.available
    assert result.models == []
    assert _KEY_VARIABLE in result.detail


def test_a_rejected_key_carries_the_server_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`models.list` authenticates, so this is where a bad key surfaces rather than mid-review."""

    def rejected(_request: httpx.Request) -> httpx.Response:
        return _raw_response(
            {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}},
            status_code=400,
        )

    _patch_transport(monkeypatch, rejected)
    result = google_adapters.probe_google(_probe_defaults())

    assert not result.available
    assert result.detail == "HTTP 400: API key not valid."


def test_the_probe_asks_for_base_models_in_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`query_base` false lists tuned models, and a Pager fetches more pages as it walks.

    Both would be silent: the first empties the chooser, the second turns a two-second
    question into as many round trips as the account has models.
    """

    asked: list[str] = []

    def listing(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return _models_response()

    _patch_transport(monkeypatch, listing)
    google_adapters.probe_google(_probe_defaults())

    assert len(asked) == 1
    assert "pageSize=200" in asked[0]
