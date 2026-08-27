"""Every provider puts what the configuration asked for on the wire, read off the wire.

`build_chat_model` branches per provider and the branches take their parameters by
completely different routes — OpenRouter through `extra_body=openrouter.request_body(...)`,
Ollama as native constructor kwargs. Until this file, nothing asserted that either branch
honoured `ReasoningModelConfig` at all. That is how `temperature` came to be absent from
every hosted judgement this product ever made: it sat visible in the Ollama branch and its
absence next door read as deliberate.

So the shape here is a conformance suite rather than a test per provider. It is parametrised
over the registered `ProviderDescriptor`s, and `test_every_registered_provider_is_covered`
fails the moment one appears that nothing below describes — a provider added tomorrow is
covered because the suite refuses to pass without it, not because somebody remembered.

Each case builds the real model, sends one real request through an `httpx.MockTransport`,
and reads the body that left. Nothing is stubbed above the socket: the real
`openrouter.http_client` runs with its real response hooks, and the real `ollama` client
serialises the real `ChatOllama` parameters. A helper's return value is not what any of this
asserts, because a parameter is removed from a request by deleting one line and every test
that reads a helper goes on passing while the request loses it.

**What this file does not claim.** It asserts what leaves ArchCompass, and nothing about what
the vendor then does with it. `docs/frontend-plan.md` records that `gemini-3.5-flash-lite`
and `gemini-3.6-flash` fix their own sampling and discarded `temperature` with a warning on
every call — observed against Google's *native* API, which this product no longer reaches,
and never re-verified through OpenRouter. A green run here means the parameter was sent. It
does not mean it was honoured, and no offline test can mean that.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

import httpx
import pytest

from archcompass.bootstrap import _ALL_PROVIDERS
from archcompass.configuration import ReasoningModelConfig
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.adapters import openrouter
from archcompass.reasoning.adapters.factory import build_chat_model
from archcompass.reasoning.adapters.providers import (
    DETERMINISTIC_DESCRIPTOR,
    DETERMINISTIC_MODEL,
    OLLAMA_DESCRIPTOR,
)
from archcompass.reasoning.model_catalog import reasoning_config
from archcompass.reasoning.ports import ProviderDescriptor
from archcompass.records import ThinkingMode

#: The one prompt every case sends, so a body can be asserted whole.
PROMPT: Final = "judge this"


class _Sentinel:
    """A stand-in that names itself in a failure message instead of printing as `<object>`."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name


#: The parameter was not in the request. Every reader below returns this rather than raising,
#: because "nothing was sent" is the answer three of these tests are asking for.
ABSENT: Final = _Sentinel("<not in the request>")

#: The same absence, asserted for a different reason, and the reason is the whole point of
#: giving it a second name. `context_window_tokens` does not mean one thing across providers:
#: on Ollama it is `num_ctx`, which the runner allocates before it answers anything, so it
#: is genuinely a request parameter; on a hosted API there is no such field to send. The
#: number still does work there — `ReasoningModelConfig.output_fits_context_window` validates
#: against it and `ModelCatalogService` clamps it down to each model's own window — but none
#: of that work is on the wire. Named so this reads as a decision rather than as a provider
#: quietly skipped.
NO_SUCH_REQUEST_PARAMETER: Final = ABSENT


@dataclass(frozen=True, slots=True)
class SentParameters:
    """What one request said about each thing `ReasoningModelConfig` can ask for.

    One record across providers, filled in from each provider's own spelling, so the
    assertions below can be written once and read as a contract rather than as two lists of
    vendor keys that happen to sit in the same file.
    """

    model: object
    #: Whatever the provider was told about reasoning, in its own shape — `{"effort": ...}`
    #: on OpenRouter, a bool or a level under `think` on Ollama. Kept raw rather than
    #: normalised to a `ThinkingMode`, because normalising is what an adapter is supposed to
    #: do and a test that did it too could not see an adapter that had stopped.
    thinking: object
    temperature: object
    max_output_tokens: object
    context_window_tokens: object


