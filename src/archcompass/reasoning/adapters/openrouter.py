"""One hosted boundary, and the catalogue behind it.

OpenRouter answers OpenAI's chat API, so the transport is the one every vendor of that API
already shares. It is not in `openai_compatible.py` because two things about it are
behaviour rather than data, and a row in that table cannot carry either.

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

from collections.abc import Mapping
from typing import Any, Final, cast

import httpx

from archcompass.reasoning.ports import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.records import AvailableModel, ProbeResult

BASE_URL: Final = "https://openrouter.ai/api/v1"
API_KEY_ENV: Final = "OPENROUTER_API_KEY"

#: How long the catalogue may take before the chooser gives up on it. The same two seconds
#: every other probe allows: this answers a dropdown, not a review. Measured at 0.11s for
#: the whole catalogue, which is 690 KB uncompressed and a tenth of that over the wire.
_CATALOGUE_TIMEOUT: Final = 20.0

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


def request_body(max_output_tokens: int) -> dict[str, Any]:
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
    """

    return {
        "max_tokens": max_output_tokens,
        "provider": {"require_parameters": True},
    }


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
        # One mode, and that is a claim about the request rather than about the models.
        # `reasoning_effort` reaches 144 of them and would be a real second mode; offering
        # it means deciding what ArchCompass does with a level, which is its own change.
        thinking_modes=(None,),
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
