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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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


def http_client(timeout: float) -> httpx.Client:
    """The transport OpenRouter is reached through.

    Its only job beyond the timeout is `_raise_inline_error`, which is why it exists at all
    rather than the SDK's own client being good enough.
    """

    return httpx.Client(
        timeout=timeout,
        event_hooks={"response": [_raise_inline_error]},
    )


def request_body(max_output_tokens: int, thinking: ThinkingMode = None) -> dict[str, Any]:
    """The parameters that go on the wire beside the messages, and why not through the field.

    Two things have to be true at once, and only this shape gets both.

    `provider.require_parameters` is the difference between "this route probably honours a
    JSON schema" and "this route does". OpenRouter's default is a soft preference that never
    removes a candidate endpoint — so a model whose catalogue entry says `structured_outputs`
    can still be served by one of its endpoints that does not, because the model-level flag
    is a union across all of them. On `openai/gpt-oss-120b` five of twenty endpoints do not
    support it. `require_parameters` makes the filter hard, and a route that cannot honour
    the request is a loud 404 rather than a review that looks fine and is not.

    But it is matched against *every* parameter in the body, and that is why the ceiling is
    here rather than in `ChatOpenAI(max_completion_tokens=…)`. That field normalises to
    `max_completion_tokens` on the wire whichever name it is given — measured — and no
    endpoint of `google/gemini-3.5-flash-lite` declares it, while all seven declare
    `max_tokens`. The two together were a 404 on every request; `max_tokens` through
    `extra_body`, which the SDK passes verbatim, is a 200.

    So the ceiling is enforced twice over: the route is chosen for supporting it, and the
    route then applies it. Measured: `max_tokens=16` came back with 12 completion tokens and
    `finish_reason="length"`.

    Which is also why nothing else is here. Every parameter in the body narrows the set of
    endpoints that can serve the request, so one sent out of habit is availability spent for
    nothing — and `temperature` was exactly that. It was pinned to 0 for a determinism this
    path does not have: measured over three runs of one candidate set on identical input,
    verdicts moved anyway (`material`, `cleared`, `held` for the same candidate). What it did
    buy was a narrower route — three of `google/gemini-3.5-flash-lite`'s seven endpoints
    declare it — and on a reasoning-only model it bought a wall: none of
    `openai/gpt-5.6-luna-pro`'s five endpoints accept `temperature` at all, so every request
    was a 404 before a candidate was ever read. It is not sent now, and the model's own
    default stands.

    `reasoning` is sent only when a depth was asked for. OpenRouter spells it as an effort
    on both of the two shapes its endpoints declare, and this is the portable one; absent, a
    model reasons however it reasons, which is what `None` has always meant here.
    """

    body: dict[str, Any] = {
        "max_tokens": max_output_tokens,
        "provider": {"require_parameters": True},
    }
    if isinstance(thinking, str):
        body["reasoning"] = {"effort": thinking}
    return body


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
