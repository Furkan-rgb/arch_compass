"""One hosted boundary, and the catalogue behind it.

OpenRouter answers OpenAI's chat API, so the transport underneath is `langchain-openai` and
the `httpx` client below. Two things about it are behaviour rather than configuration.

The first is discovery. Every other vendor here is offered a hand-approved list of models,
intersected with what the endpoint lists, because a vendor's catalogue is full of models
that will not honour a JSON schema and the only way to know which is to have judged with
them. OpenRouter publishes that fact per model. So the list is a *capability filter* over
the live catalogue — a model is offered when it declares `structured_outputs` and `tools` —
and there is no list here to go stale when somebody ships a better model on a Tuesday.

The second is the request. See `request_body`.

What is deliberately not here: any notion of Google, Anthropic, OpenAI or Cerebras. Which
upstream serves a request is OpenRouter's routing decision, configured on the request as a
`provider` block and reported back on the response. ArchCompass chooses a model and the
capabilities it needs; it does not choose a company.

It does now *write down* which company answered. Not choosing a route and not knowing which
route was taken are two different positions, and only the first one was ever argued for
here: `google/gemini-3.5-flash-lite` is served by seven endpoints that are not the same
silicon, the same quantisation or the same sampler, and until `observed_route` the record of
a judgement could not say which of them ran it. See `observed_route` for how it is kept and
`Finding.served_by` for where it lands.
"""

from __future__ import annotations

from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Final, cast

import httpx
from langchain_core.embeddings import Embeddings

from archcompass.domain.errors import ProviderError
from archcompass.reasoning.ports import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.records import AvailableModel, ProbeResult
from archcompass.records import THINKING_LEVELS, ThinkingMode

BASE_URL: Final = "https://openrouter.ai/api/v1"
API_KEY_ENV: Final = "OPENROUTER_API_KEY"

#: How long the catalogue may take before the chooser gives up on it. The same two seconds
#: every other probe allows: this answers a dropdown, not a review. Measured at 0.11s for
#: the whole catalogue, which is 690 KB uncompressed and a tenth of that over the wire.
_CATALOGUE_TIMEOUT: Final = 20.0

#: Longer, because this one is a model call rather than a listing: the policy corpus goes
#: through it in groups of sixty-four.
_EMBEDDING_TIMEOUT: Final = 120.0

#: What a model must declare to be worth offering. `structured_outputs` because every
#: judgement is a JSON-schema call and a model that cannot hold one fails forty times in the
#: middle of a review rather than once at selection; `tools` because a hinge investigation is
#: a tool loop and a workspace that cannot run one asks a person what the repository already
#: knew.
_REQUIRED_CAPABILITIES: Final = frozenset({"structured_outputs", "tools"})

#: Catalogue entries that are not a model this workspace can judge with, whatever their
#: capabilities say. Three shapes, and each would fail differently.
#:
#: `openrouter/…` is a router: it resolves to a different underlying model per request —
#: two consecutive calls to `openrouter/free` were served by Nvidia and by Cohere. `~…`
#: is a moving pointer, `~anthropic/claude-haiku-latest` today and something else next
#: quarter. Both break the promise `model_identity` makes, which is that the same string
#: means the same model produced it; the finding cache is keyed on that promise, so either
#: would quietly file two models under one name and report no change when everything had.
#:
#: `…:batch` is reachable only through OpenRouter's own batch endpoint and refuses an
#: ordinary call outright — "This model is only available through the Batch API" — so
#: offering one would put a row on the chooser that fails on the first judgement.
_ROUTER_NAMESPACE: Final = "openrouter/"
_MOVING_POINTER: Final = "~"
_BATCH_ONLY: Final = ":batch"


