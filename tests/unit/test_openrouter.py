"""The hosted boundary: what it offers, what it puts on the wire, and what it keeps of the
answer.

Nothing here talks to OpenRouter. What is worth testing is the part that is ours — which
catalogue rows become choices, the request contract, the embedding join, and the two things
the transport does that the SDK's own client will not: notice an error delivered inside a
200, and keep the one field on a completion that says which endpoint served it.

The wire tests drive a real `ChatOpenAI` over an `httpx.MockTransport` and read the request
it produced. That is the only form that can catch this class of defect: a parameter is
removed from a body by deleting one line, and every test asserting on a helper's return
value goes on passing while the request loses it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from langchain_core.tools import StructuredTool

from archcompass.configuration import ReasoningModelConfig
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    Participant,
    Policy,
    PolicyScope,
    PolicyStrength,
    RepositoryAtlas,
    RepositoryRef,
)
from archcompass.domain.errors import ProviderError
from archcompass.ports.capabilities import ReviewedSubject
from archcompass.ports.policy_retrieval import (
    PolicySelection,
    RetrievalProvenance,
    RetrievedPolicySet,
)
from archcompass.reasoning.adapters import openrouter
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.review_tools import OfferedTools
from archcompass.reasoning.adapters.selected import (
    SelectedLangChainChatModel,
    SelectedLangChainJudge,
)
from archcompass.reasoning.model_catalog import reasoning_config
from archcompass.reasoning.records import model_identity
from archcompass.retrying import is_transient


def _entry(identifier: str, *, parameters: list[str] | None = None, **rest: Any) -> dict[str, Any]:
    return {
        "id": identifier,
        "name": rest.pop("name", identifier),
        "supported_parameters": (
            ["structured_outputs", "tools", "max_tokens"] if parameters is None else parameters
        ),
        **rest,
    }


def _offering(monkeypatch: pytest.MonkeyPatch, *identifiers: str) -> None:
    """Offer exactly these ids for the length of one test.

    `_OFFERED_MODELS` is a product decision — the names this project stands behind — and the
    tests below are about the gates around it rather than about its contents. One that named
    the real list would fail the day somebody added a model, for a reason that has nothing to
    do with what it checks. `test_only_a_named_model_is_offered` is where the real list is
    asserted, and it is the only test here that reads it.
    """

    monkeypatch.setattr(openrouter, "_OFFERED_MODELS", frozenset(identifiers))


def _offered(entries: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(openrouter, "_catalogue", lambda path, key: entries)
    result = openrouter.probe(openrouter.DESCRIPTOR.defaults)
    return [model.name for model in result.models]


def test_a_model_is_offered_for_declaring_what_a_review_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A named model still has to declare what a review needs.

    The two gates are independent and this is the second one. A model can be on the
    allowlist and still be refused: a vendor that drops `structured_outputs` from a row —
    which is how OpenRouter reports an endpoint change — stops being offered without anybody
    editing a list, and that is the half of the old capability filter worth keeping.
    """

    _offering(
        monkeypatch,
        "vendor/judges-fine",
        "vendor/no-schema",
        "vendor/no-tools",
        "vendor/nothing",
    )

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