def _openrouter_sent(body: Mapping[str, object]) -> SentParameters:
    """OpenRouter's spelling. `max_tokens`, not `max_completion_tokens` — `request_body` says
    why, and the difference is which of a model's endpoints can serve the request."""

    return SentParameters(
        model=body.get("model", ABSENT),
        thinking=body.get("reasoning", ABSENT),
        temperature=body.get("temperature", ABSENT),
        max_output_tokens=body.get("max_tokens", ABSENT),
        context_window_tokens=ABSENT,
    )


def _ollama_sent(body: Mapping[str, object]) -> SentParameters:
    """Ollama's spelling. The decoding parameters live under `options`; `think` does not."""

    raw = body.get("options")
    options: Mapping[str, object] = (
        cast("Mapping[str, object]", raw) if isinstance(raw, dict) else {}
    )
    return SentParameters(
        model=body.get("model", ABSENT),
        thinking=body.get("think", ABSENT),
        temperature=options.get("temperature", ABSENT),
        max_output_tokens=options.get("num_predict", ABSENT),
        context_window_tokens=options.get("num_ctx", ABSENT),
    )


def _openrouter_answers(request: httpx.Request) -> httpx.Response:
    """One completion, shaped the way OpenRouter answers, so `langchain-openai` can parse it.

    No top-level `error`, because `openrouter._raise_inline_error` runs for real on this
    path and a body carrying one would be turned into an exception before the SDK saw it.
    """

    del request
    return httpx.Response(
        200,
        json={
            "id": "gen-1",
            "object": "chat.completion",
            "created": 1,
            "model": "google/gemini-3.5-flash-lite",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "ready"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


def _ollama_answers(request: httpx.Request) -> httpx.Response:
    """Two NDJSON chunks, because `ChatOllama` streams even when asked to `invoke`.

    `done_reason` is `stop` rather than `load`: `langchain-ollama` discards a `load` chunk,
    and a stream of nothing but discarded chunks raises "No data received from Ollama
    stream" instead of returning the message this test then never inspects.
    """

    del request
    chunks = (
        {
            "model": "qwen3.8:27b",
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": "ready"},
            "done": False,
        },
        {
            "model": "qwen3.8:27b",
            "created_at": "2026-01-01T00:00:00Z",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "total_duration": 1,
            "prompt_eval_count": 1,
            "eval_count": 1,
        },
    )
    return httpx.Response(
        200, content=b"\n".join(json.dumps(chunk).encode("utf-8") for chunk in chunks)
    )


@dataclass(frozen=True, slots=True)
class WireContract:
    """One provider, and everything needed to read a request it produced.

    `expects` and `whole_body` are the specification, written out in the provider's own keys.
    They restate the adapter rather than calling it, deliberately: a test that asked
    `request_body` what it would send could not notice `request_body` sending the wrong
    thing.
    """

    descriptor: ProviderDescriptor
    model: str
    answers: Callable[[httpx.Request], httpx.Response]
    reads: Callable[[Mapping[str, object]], SentParameters]
    expects: Callable[[ReasoningModelConfig], SentParameters]
    whole_body: Callable[[ReasoningModelConfig], Mapping[str, object]]


def _openrouter_expects(config: ReasoningModelConfig) -> SentParameters:
    """What a request must carry, given a configuration, on the hosted path.

    The thinking mode maps onto the ends of OpenRouter's effort scale where it arrives as a
    switch: `True` is `high` and `False` is the floor, `minimal`. That mapping is not
    invented here — `ReasoningModelConfig.thinking` and `_thinking_mode` in the CLI both
    state it, and until it was implemented both statements were false.
    """

    effort: object
    if config.thinking is None:
        effort = ABSENT
    elif isinstance(config.thinking, bool):
        effort = {"effort": "high" if config.thinking else "minimal"}
    else:
        effort = {"effort": config.thinking}
    return SentParameters(
        model=config.model,
        thinking=effort,
        temperature=0,
        max_output_tokens=config.max_output_tokens,
        # Nothing on this request describes the context window, and that is the correct
        # request rather than a missing parameter.
        context_window_tokens=NO_SUCH_REQUEST_PARAMETER,
    )


def _ollama_expects(config: ReasoningModelConfig) -> SentParameters:
    """What a request must carry on the local path.

    `think` is the switch itself, so all three states go across as themselves and `None`
    goes across as nothing — the ollama client dumps its request with `exclude_none=True`.

    `num_ctx` is the one place `context_window_tokens` is a request parameter, and it is a
    memory allocation rather than a budget: `OLLAMA_DESCRIPTOR` chose 64k from what this
    product actually sends, because a runner asked for more takes it out of the card before
    it answers anything.
    """

    return SentParameters(
        model=config.model,
        thinking=ABSENT if config.thinking is None else config.thinking,
        temperature=0.0,
        max_output_tokens=config.max_output_tokens,
        context_window_tokens=config.context_window_tokens,
    )


def _openrouter_whole_body(config: ReasoningModelConfig) -> Mapping[str, object]:
    """The complete request, so a parameter smuggled in fails as loudly as one dropped.

    That direction matters more here than on most paths. Every parameter in this body is a
    routing preference OpenRouter matches against the endpoints that could serve the
    request, so an idle one costs a worse route. `provider` is the key this is really
    watching: `provider.require_parameters` was removed after it 404'd a whole experiment,
    and nothing is entitled to put a routing pin back without an argument.
    """

    return {
        "model": config.model,
        "messages": [{"content": PROMPT, "role": "user"}],
        "stream": False,
        "max_tokens": config.max_output_tokens,
        "temperature": 0,
        "reasoning": {"effort": "high"},
    }


def _ollama_whole_body(config: ReasoningModelConfig) -> Mapping[str, object]:
    """The complete request, including the two keys nothing here chose.

    `stream` is true because `ChatOllama` aggregates a stream even for `invoke`, and `tools`
    is an empty list because the ollama client sends the list it was handed rather than
    omitting it. Both are asserted rather than filtered out: they are what goes on the wire,
    and a test that hid them would be describing a request this product does not make.
    """

    return {
        "model": config.model,
        "messages": [{"content": PROMPT, "role": "user"}],
        "stream": True,
        "think": True,
        "tools": [],
        "options": {
            "temperature": 0.0,
            "num_ctx": config.context_window_tokens,
            "num_predict": config.max_output_tokens,
        },
    }


#: Every provider `build_chat_model` builds a model for, with the model this suite drives it
#: with. The OpenRouter model is the one the adapter's own comments are measured against;
#: the Ollama model is the one `OLLAMA_MODELS` recommends.
WIRE_CONTRACTS: Final[dict[str, WireContract]] = {
    openrouter.DESCRIPTOR.name: WireContract(
        descriptor=openrouter.DESCRIPTOR,
        model="google/gemini-3.5-flash-lite",
        answers=_openrouter_answers,
        reads=_openrouter_sent,
        expects=_openrouter_expects,
        whole_body=_openrouter_whole_body,
    ),
    OLLAMA_DESCRIPTOR.name: WireContract(
        descriptor=OLLAMA_DESCRIPTOR,
        model="qwen3.8:27b",
        answers=_ollama_answers,
        reads=_ollama_sent,
        expects=_ollama_expects,
        whole_body=_ollama_whole_body,
    ),
}

#: Providers that deliberately build no chat model, and so have no wire to conform to. The
#: deterministic stand-in reasons in-process; `build_chat_model` refuses it by name and
#: `SelectedLangChainChatModel` relies on that refusal rather than testing the provider
#: itself. Listed rather than skipped so the coverage test below can tell "no wire" from
#: "nobody wrote one".
NO_CHAT_MODEL: Final[dict[str, ProviderDescriptor]] = {
    DETERMINISTIC_DESCRIPTOR.name: DETERMINISTIC_DESCRIPTOR,
}

_CASES: Final = tuple(
    pytest.param(contract, id=name) for name, contract in WIRE_CONTRACTS.items()
)


def _capture(
    contract: WireContract, thinking: ThinkingMode, monkeypatch: pytest.MonkeyPatch
) -> tuple[ReasoningModelConfig, Mapping[str, object]]:
    """Build the model this configuration asks for, send one request, return what left.

    The transport is replaced at `httpx.HTTPTransport`, which is the lowest point both
    providers pass through and the only one they share: `ChatOpenAI` is handed
    `openrouter.http_client(...)` and `ChatOllama` builds an `ollama.Client` that builds its
    own `httpx.Client`, and neither offers a seam above this. Patching here means every line
    of both branches runs for real — including `http_client`'s response hooks, which the
    older `_served_over` helper in `test_openrouter.py` has to reinstall by hand because it
    replaces the client instead.
    """

    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-key")
    seen: list[Mapping[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(cast("Mapping[str, object]", json.loads(request.content)))
        return contract.answers(request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx.HTTPTransport,
        "handle_request",
        lambda _self, request: transport.handle_request(request),
    )

    config = reasoning_config(contract.descriptor, contract.model, thinking)
    build_chat_model(config).invoke(PROMPT)

    assert len(seen) == 1, f"one invocation should be one request, not {len(seen)}"
    return config, seen[0]


def test_every_registered_provider_is_covered() -> None:
    """A provider added to the registry is covered here, or this suite stops passing.

    Read off `_ALL_PROVIDERS` rather than `enabled_providers()` on purpose. The second is the
    deployment's filtered view, so a suite parametrised over it would quietly stop covering
    Ollama the moment `ARCHCOMPASS_PROVIDERS` named only the hosted one — coverage that
    depends on an environment variable is coverage nobody can rely on.

    This is also the answer to the second dispatch table. `ProviderDescriptor` says adding a
    provider is "adding a module and naming it once in the composition root", and
    `build_chat_model` is a second place that has to be edited too — forgetting it gives a
    runtime `ConfigurationError`, not a type error. Nothing in the type system catches that.
    This does, at the cost of one assertion.
    """

    described = set(WIRE_CONTRACTS) | set(NO_CHAT_MODEL)

    assert described == set(_ALL_PROVIDERS), (
        f"providers described here but not registered: {described - set(_ALL_PROVIDERS)}; "
        f"registered but not described: {set(_ALL_PROVIDERS) - described}. A new provider "
        "needs a WireContract, or a line in NO_CHAT_MODEL saying why it has no wire."
    )
    assert not set(WIRE_CONTRACTS) & set(NO_CHAT_MODEL), (
        "a provider cannot both have a wire contract and have no chat model"
    )


@pytest.mark.parametrize("contract", _CASES)
@pytest.mark.parametrize(
    "thinking", [True, False, None], ids=["thinking-true", "thinking-false", "thinking-absent"]
)
def test_a_request_carries_what_the_configuration_asked_for(
    contract: WireContract, thinking: ThinkingMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole normalised record, per provider, in each of the three thinking states.

    Asserted as one value rather than field by field so that a parameter which stops being
    sent fails here even though nothing was asserting on it individually — which is exactly
    how `temperature` was lost on the hosted path.

    The output budget is read back off the configuration rather than written down, because
    `reasoning_config` chooses between `max_output_tokens` and `max_output_tokens_thinking`
    by the mode; what is being asserted is that whichever number it chose is the number that
    went, not what the number should be. `test_model_catalog.py` owns the choice.
    """

    config, body = _capture(contract, thinking, monkeypatch)

    assert contract.reads(body) == contract.expects(config)


@pytest.mark.parametrize("contract", _CASES)
def test_the_three_thinking_states_reach_the_wire_as_three_instructions(
    contract: WireContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`true`, `false` and absent must be three requests, not one.

    This is the assertion the abstraction actually turns on. `ReasoningModelConfig.thinking`
    is the specification: "an adapter owes all three however its own API spells them. `true`
    in particular must reach the provider as an instruction and never decay into absence: a
    request that says nothing gets the model's default, and defaults are a property of the
    model rather than of the API."

    It was broken on the hosted path and passing on the local one, which is what made it
    worth writing as one test over both. `openrouter.request_body` sent `reasoning` only for
    a `str`, so nothing the switch chose reached the provider as reasoning at all. Measured on
    the parent commit, the three settings produced `{"max_tokens": 32768}` for `on`,
    `{"max_tokens": 16384}` for `off` and `{"max_tokens": 32768}` for absent: `on` and absent
    were byte-identical, and `off` was told apart only by its budget, because
    `_spends_little_on_thinking` reads `False` as a mode that spends little. Three settings,
    two instructions about budget, none about reasoning — and the model's own default every
    time.

    Only the thinking field is compared here, and that is what makes the three assertions
    below mean what they say. A difference in a budget is not the provider being told anything
    about reasoning: the same three broken bodies, compared whole, satisfy two of these three
    pairs, so a whole-body version of this test would have reported the switch working while
    every request said nothing about reasoning at all.
    """

    said = {
        state: contract.reads(_capture(contract, state, monkeypatch)[1]).thinking
        for state in (True, False, None)
    }

    assert said[True] != said[None], (
        f"{contract.descriptor.name}: thinking=True decayed into the same request as asking "
        f"for nothing ({said[True]!r}); the model gets its own default either way"
    )
    assert said[False] != said[None], (
        f"{contract.descriptor.name}: thinking=False decayed into the same request as asking "
        f"for nothing ({said[False]!r})"
    )
    assert said[True] != said[False], (
        f"{contract.descriptor.name}: thinking=True and thinking=False are the same request "
        f"({said[True]!r})"
    )


@pytest.mark.parametrize("contract", _CASES)
def test_a_judge_decodes_greedily_on_every_provider(
    contract: WireContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`temperature` is 0 on both paths, and it is asserted on the wire on both.

    Separated from the record above because of what it cost to be missing. It sat in the
    Ollama branch of `build_chat_model` and nowhere else, so every hosted judgement this
    product ever made was sampled at whatever default the endpoint chose, and the only
    assertion on the subject was that the parameter was absent from a helper's return value.

    What it does not assert, in either direction: that judging is reproducible, and that the
    vendor honours it. The first is false and no sampling parameter reaches it — a judgement
    is a sampled tool call at the end of a sampled reasoning trace. The second is the caveat
    in this module's docstring.
    """

    _, body = _capture(contract, None, monkeypatch)

    assert contract.reads(body).temperature == 0


@pytest.mark.parametrize("contract", _CASES)
def test_nothing_is_sent_beyond_what_the_configuration_asked_for(
    contract: WireContract, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The complete body, so an added parameter fails as loudly as a removed one.

    Driven at `thinking=True` because that is the state that was broken, and because a whole
    body pinned in the one state that used to say nothing is the one a regression would show
    up in first.
    """

    config, body = _capture(contract, True, monkeypatch)

    assert body == contract.whole_body(config)


@pytest.mark.parametrize(
    "descriptor", [pytest.param(value, id=name) for name, value in NO_CHAT_MODEL.items()]
)
def test_a_provider_with_no_chat_model_is_refused_by_name(
    descriptor: ProviderDescriptor,
) -> None:
    """The stand-in reasons in-process, so asking for a transport is a configuration error.

    Asserted rather than skipped, because the refusal is load-bearing:
    `SelectedLangChainChatModel._resolve` deliberately has no branch for the stand-in and
    says so, relying on this raise to catch a stored selection naming a provider that cannot
    be built.
    """

    config = reasoning_config(descriptor, DETERMINISTIC_MODEL, None)

    with pytest.raises(ConfigurationError, match=descriptor.name):
        build_chat_model(config)


#: How a request could name a context window if one were ever added to the hosted body.
#: Written as a fragment rather than a list of exact keys, because the field this guards
#: against is one nobody has chosen a name for yet: `num_ctx` is Ollama's spelling,
#: `context_length` is what several hosted APIs use, and anything else still has to say
#: `ctx` or `context` somewhere to mean it.
_NAMES_A_CONTEXT_WINDOW: Final = re.compile(
    r"ctx|context[_-]?(window|length|size|tokens)", re.IGNORECASE
)


def _context_window_mentions(body: Mapping[str, object], number: int) -> list[str]:
    """Every place in a request that names a context window, or carries this one's number.

    Both, because either one alone is easy to slip past. A key check misses a window sent
    under a name this regex has not thought of; a value check misses a window sent as
    something other than the configured number. Nested, because `extra_body` is merged into
    the request by the SDK and a parameter can arrive one level down.
    """

    found: list[str] = []

    def walk(node: object, path: str) -> None:
        if isinstance(node, Mapping):
            for key, value in cast("Mapping[object, object]", node).items():
                where = f"{path}.{key}" if path else str(key)
                if _NAMES_A_CONTEXT_WINDOW.search(str(key)) or (
                    not isinstance(value, bool) and value == number
                ):
                    found.append(f"{where}={value!r}")
                walk(value, where)
        elif isinstance(node, list):
            for index, item in enumerate(cast("list[object]", node)):
                walk(item, f"{path}[{index}]")

    walk(body, "")
    return sorted(found)


def test_the_context_window_means_two_different_things_and_only_one_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stated as its own test, because "absent" here is a decision rather than an omission.

    On Ollama `context_window_tokens` is `num_ctx`: the runner allocates that window before
    it answers anything, which is why `OLLAMA_DESCRIPTOR` sets its own from what this product
    sends rather than from what a model can take. On OpenRouter there is no such request
    field; the number is a local bound that `ReasoningModelConfig.output_fits_context_window`
    validates against and `ModelCatalogService` clamps to each model's own window, and none
    of that reaches the provider.

    Both halves are read off a request that was actually sent. The hosted half used to call
    `_openrouter_expects` and assert that the constant it returns is the constant it returns,
    which cannot fail and so was documentation wearing a test's clothes — worse than a comment
    for being reported as a passing assertion. It sends three requests now, one per thinking
    state, and asserts that nothing in any of them names a context window or carries the
    configured number: 128000 for `google/gemini-3.5-flash-lite`, which collides with neither
    output budget (16384 and 32768), so a hit is a hit.

    `test_nothing_is_sent_beyond_what_the_configuration_asked_for` would also fail if this
    field were added, and this is still worth its own assertion: that one pins one literal
    body in one thinking state, so it says "the request is exactly this" where this says "the
    context window is deliberately not in it, under any spelling and in every state".
    """

    hosted = WIRE_CONTRACTS[openrouter.DESCRIPTOR.name]
    for state in (True, False, None):
        config, body = _capture(hosted, state, monkeypatch)
        assert _context_window_mentions(body, config.context_window_tokens) == [], (
            f"a hosted request with thinking={state!r} describes its context window; there "
            "is no such field on this API and the number is a local bound"
        )

    local_config, local_body = _capture(WIRE_CONTRACTS[OLLAMA_DESCRIPTOR.name], None, monkeypatch)

    assert _ollama_sent(local_body).context_window_tokens == local_config.context_window_tokens
    assert local_config.context_window_tokens == OLLAMA_DESCRIPTOR.defaults.context_window_tokens


def test_no_request_pins_a_route(monkeypatch: pytest.MonkeyPatch) -> None:
    """`provider` never goes on the wire, asserted on the request rather than on the helper.

    `provider.require_parameters` turned OpenRouter's soft routing preference into a hard
    filter, and it was removed after it left an experiment with no eligible endpoint at all
    and a 404 on every call. `test_openrouter.py` asserts that `request_body` does not return
    one; this asserts that no layer between it and the socket adds one back, which is the
    only form that covers `extra_body` being merged by the SDK.

    Recording is not pinning: `openrouter._observe_route` still reads which endpoint answered
    off the response, and nothing about that appears in a request.
    """

    body: dict[str, Any] = dict(_capture(WIRE_CONTRACTS["openrouter"], "medium", monkeypatch)[1])

    assert "provider" not in body