class InlineProviderError(ProviderError):
    """A refusal the provider put inside a 200 body instead of in the status line.

    Carries the status the body claimed, because that is the only place it is stated. The
    retry layer reads `status_code` off whatever it is handed, so a 429 delivered this way
    is waited on exactly like one delivered properly.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _raise_inline_error(response: httpx.Response) -> None:
    """Turn a 200 that is actually an error into an error, before the SDK sees it.

    OpenRouter documents that anything going wrong *while the model is producing output* is
    reported in the response body rather than in the status — the request reached a provider,
    so by HTTP's reckoning it succeeded. The body then has an `error` object and no `choices`.

    What that costs without this hook is not a worse message, it is the review. The OpenAI
    SDK iterates `choices` while parsing, so the first thing to fail is
    `TypeError: 'NoneType' object is not iterable` — an exception carrying no status and no
    recognisable phrase, which `is_transient` therefore reads as permanent. A rate limit
    arriving partway through a review's judgements ends the whole review instead of costing
    four seconds.

    Deliberately narrow. Only a 2xx, only JSON, only a top-level `error` object: a body
    shaped like that is never a completion anybody could use, on any vendor of this API.
    Streaming is left alone — reading the body here would consume it — and ArchCompass does
    not stream a structured call anyway.
    """

    if response.status_code // 100 != 2:
        return
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type or "event-stream" in content_type:
        return
    response.read()
    try:
        document = cast(object, response.json())
    except ValueError:
        return
    if not isinstance(document, dict):
        return
    error = cast(Mapping[str, object], document).get("error")
    if not isinstance(error, dict):
        return
    detail = cast(Mapping[str, object], error)
    code = detail.get("code")
    message = detail.get("message")
    raise InlineProviderError(
        f"The provider answered {response.status_code} with an error in the body: "
        f"{message if isinstance(message, str) else error}",
        status_code=code if isinstance(code, int) else None,
    )


@dataclass(slots=True)
class ServedRoute:
    """Which of a model's endpoints answered, across one span of requests.

    A list rather than one name, because a judgement is a conversation rather than a call:
    `DeepArchitectureJudge` may reach the provider twenty-six times for a single candidate,
    and OpenRouter routes each of those requests on its own. Keeping only the last would say
    one endpoint served a judgement that two of them served, and telling those two cases
    apart is the entire reason this is recorded.
    """

    endpoints: list[str] = field(default_factory=list[str])

    @property
    def served_by(self) -> str:
        """Every endpoint that answered, first seen first, as one storable string.

        Comma-joined because a provenance field is read and shown far more often than it is
        parsed, so the shape it is stored in should be the shape it is read in. This cites
        no other field as precedent any more: the one it used to cite was
        `Review.model_identity`, a comma-joined set that the revision delta then compared
        against a single identity, and it was deleted for exactly that. The join is right
        here and was wrong there, and the difference is that nothing compares this.

        Empty is a real answer and not a missing one. It is what a local Ollama and the
        deterministic stand-in produce, because neither has an endpoint to name.
        """

        return ",".join(self.endpoints)

    def observed(self, endpoint: str) -> None:
        """Note an endpoint, once, in the order it first answered.

        Deduplicated rather than counted: how many of a judgement's requests one endpoint
        served is not a question the record is being kept to answer, and a judgement that
        made twenty-six calls to one endpoint would otherwise store that name twenty-six
        times in a field a person reads.
        """

        if endpoint and endpoint not in self.endpoints:
            self.endpoints.append(endpoint)


#: The record `_observe_route` writes into, for whatever span of calls is being observed.
#:
#: A `ContextVar` rather than a thread-local or an attribute on the transport, because
#: neither of those can say *which judgement* a response belongs to. The transport is one
#: object shared by every candidate in a review — the graph fans out one branch per candidate
#: and forty-six of them is an ordinary number for a real repository — so an attribute on it
#: would hand whichever endpoint answered last to whatever asked next. A thread-local would
#: hold for a judgement's own requests and lose anything LangGraph chose to run elsewhere.
#:
#: LangGraph copies the calling context into every task it schedules and runs a lone task on
#: the calling thread, so a record set here is visible to the requests made under it and to
#: no other branch. The variable holds a *mutable* record for that reason: a copied context
#: gives a task its own binding, and what has to travel back out is the writing, not the
#: binding.
#:
#: The failure mode if a request is ever made somewhere this cannot be seen is `None` here
#: and an empty `served_by` on the finding — nothing recorded rather than something wrong,
#: which is the only acceptable direction for a provenance field to fail in.
_OBSERVED_ROUTE: ContextVar[ServedRoute | None] = ContextVar(
    "archcompass_observed_route", default=None
)


@contextmanager
def observed_route() -> Generator[ServedRoute]:
    """Record which endpoints answer while this block runs.

    Nothing is recorded outside one of these, deliberately. A record with no owner would be
    a global "last endpoint seen", and that value is wrong exactly when a review is busy,
    which is the only time anybody looks at it.

    A block that reaches something other than OpenRouter yields a record that stays empty and
    is stored empty. That is the honest answer for a provider with one endpoint.
    """

    record = ServedRoute()
    token = _OBSERVED_ROUTE.set(record)
    try:
        yield record
    finally:
        _OBSERVED_ROUTE.reset(token)


def _observe_route(response: httpx.Response) -> None:
    """Keep the one thing on a completion that says where it was really served.

    OpenRouter names the endpoint that answered in a top-level `provider` field on every
    completion. Nothing downstream of here ever sees it: `langchain-openai` builds an
    `AIMessage`'s `response_metadata` from a fixed set of keys and this is not one of them.
    Measured against a body carrying `"provider": "Google AI Studio"`, the metadata that
    arrived held `model_provider: "openai"`, the model id, a usage block and a finish reason
    — and nothing at all about the route. The response body is the only place the field
    exists, and this client is the only place this application holds the body.

    The same three guards as `_raise_inline_error`, for the same reasons: only a 2xx, only
    JSON, never a stream, because reading a streamed body here would consume it before the
    SDK could. `Response.read()` caches, so the two hooks do not take the body from one
    another.

    Recording is not pinning. `request_body` explains why no `provider` block is sent and
    nothing here starts sending one — this answers the question after the fact instead of
    forbidding the answer beforehand, which is what the hard filter did before it 404'd a
    whole experiment.
    """

    record = _OBSERVED_ROUTE.get()
    if record is None or response.status_code // 100 != 2:
        return
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type or "event-stream" in content_type:
        return
    response.read()
    try:
        document = cast(object, response.json())
    except ValueError:
        return
    if not isinstance(document, dict):
        return
    endpoint = cast(Mapping[str, object], document).get("provider")
    if isinstance(endpoint, str):
        record.observed(endpoint)


#: What this transport does beyond sending, in the order it does it.
#:
#: Observing comes first so that a body OpenRouter served and then reported an error inside
#: still records which endpoint served it — `_raise_inline_error` raises out of the hook
#: chain, and the route is worth most in exactly the case where something went wrong.
#:
#: A named tuple rather than a literal inside `http_client` because the test that proves a
#: response's route is kept has to install the same hooks over a mock transport. Reaching for
#: this list is what makes a hook added later covered by that test rather than quietly
#: outside it.
_RESPONSE_HOOKS: Final = (_observe_route, _raise_inline_error)


def http_client(timeout: float) -> httpx.Client:
    """The transport OpenRouter is reached through.

    Its only jobs beyond the timeout are `_RESPONSE_HOOKS`, which is why it exists at all
    rather than the SDK's own client being good enough.
    """

    return httpx.Client(
        timeout=timeout,
        event_hooks={"response": list(_RESPONSE_HOOKS)},
    )


def request_body(max_output_tokens: int, thinking: ThinkingMode = None) -> dict[str, Any]:
    """The parameters that go on the wire beside the messages, and why so few of them.

    Only what the request cannot be made without, plus the one thing a judge's decoding
    should not be left to a default. OpenRouter matches every parameter here against the
    endpoints that could serve the request — but as a *preference*, now that no
    `provider.require_parameters` accompanies it: an endpoint that does not declare a
    parameter is ranked below one that does, and an endpoint that ends up serving the request
    anyway drops the parameter rather than refusing it. So an idle parameter costs a worse
    route, where it used to cost the request. That is a reason to send few, and it stopped
    being a reason to send none the day the hard filter came out.

    `max_tokens` rather than `ChatOpenAI(max_completion_tokens=…)`, and through `extra_body`
    rather than through the field. That field normalises to `max_completion_tokens` on the
    wire whichever name it is given — measured — and no endpoint of
    `google/gemini-3.5-flash-lite` declares it while all seven declare `max_tokens`.
    `extra_body` is passed verbatim, so this is the only way to send the name the endpoints
    have. Measured: `max_tokens=16` came back with 12 completion tokens and
    `finish_reason="length"`.

    `reasoning` is sent whenever a depth was asked for, in any of the shapes one can be asked
    for in. OpenRouter spells it as an effort on both of the two shapes its endpoints declare,
    and this is the portable one; absent, a model reasons however it reasons, which is what
    `None` has always meant here.

    A switch is read as the ends of that scale — `True` is `high`, `False` is `minimal`. This
    is a levels API and it has no boolean, so `minimal` is the floor rather than off, and that
    approximation is stated rather than hidden. It is also not invented here: it is what
    `ReasoningModelConfig.thinking` and `_thinking_mode` in the CLI both already say happens,
    and until this mapping existed both of those sentences were false. `isinstance(thinking,
    str)` was the whole condition, so `True` produced no `reasoning` key at all — which is
    precisely the decay into absence that `ReasoningModelConfig.thinking` forbids, and it was
    reachable. Measured on the parent commit, `--provider openrouter` with each of the three
    settings sent `{"max_tokens": 32768}` for `on`, `{"max_tokens": 16384}` for `off` and
    `{"max_tokens": 32768}` for naming no depth at all: `on` and absent were the same request
    byte for byte, `off` differed from both only in the budget, because
    `_spends_little_on_thinking` reads `False` as a mode that spends little. So three settings
    reached the provider as two instructions about budget and none about reasoning, which is
    the whole of what the switch was for. `test_provider_conformance.py` asserts the three
    states are three requests, on every provider, and compares only the thinking field so that
    a difference in budget cannot be mistaken for one.

    `temperature` is 0, because a judge should decode greedily and nothing on this path was
    asking it to. It was here once and was removed, and that removal has to be read with its
    date on it: it happened while `provider.require_parameters` was still in this body, which
    is what made every parameter a hard filter. Three of `google/gemini-3.5-flash-lite`'s
    seven endpoints declare `temperature`, so under the filter sending it cut the route set
    to three; none of `openai/gpt-5.6-luna-pro`'s five declare it, so under the filter it cut
    the route set to zero and every request 404'd before a candidate was read. The filter is
    gone. Neither of those costs can be built out of this parameter any more, and the second
    one — the wall — was never a property of the parameter at all.

    The other half of that removal does not survive either, and it is the half worth being
    careful about. It said `temperature` had been pinned "for a determinism this path does
    not have", measured over three runs of one candidate that came back `material`, `cleared`
    and `held`. That measurement is real, and it has since been reproduced over four runs on
    byte-identical input — same commit, same candidate bytes, same case, same sixteen
    policies. What it demonstrates is that greedy decoding does not make an agent loop
    reproducible, which is true and which nothing sendable here could change: the structured
    answer is a sampled tool call at the end of a sampled reasoning trace, and those four runs
    had already diverged at their opening tool call. No sampling parameter converges a
    conversation that has gone to four different places. What one does is take a source of
    variance out of every token this judge emits, which is right for a judge whether or not it
    is sufficient — and "insufficient" was read as "worthless" once already.

    One thing it may not buy, stated rather than assumed. `docs/frontend-plan.md` records that
    `gemini-3.5-flash-lite` and `gemini-3.6-flash` fix their own sampling and discarded
    `temperature` with a warning on every call. That was observed against Google's native API
    rather than through OpenRouter and has not been re-verified here, so this may be a no-op
    for exactly the model this workspace runs while remaining right for every other model on
    this path. `Finding.served_by` is what makes it answerable instead of arguable: the record
    now says which of the seven endpoints served a judgement, so the next divergence can be
    read as sampling or as routing rather than debated.

    What is deliberately still not sent. `top_p` at temperature 0 selects from a distribution
    that has already collapsed onto one token, which is the definition of a parameter sent out
    of habit. `seed` is the parameter to reach for if the record shows this family really does
    ignore `temperature` — but fewer endpoints declare it than declare `temperature`, it
    cannot make a tool loop reproducible either, and there is now a record that can say
    whether it is needed before its cost is spent.

    What is deliberately gone, and what that costs. `provider.require_parameters` used to be
    here to turn OpenRouter's soft routing preference into a hard filter, on the reasoning
    that a model's catalogue capabilities are a union across its endpoints and a route that
    silently could not hold a schema would produce a review that looked fine and was not.
    Measured against that: no judgement was ever observed to be served by an endpoint that
    dropped what was asked, across the whole qualification programme, so the guarantee was
    never seen to be worth anything. What it was observed to cost is a hard 404 — every
    eligible endpoint of `openai/gpt-5.6-luna-pro` declares the two parameters sent here,
    and a narrowing of that account's own provider policy still left the filter with nothing
    to choose, mid-experiment, reported as "No endpoints available matching your guardrail
    restrictions and data policy".

    So the filter is not sent, and the residual risk is stated rather than defended against:
    a request may be routed to an endpoint whose support for structured output is weaker
    than its model's catalogue row claims. That failure is loud — the schema call raises —
    and `_judgeable` still refuses to offer a model whose catalogue does not declare both
    capabilities. Nothing here weakens or overrides an account's own privacy, ZDR or
    provider policy; those filters are OpenRouter's to apply and this simply stops
    intersecting a second one with them.
    """

    body: dict[str, Any] = {"max_tokens": max_output_tokens, "temperature": 0}
    effort = _effort(thinking)
    if effort is not None:
        body["reasoning"] = {"effort": effort}
    return body


def _effort(thinking: ThinkingMode) -> str | None:
    """One thinking mode as the single word this API has for it, or nothing to send.

    `isinstance` rather than `is True` because `ThinkingMode` is `bool | ThinkingLevel |
    None`, and testing the bool first is what leaves a level narrowed to a level for the
    return — the two shapes are told apart by their type, which is the only thing that
    distinguishes them.
    """

    if thinking is None:
        return None
    if isinstance(thinking, bool):
        return "high" if thinking else "minimal"
    return thinking


def _catalogue(path: str, api_key: str) -> list[Mapping[str, object]]:
    response = httpx.get(
        f"{BASE_URL}/{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=_CATALOGUE_TIMEOUT,
    )
    response.raise_for_status()
    body = cast(object, response.json())
    if not isinstance(body, dict):
        return []
    data = cast(Mapping[str, object], body).get("data")
    if not isinstance(data, list):
        return []
    return [
        cast(Mapping[str, object], entry)
        for entry in cast(list[object], data)
        if isinstance(entry, dict)
    ]


def _judgeable(entry: Mapping[str, object]) -> AvailableModel | None:
    """One catalogue row as a model this workspace could judge with, or nothing."""

    identifier = entry.get("id")
    if not isinstance(identifier, str):
        return None
    if (
        identifier.startswith((_ROUTER_NAMESPACE, _MOVING_POINTER))
        or identifier.endswith(_BATCH_ONLY)
    ):
        return None
    declared = entry.get("supported_parameters")
    if not isinstance(declared, list):
        return None
    capabilities = {
        item for item in cast(list[object], declared) if isinstance(item, str)
    }
    if not capabilities.issuperset(_REQUIRED_CAPABILITIES):
        return None
    name = entry.get("name")
    context = entry.get("context_length")
    top = entry.get("top_provider")
    output = (
        cast(Mapping[str, object], top).get("max_completion_tokens")
        if isinstance(top, dict)
        else None
    )
    return AvailableModel(
        name=identifier,
        label=name if isinstance(name, str) and name else identifier,
        input_token_limit=context if isinstance(context, int) else None,
        output_token_limit=output if isinstance(output, int) else None,
        # The depths this provider offers, where the model declares it reasons at all.
        # `None` is always there and always means "the model's own default"; a level is sent
        # as an effort and every one of the four is accepted.
        thinking_modes=(
            (None, *THINKING_LEVELS) if "reasoning" in capabilities else (None,)
        ),
    )


def probe(defaults: ProviderDefaults) -> ProbeResult:
    """Every model in the live catalogue that could hold a judgement, newest first.

    No approved list and no local enum. The catalogue is the source of truth for what
    exists and for what each model can do, and the filter is stated in terms of the
    capability rather than in terms of a name somebody checked once.
    """

    from archcompass.configuration import resolve_api_key

    try:
        api_key = resolve_api_key(defaults.api_key_env, provider="openrouter")
    except Exception as error:  # a missing key is a report, not a crash
        return ProbeResult(available=False, detail=str(error))
    try:
        entries = _catalogue("models", api_key)
    except (httpx.HTTPError, ConnectionError, KeyError, TypeError, ValueError) as error:
        return ProbeResult(available=False, detail=f"{BASE_URL}: {error}")

    offered = [model for model in map(_judgeable, entries) if model is not None]
    if not offered:
        return ProbeResult(
            available=False,
            detail=(
                "OpenRouter listed no model that declares both structured output and "
                "tools, which is what a judgement and a hinge investigation need."
            ),
        )
    offered.sort(key=lambda model: model.label)
    return ProbeResult(available=True, models=offered)


def embedding_models(api_key: str) -> tuple[tuple[str, str], ...]:
    """The `(id, label)` of every embedding model OpenRouter serves.

    Its own endpoint, because `/models` is the chat catalogue and has none of them in it —
    422 entries, every one `output_modalities: ["text"]`.

    Dimensions are deliberately absent from the pair. No catalogue row carries them, on
    either endpoint, and the index keys on an exact width — so the number has to come from
    somewhere that knows it, which is `_OPENROUTER_EMBEDDINGS` beside the Google table that
    has always worked the same way.
    """

    listed: list[tuple[str, str]] = []
    for entry in _catalogue("embeddings/models", api_key):
        identifier = entry.get("id")
        if not isinstance(identifier, str):
            continue
        name = entry.get("name")
        listed.append((identifier, name if isinstance(name, str) and name else identifier))
    return tuple(listed)


#: The embedding models this workspace offers, and the width each one returns.
#:
#: A table, where the reasoning models are a live filter, and the difference is not a
#: preference. The index keys on an exact width — `embedding_identity` is
#: `provider:model:dimensions` and a namespace whose vectors do not compare is a silent
#: wrong answer — and **no catalogue row carries dimensions**, on either endpoint. What
#: `/embeddings/models` reports under `supported_parameters` is chat sampling: `temperature`,
#: `top_p`, `response_format`. So the number has to come from somewhere that knows it.
#:
#: Discovering it would mean one embedding call per model, and the chooser has two seconds
#: for the whole catalogue. `_GOOGLE_EMBEDDINGS` has always worked this way beside it.
#:
#: `dimensions` is sent on every request and validated upstream — an unsupported width comes
#: back as `dimensions must be one of 2048` rather than as a shorter vector — so a wrong row
#: here fails loudly on the first call rather than quietly filling an index.
_EMBEDDING_MODELS: Final = (
    ("google/gemini-embedding-2", 3072, "Gemini Embedding 2"),
    ("google/gemini-embedding-001", 3072, "Gemini Embedding 001"),
    ("openai/text-embedding-3-large", 3072, "OpenAI text-embedding-3-large"),
    ("openai/text-embedding-3-small", 1536, "OpenAI text-embedding-3-small"),
    ("qwen/qwen3-embedding-8b", 4096, "Qwen3 Embedding 8B"),
)


def embedding_candidates(api_key: str) -> tuple[tuple[str, int, str], ...]:
    """The rows above that OpenRouter is actually serving today.

    Intersected with the live listing rather than offered blind, so a model withdrawn
    upstream leaves the chooser instead of failing on the first review that picks it.
    """

    listed = {identifier for identifier, _ in embedding_models(api_key)}
    return tuple(row for row in _EMBEDDING_MODELS if row[0] in listed)


class OpenRouterEmbeddings(Embeddings):
    """`POST /api/v1/embeddings`, which is OpenAI-shaped and takes a list natively.

    Its own class rather than `OpenAIEmbeddings` pointed here, and rather than anything from
    `langchain-openrouter`, which ships no `Embeddings` implementation at all. What it has to
    do is small enough that borrowing a larger one would be the bigger dependency: send the
    texts, send the width, keep the order.

    `call_with_retry` is not here. Every caller already wraps it — `sqlite_index` retries a
    group of chunks, and a query retries at its own call site — and a second retry inside
    this one would multiply the waits rather than add to them.
    """

    def __init__(self, *, api_key: str, model: str, dimensions: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = httpx.post(
            f"{BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "input": list(texts),
                "dimensions": self._dimensions,
            },
            timeout=_EMBEDDING_TIMEOUT,
        )
        if response.status_code // 100 != 2:
            raise ProviderError(
                f"OpenRouter refused an embedding request for {self._model}: "
                f"{response.status_code} {response.text[:200]}"
            )
        body = cast(object, response.json())
        if not isinstance(body, dict):
            raise ProviderError("OpenRouter answered an embedding request with no object.")
        data = cast(Mapping[str, object], body).get("data")
        answered = len(cast(list[object], data)) if isinstance(data, list) else 0
        if answered != len(texts):
            raise ProviderError(
                f"OpenRouter embedded {answered} of {len(texts)} texts. A partial answer "
                "is not written into an index, because a missing vector reads as an "
                "unrelated one."
            )
        vectors: list[list[float]] = []
        # Ordered by `index` rather than by arrival: the caller pairs these back onto its own
        # list, and a reordered response would file every chunk under its neighbour's text.
        # This is the join the deleted batch path got wrong by trusting position instead.
        def _position(item: Mapping[str, object]) -> int:
            at = item.get("index")
            return at if isinstance(at, int) else 0

        for entry in sorted(cast(list[Mapping[str, object]], data), key=_position):
            vector = entry.get("embedding")
            if not isinstance(vector, list):
                raise ProviderError("OpenRouter answered an embedding request without a vector.")
            vectors.append(
                [
                    float(value)
                    for value in cast(list[object], vector)
                    if isinstance(value, (int, float))
                ]
            )
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


DESCRIPTOR: Final = ProviderDescriptor(
    name="openrouter",
    label="OpenRouter",
    probe=probe,
    defaults=ProviderDefaults(
        base_url=BASE_URL,
        # No `base_url_env`: one hosted address, and a variable that could point
        # `openrouter` at somebody else's host would make the provider's name stop
        # describing where the request went.
        api_key_env=API_KEY_ENV,
        # A floor, not a description. The catalogue spans 4,095 to 2,000,000 tokens across
        # the models it offers, and the probe reports each model's own window, which
        # `ModelCatalogService` then clamps the authored budget down to. This number is only
        # what applies before a model has been chosen.
        context_window_tokens=128_000,
    ),
)