def test_only_a_named_model_is_offered(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first gate, and the one that reads as a product decision rather than a filter.

    A capable model nobody named is refused. That is the whole change from the capability
    filter this used to be: `vendor/capable` below declares everything a judgement needs and
    is still not offered, because a chooser is a list a person reads and every name on it is
    one somebody stood behind. `reasoning/qualification.py` records what each of them did.

    The real list is asserted here rather than lent, so adding a model is a change that shows
    up in a diff a reviewer reads — which is the point of having one.
    """

    offered = _offered(
        [
            _entry("google/gemini-3.5-flash-lite"),
            _entry("z-ai/glm-5.3-flash"),
            _entry("vendor/capable"),
        ],
        monkeypatch,
    )

    assert offered == ["google/gemini-3.5-flash-lite", "z-ai/glm-5.3-flash"]
    assert sorted(openrouter._OFFERED_MODELS) == [
        "google/gemini-3.5-flash-lite",
        "google/gemini-3.6-flash",
        "z-ai/glm-5.3",
        "z-ai/glm-5.3-flash",
    ]


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

    # On the allowlist deliberately: these guards exist to refuse a shape somebody adds to
    # it by hand, which is the only way one of them can reach `_judgeable` at all now.
    _offering(monkeypatch, identifier, "vendor/real")

    offered = _offered([_entry(identifier), _entry("vendor/real")], monkeypatch)

    assert offered == ["vendor/real"], why


def test_a_models_own_window_reaches_the_chooser(monkeypatch: pytest.MonkeyPatch) -> None:
    """The catalogue knows more than any descriptor could, so it is asked.

    A single `context_window_tokens` on the descriptor cannot describe models spanning four
    thousand tokens to two million, and the four offered already span 1M and 1.3M. Reporting
    each model's own is what lets `ModelCatalogService` clamp an authored budget down to the
    model actually chosen.
    """

    _offering(monkeypatch, "vendor/small")
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

    No endpoint of `google/gemini-3.5-flash-lite` declares `max_completion_tokens` while all
    seven declare `max_tokens`. `ChatOpenAI`'s own field normalises to the first whichever
    name it is given, so the ceiling goes through `extra_body`, which the SDK passes
    verbatim.

    Asserted as the whole `extra_body` rather than as one key, so that a parameter added here
    without a reason written beside it fails a test rather than quietly ranking the endpoints
    differently. `temperature` is the other member of that body; `request_body` argues it.
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

    assert body == {"max_tokens": 8_000, "temperature": 0}


def test_no_provider_routing_preference_is_sent_at_all() -> None:
    """`provider.require_parameters` is gone, and nothing replaced it.

    It was here to turn OpenRouter's soft routing preference into a hard filter. Nothing was
    ever observed to be served by an endpoint that dropped what was asked, so the guarantee
    was never seen to be worth anything — while the filter was observed to remove every
    remaining route and refuse the request outright when an account's own provider policy
    narrowed underneath it.

    `provider` is asserted absent rather than empty, because an empty block is still a
    preference OpenRouter reads, and because nothing here is entitled to weaken the privacy,
    ZDR or provider policy that the account itself sets.
    """

    assert "provider" not in openrouter.request_body(1)
    assert "provider" not in openrouter.request_body(1, "medium")


def test_a_depth_is_sent_only_when_one_was_asked_for() -> None:
    """`None` means the model's own default, and says nothing on the wire to mean it.

    Every parameter in the body narrows the endpoints that can serve the request, so one
    sent to mean "no preference" would be availability spent to say nothing.

    Only `None` earns that silence. This test used to assert it for `False` as well, which
    read as the same decision and was not one: it left "do not reason" and "reason however
    you like" as the same request. A switch is now sent as the ends of the effort scale —
    `request_body` argues the approximation, and `test_provider_conformance.py` asserts on
    the wire that the three states stay three requests.
    """

    assert "reasoning" not in openrouter.request_body(1)
    assert openrouter.request_body(1, True)["reasoning"] == {"effort": "high"}
    assert openrouter.request_body(1, False)["reasoning"] == {"effort": "minimal"}
    assert openrouter.request_body(1, "medium")["reasoning"] == {"effort": "medium"}


def _completion(
    content: str,
    *,
    provider: str | None = "Google AI Studio",
    calls: Sequence[tuple[str, Mapping[str, object]]] = (),
) -> dict[str, Any]:
    """One chat completion, shaped the way OpenRouter answers.

    `provider` is the field this whole exercise turns on: OpenRouter names the endpoint that
    served the request at the top level of the body, beside `model`. `None` builds the body
    a vendor of this API that has no such notion would send, which has to stay readable.

    `calls` makes the completion a turn that asks for tools instead of one that answers,
    which is what a judgement that looks things up actually consists of. The shape is the
    OpenAI one because that is what OpenRouter speaks and what `langchain-openai` parses:
    arguments are a JSON *string*, not an object, and a message carrying tool calls carries
    a null content and a `tool_calls` finish reason.
    """

    message: dict[str, Any] = {"role": "assistant", "content": content or None}
    if calls:
        message["tool_calls"] = [
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
            for index, (name, arguments) in enumerate(calls)
        ]
    body: dict[str, Any] = {
        "id": "gen-1",
        "model": "google/gemini-3.5-flash-lite",
        "object": "chat.completion",
        "created": 1,
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls" if calls else "stop",
                "message": message,
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    if provider is not None:
        body["provider"] = provider
    return body


def _served_over(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Give `build_chat_model` a transport that answers from `handler`.

    The client is built here rather than by monkeypatching a socket, and it installs
    `_RESPONSE_HOOKS` rather than a copy of that list — so a hook added to the real transport
    later is exercised by these tests instead of quietly falling outside the only place that
    watches one run. The single line these tests then do not cover is `http_client`'s own
    `event_hooks=` argument, and it is the same expression.
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    monkeypatch.setattr(
        openrouter,
        "http_client",
        lambda timeout: httpx.Client(
            timeout=timeout,
            transport=httpx.MockTransport(handler),
            event_hooks={"response": list(openrouter._RESPONSE_HOOKS)},
        ),
    )


def test_a_judge_asks_for_greedy_decoding_and_the_request_carries_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole body, asserted as one value, because that is what went wrong.

    `temperature=0` sat in the Ollama branch of `build_chat_model` and nowhere else, so every
    hosted judgement this product has ever made was sampled at whatever the endpoint's default
    is. Nothing failed and nothing said so: the only assertion on the subject was that the
    parameter was absent, which is a test of the helper rather than of the request.

    So this reads the request a real `ChatOpenAI` produced. Asserting the body as a whole
    rather than one key at a time is deliberate in both directions — a parameter silently
    dropped fails here, and so does one smuggled in, which matters on a path where every
    parameter is a routing preference.

    It does not assert that judging is reproducible, and nothing here should. Temperature
    removes a source of variance from each token; the loop's variance is a sampled tool call
    at the end of a sampled reasoning trace, and no parameter in this body reaches that.
    """

    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(cast("dict[str, Any]", json.loads(request.content)))
        return httpx.Response(200, json=_completion("ready"))

    _served_over(handler, monkeypatch)
    config = reasoning_config(openrouter.DESCRIPTOR, "google/gemini-3.5-flash-lite", "medium")

    build_chat_model(config).invoke("judge this")

    assert sent == {
        "messages": [{"content": "judge this", "role": "user"}],
        "model": "google/gemini-3.5-flash-lite",
        "stream": False,
        "max_tokens": config.max_output_tokens,
        "temperature": 0,
        "reasoning": {"effort": "medium"},
    }


def test_no_sampling_parameter_is_sent_that_temperature_has_already_settled() -> None:
    """`top_p` and `seed` are absent, and their absence is a decision rather than an omission.

    Every parameter in this body is a routing preference, so one that says nothing ranks the
    endpoints for nothing. At temperature 0 `top_p` chooses from a distribution that has
    collapsed onto a single token. `seed` is the parameter to reach for if the record shows
    this model family ignores `temperature` — `Finding.served_by` is what will show it — and
    until then it is declared by fewer endpoints while buying no more reproducibility.
    """

    body = openrouter.request_body(1, "medium")

    assert "top_p" not in body
    assert "seed" not in body


def test_the_endpoint_that_answered_is_kept_off_a_body_nothing_else_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hook, on its own, because it is the only place the field ever exists.

    `langchain-openai` builds `response_metadata` from a fixed set of keys and `provider` is
    not one of them, so a completion that arrives naming "Google AI Studio" reaches the
    application as an `AIMessage` that cannot say where it came from. Asserted here as well:
    a body from a vendor of this API with no such notion records nothing rather than
    something empty, and a body arriving with nothing recording records nothing at all.
    """

    def answered(provider: str | None) -> httpx.Response:
        return httpx.Response(
            200,
            json=_completion("ready", provider=provider),
            headers={"content-type": "application/json"},
        )

    with openrouter.observed_route() as route:
        openrouter._observe_route(answered("Google AI Studio"))
        openrouter._observe_route(answered("Vertex"))
        openrouter._observe_route(answered("Google AI Studio"))
        openrouter._observe_route(answered(None))

    # First seen first, each endpoint once: a judgement that made twenty-six calls to one
    # endpoint must not store that name twenty-six times in a field a person reads.
    assert route.served_by == "Google AI Studio,Vertex"

    # Outside a record there is nothing to write into, and that has to be silent rather than
    # fatal: the same transport carries the catalogue probe and the embedding calls.
    openrouter._observe_route(answered("Google AI Studio"))


def _judged(tmp_path: Path) -> tuple[Candidate, ArchitectureCase, RetrievedPolicySet]:
    candidate = Candidate.identified(
        pattern="sole_implementation",
        summary="Port has one implementation",
        participants=(Participant("Port", "interface"),),
    )
    policy = Policy(
        "policy-a",
        "Delay abstraction",
        "Keep a boundary only when it hides meaningful variation.",
        PolicyScope.GENERAL,
        PolicyStrength.GUIDANCE,
        "hash-a",
    )
    del tmp_path
    return (
        candidate,
        ArchitectureCase.create(),
        RetrievedPolicySet(
            str(candidate.id),
            (PolicySelection(policy),),
            RetrievalProvenance(candidate.id, "test", "1", "corpus", (policy.id,)),
        ),
    )


class _Selected:
    """A workspace whose selected model is this hosted one, as the transport reads it."""

    def __init__(self, config: ReasoningModelConfig) -> None:
        self._config = config

    def current(self) -> ReasoningModelConfig:
        return self._config

    def record_failure(self, detail: str) -> None:
        raise AssertionError(f"nothing here reaches OpenRouter: {detail}")


def test_a_finding_records_every_endpoint_that_served_the_judgement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The record that turns the open question in the diagnosis into a query.

    One candidate's verdict swung cleared → material → cleared → material across four
    revisions of one branch on byte-identical input, and nothing stored could say whether the
    cause was the sampler or which of `google/gemini-3.5-flash-lite`'s seven endpoints
    answered. `model_identity` is the same string either way. Now the finding carries the
    answer the gateway itself gave.

    Two calls in one judgement, and both endpoints on the finding, because that is the case
    a simpler record gets wrong: the first answer here fails the schema, `structured_output`
    asks once more, and the gateway routes the second request somewhere else. Keeping only
    the last would report a judgement as served by "Vertex" when half of it was not.

    Offline throughout — the transport is a mock and the two bodies are written here.
    """

    answers = iter(
        [
            (_completion(json.dumps({"verdict": "definitely"}), provider="Google AI Studio")),
            (
                _completion(
                    json.dumps(
                        {
                            "verdict": "cleared",
                            "reasoning": "The boundary earns its keep.",
                            "policy_bearings": [
                                {"policy_id": "policy-a", "reasoning": "It applies."}
                            ],
                        }
                    ),
                    provider="Vertex",
                )
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=next(answers))

    _served_over(handler, monkeypatch)
    config = reasoning_config(openrouter.DESCRIPTOR, "google/gemini-3.5-flash-lite", None)
    judge = SelectedLangChainJudge(SelectedLangChainChatModel(cast("Any", _Selected(config))))
    candidate, case, policies = _judged(tmp_path)

    finding = judge.judge(candidate, case, policies)

    assert finding.served_by == "Google AI Studio,Vertex"
    # The provenance beside it is unaffected: which endpoint answered is not part of what the
    # judgement was asked, and nothing that compares two judgements may start reading it.
    assert finding.model_identity == model_identity(config)


def test_a_provider_with_one_endpoint_records_nothing_rather_than_something(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty is the answer for Ollama and for the deterministic stand-in, and it is stored.

    A local runner has no endpoint to name and no gateway choosing between several, so there
    is nothing true to put here. The field has to read as absent rather than as a route
    somebody could compare, which is also what every finding stored before the field existed
    reads as.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json=_completion(
                json.dumps(
                    {
                        "verdict": "cleared",
                        "reasoning": "The boundary earns its keep.",
                        "policy_bearings": [{"policy_id": "policy-a", "reasoning": "It applies."}],
                    }
                ),
                provider=None,
            ),
        )

    _served_over(handler, monkeypatch)
    config = reasoning_config(openrouter.DESCRIPTOR, "google/gemini-3.5-flash-lite", None)
    judge = SelectedLangChainJudge(SelectedLangChainChatModel(cast("Any", _Selected(config))))
    candidate, case, policies = _judged(tmp_path)

    finding = judge.judge(candidate, case, policies)

    assert finding.served_by == ""


def test_two_judgements_in_flight_at_once_keep_their_routes_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shape a review actually runs in, and the one a simpler record gets wrong.

    The graph dispatches every selected candidate at once — forty-six of them is an ordinary
    number for a real repository — and all of those branches judge through one
    `SelectedLangChainJudge` over one `httpx.Client`. So the obvious place to hang "which
    endpoint answered", an attribute on the transport or on the judge, is shared by every
    judgement in flight, and the value it holds when a branch finishes is whatever answered
    last anywhere. That is wrong exactly when a review is busy, which is the only time the
    field is interesting. This test fails against that design and passes against the
    `ContextVar` in `openrouter`.

    The barrier is what makes it a test of isolation rather than of sequencing: neither
    request is answered until both are on the wire, so the two judgements genuinely overlap
    rather than happening to take turns. Each thread is handed its own endpoint, and each
    finding must come back naming one endpoint — its own — rather than two, or the other's.

    Offline: the transport is a mock, the two bodies are written here, and the only thing
    concurrent is this process.
    """

    both_in_flight = threading.Barrier(2, timeout=30)
    endpoints = iter(("Google AI Studio", "Vertex"))
    routed: dict[int, str] = {}
    handing_out = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        with handing_out:
            endpoint = routed.setdefault(threading.get_ident(), next(endpoints))
        both_in_flight.wait()
        return httpx.Response(
            200,
            json=_completion(
                json.dumps(
                    {
                        "verdict": "cleared",
                        "reasoning": "The boundary earns its keep.",
                        "policy_bearings": [{"policy_id": "policy-a", "reasoning": "It applies."}],
                    }
                ),
                provider=endpoint,
            ),
        )

    _served_over(handler, monkeypatch)
    config = reasoning_config(openrouter.DESCRIPTOR, "google/gemini-3.5-flash-lite", None)
    judge = SelectedLangChainJudge(SelectedLangChainChatModel(cast("Any", _Selected(config))))
    first = _judged(tmp_path)
    second = _judged(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as branches:
        findings = list(branches.map(lambda judged: judge.judge(*judged), (first, second)))

    # One name each, and not the same name: a leak in either direction shows up here as a
    # comma-joined pair or as two findings claiming the same endpoint.
    assert sorted(finding.served_by for finding in findings) == ["Google AI Studio", "Vertex"]


class _Grep:
    """A toolbox offering one tool, so a judgement really runs the gathering loop."""

    def for_review(self, repository: RepositoryRef, atlas: RepositoryAtlas) -> OfferedTools:
        del repository, atlas

        def grep(pattern: str) -> str:
            del pattern
            return "src/sinks.py:12: class FileSink"

        return OfferedTools(
            tools=(
                StructuredTool.from_function(
                    func=grep,
                    name="grep",
                    description="Search the reviewed source.",
                    args_schema={
                        "type": "object",
                        "properties": {"pattern": {"type": "string"}},
                        "required": ["pattern"],
                        "additionalProperties": False,
                    },
                ),
            )
        )


def test_the_route_is_seen_from_inside_the_gathering_loop_as_well(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The production path, which is the one every other test here goes around.

    A hosted judgement is a `DeepArchitectureJudge` running a LangGraph agent, and every
    request it makes is made from inside that graph rather than from the frame that opened
    `observed_route`. The record is a `ContextVar`, so this asserts the assumption the whole
    design rests on: LangGraph copies the calling context into the tasks it schedules, the
    copy carries the same mutable record, and a completion arriving three frames down is
    written into the record the judgement will read when it returns. If that were false,
    `served_by` would be silently empty for every hosted judgement that used a tool — which
    is most of them, and exactly the ones worth knowing the route of.

    The script is a real gathering: the model asks for a grep, the tool runs, and the second
    turn answers with the structured verdict. The gateway routes the two requests to
    different endpoints, as it is free to do, and the finding names both.

    Offline: an `httpx.MockTransport`, two bodies written here, and a tool that reads
    nothing.
    """

    answers = iter(
        [
            _completion("", provider="Google AI Studio", calls=[("grep", {"pattern": "Sink"})]),
            _completion(
                "",
                provider="Vertex",
                calls=[
                    (
                        "FindingOutput",
                        {
                            "verdict": "cleared",
                            "reasoning": "The boundary earns its keep.",
                            "policy_bearings": [
                                {"policy_id": "policy-a", "reasoning": "It applies."}
                            ],
                        },
                    )
                ],
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(200, json=next(answers))

    _served_over(handler, monkeypatch)
    config = reasoning_config(openrouter.DESCRIPTOR, "google/gemini-3.5-flash-lite", None)
    judge = SelectedLangChainJudge(
        SelectedLangChainChatModel(cast("Any", _Selected(config))), cast("Any", _Grep())
    )
    candidate, case, policies = _judged(tmp_path)
    repository = RepositoryRef("repo", tmp_path, "branch", "content")
    subject = ReviewedSubject(repository=repository, atlas=RepositoryAtlas("atlas", repository))

    finding = judge.judge(candidate, case, policies, subject=subject)

    # The loop really ran — a judgement that fell through to the toolless branch would name
    # one endpoint and would prove nothing about where the record can be seen from.
    assert [item.tool for item in subject.lookups] == ["grep"]
    assert finding.served_by == "Google AI Studio,Vertex"


def test_a_model_that_cannot_reason_offers_only_its_own_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The depths offered are the model's claim, not this provider's."""

    _offering(monkeypatch, "vendor/thinks", "vendor/plain")

    reasoning = openrouter._judgeable(
        {
            "id": "vendor/thinks",
            "supported_parameters": [*openrouter._REQUIRED_CAPABILITIES, "reasoning"],
        }
    )
    plain = openrouter._judgeable(
        {"id": "vendor/plain", "supported_parameters": list(openrouter._REQUIRED_CAPABILITIES)}
    )

    assert reasoning is not None and plain is not None
    assert reasoning.thinking_modes == (None, "minimal", "low", "medium", "high")
    assert plain.thinking_modes == (None,)


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
    embedder = openrouter.OpenRouterEmbeddings(api_key="k", model="vendor/embed", dimensions=8)
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


def _http_response(
    status: int, body: bytes, content_type: str = "application/json"
) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        headers={"content-type": content_type},
        content=body,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )


def test_a_rate_limit_hidden_in_a_200_body_is_still_a_rate_limit() -> None:
    """The failure this transport exists for, end to end.

    OpenRouter reports anything that goes wrong mid-generation in the body, because the
    request did reach a provider. The body then has an `error` and no `choices`, the SDK
    iterates `choices` while parsing, and the review dies on
    `TypeError: 'NoneType' object is not iterable` — no status, no phrase, so `is_transient`
    reads it as permanent and a four-second wait becomes a lost review.
    """

    inline = _http_response(200, b'{"error": {"code": 429, "message": "Rate limit exceeded"}}')

    with pytest.raises(openrouter.InlineProviderError) as refused:
        openrouter._raise_inline_error(inline)

    assert "Rate limit exceeded" in str(refused.value)
    assert is_transient(refused.value), "a 429 in the body must be waited on"


def test_a_permanent_error_in_a_200_body_is_not_waited_on() -> None:
    """The same interception must not turn every refusal into a retry loop."""

    inline = _http_response(200, b'{"error": {"code": 402, "message": "Insufficient credits"}}')

    with pytest.raises(openrouter.InlineProviderError) as refused:
        openrouter._raise_inline_error(inline)

    assert not is_transient(refused.value)
    assert isinstance(refused.value, ProviderError), "the domain type every caller catches"


def test_an_error_with_no_code_still_stops_the_parse() -> None:
    """A body that is an error is not a completion, whether or not it says how."""

    inline = _http_response(200, b'{"error": {"message": "something went wrong upstream"}}')

    with pytest.raises(openrouter.InlineProviderError, match="something went wrong upstream"):
        openrouter._raise_inline_error(inline)


def test_an_ordinary_completion_passes_through_untouched() -> None:
    body = b'{"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}'

    openrouter._raise_inline_error(_http_response(200, body))


def test_a_real_error_status_is_left_to_the_sdk() -> None:
    """A 429 in the status line already works; intercepting it would only reword it."""

    openrouter._raise_inline_error(
        _http_response(429, b'{"error": {"code": 429, "message": "slow down"}}')
    )


def test_a_stream_is_never_read_here() -> None:
    """Reading the body in the hook would consume the stream.

    ArchCompass does not stream a structured call, and this guard is what keeps that from
    becoming a rule somebody has to remember rather than one the code holds.
    """

    openrouter._raise_inline_error(
        _http_response(200, b"data: {}\n\n", content_type="text/event-stream")
    )


def test_a_body_that_was_served_and_then_errored_still_names_who_served_it() -> None:
    """The order of `_RESPONSE_HOOKS`, over the case that order was chosen for.

    Both hooks read the same body and only one of them is allowed to end the request, so
    which runs first is a decision rather than a listing. `_raise_inline_error` raises out
    of the hook chain: put it first and every hook after it is skipped for exactly the
    responses where something went wrong. Those are the responses whose route is worth most
    — a judgement that failed mid-generation is the one where "which of the seven endpoints
    answered" is a question somebody will actually ask — so recording has to happen before
    refusing, and nothing else in this file makes that ordering fail when it is reversed.

    Driven through a real `httpx.Client` over a mock transport, reaching for
    `_RESPONSE_HOOKS` itself rather than naming the two hooks here, for the reason
    `_served_over` gives: a hook added later is then covered by this ordering rather than
    quietly outside it.

    The body is the shape OpenRouter sends when a provider accepted the request and then
    failed part way through producing output — `provider` at the top level beside an
    `error` object, and no `choices` at all, because there is no completion to carry.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "provider": "Google AI Studio",
                "model": "google/gemini-3.5-flash-lite",
                "error": {"code": 429, "message": "Rate limit exceeded"},
            },
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        event_hooks={"response": list(openrouter._RESPONSE_HOOKS)},
    )

    with (
        openrouter.observed_route() as route,
        pytest.raises(openrouter.InlineProviderError) as refused,
    ):
        client.post(f"{openrouter.BASE_URL}/chat/completions", json={})

    # The refusal still carries what the body claimed, so the retry layer waits on it. Both
    # things have to be true at once: recording first must not cost the interception.
    assert is_transient(refused.value), "a 429 in the body must still be waited on"
    assert route.served_by == "Google AI Studio"


def test_the_client_carries_the_hook_and_the_timeout() -> None:
    client = openrouter.http_client(12.5)

    assert openrouter._raise_inline_error in client.event_hooks["response"]
    assert client.timeout.read == 12.5


def test_the_embedding_catalogue_offers_only_what_is_being_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discovery is the live listing intersected with the widths this build knows.

    Both halves matter. The listing alone would offer a model whose width nothing here can
    supply, and the index keys on an exact width; the table alone would offer one OpenRouter
    has since withdrawn, which fails on the first review that picks it.
    """

    monkeypatch.setattr(
        openrouter,
        "_catalogue",
        lambda path, key: [
            {"id": "google/gemini-embedding-2", "name": "Gemini Embedding 2"},
            {"id": "some/model-we-have-no-width-for", "name": "Unknown"},
        ],
    )

    offered = openrouter.embedding_candidates("test-key")

    assert offered == (("google/gemini-embedding-2", 3072, "Gemini Embedding 2"),)


def test_an_embedding_model_withdrawn_upstream_leaves_the_chooser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(openrouter, "_catalogue", lambda path, key: [])

    assert openrouter.embedding_candidates("test-key") == ()


def test_the_refusal_a_real_transport_produces_is_the_one_that_is_recognised() -> None:
    """The whole path, because every layer of it renames the failure.

    OpenRouter answers 404, `openai` makes it `NotFoundError`, and `langchain-openai` makes
    that `OpenAIModelNotFoundError` — a name saying the model does not exist, for a model
    that does. This asserts against what those layers actually produce rather than against a
    stand-in, because the stand-in is the part that cannot go stale when they change.
    """

    from langchain_openai import ChatOpenAI

    from archcompass.domain.errors import NoEligibleProviderError
    from archcompass.retrying import call_with_retry

    refusal = {
        "error": {
            "message": (
                "No endpoints available matching your guardrail restrictions and data "
                "policy. Configure: https://openrouter.ai/settings/privacy"
            ),
            "code": 404,
        }
    }
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json=refusal))
    model = ChatOpenAI(
        model="openai/gpt-5.6-luna-pro",
        api_key=cast("Any", "test-key"),
        base_url=openrouter.BASE_URL,
        http_client=httpx.Client(transport=transport),
        max_retries=0,
    )

    with pytest.raises(NoEligibleProviderError) as failure:
        call_with_retry(
            lambda: model.invoke("judge this"),
            subject="Judging a candidate",
            sleep=lambda _: None,
        )

    assert "guardrail restrictions and data policy" in str(failure.value)
    # The model is not what was missing, so nothing here should send a reader to the picker.
    assert "not a valid model" not in str(failure.value)


def test_an_unknown_model_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """Measured: OpenRouter answers an unknown model id with **400**, not 404.

    Which is why a 404 from that chat endpoint can be read as a routing refusal without
    shadowing a genuine missing model — there is no genuine missing model at that status.
    """

    from archcompass.retrying import ineligible_reason

    invalid = ValueError(
        "Error code: 400 - {'error': {'message': "
        "'openai/nope-does-not-exist is not a valid model ID', 'code': 400}}"
    )

    assert ineligible_reason(invalid) is None
