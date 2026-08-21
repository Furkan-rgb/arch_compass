"""Provider discovery and health probes, separate from LangChain inference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import httpx
from google import genai
from google.genai import errors, types
from ollama import Client, ResponseError

from archcompass.configuration import resolve_api_key
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.model_catalog import ProviderDefaults, ProviderDescriptor
from archcompass.reasoning.records import AvailableModel, ProbeResult
from archcompass.records import ThinkingLevel, ThinkingMode

DETERMINISTIC_MODEL = "deterministic-architecture-v4"
#: The one Google model this workspace offers, and deliberately only one.
#:
#: A review is not one call: every candidate is judged separately, questions are generated,
#: a synopsis is written, and a clarification round judges again. On Google's free tier the
#: larger models are rationed by the day — `gemini-3.6-flash` allows twenty requests before
#: it starts refusing — which is fewer than a single review of a small repository spends. A
#: model that cannot finish one review is not a choice, it is a trap, and offering it in the
#: picker means the first thing a new workspace does is fail halfway through with a 429.
#: `gemini-3.5-flash-lite` has limits generous enough to finish, and it is the fastest of
#: them, so it is the whole Google line-up here.
GOOGLE_MODELS: Final = ("gemini-3.5-flash-lite",)

#: Which of those sample at a temperature of their own choosing.
#:
#: The Gemini 3 family fixes its sampling: `temperature`, `top_p` and `top_k` are dropped
#: from the request and warned about rather than honoured. Asking for a temperature of zero
#: there does not make the model deterministic — it only makes the log say the request
#: contained something the API discarded, which is worth neither the noise nor the false
#: impression that the run is reproducible. Every model above is one of those today; the set
#: stays a set because the next one Google ships need not be.
GOOGLE_FIXED_SAMPLING_MODELS: Final = frozenset({"gemini-3.5-flash-lite"})

#: What a Gemini 3 model can be asked for, and the one row that asks for nothing.
#:
#: Gemini 3 replaced the thinking switch with `thinking_level`, so there is no request that
#: means "no". `None` leaves the model on its dynamic default, which adjusts depth to the
#: request and is a fifth behaviour rather than the absence of the other four.
GOOGLE_THINKING_MODES: Final = (None, "minimal", "low", "medium", "high")


def google_thinking_level(thinking: ThinkingMode) -> ThinkingLevel | None:
    """One `ThinkingMode` as the level Gemini takes, or `None` to ask for nothing.

    The two booleans are read as the ends of the dial because Gemini 3 has no switch to read
    them as. `True` is `high`, which is what requiring reasoning means where the depth is
    chosen. `False` is `minimal` and not off: a Gemini 3 model always thinks a little, so
    `minimal` is the floor and claiming otherwise would be the quiet decay into absence that
    `ReasoningModelConfig.thinking` exists to forbid.
    """

    if thinking is None:
        return None
    if thinking is True:
        return "high"
    if thinking is False:
        return "minimal"
    return thinking


#: Which Ollama embedding models were trained to be told what the text is *for*.
#:
#: A task prompt is a prefix on the input naming the job — searching, or being searched —
#: and it is how a model knows to place a short question near the long answer to it instead
#: of treating them as two unlike texts. Google takes the same instruction as a `task_type`
#: on the request and `build_embeddings` already sends it there. Ollama's API takes only
#: text, and its modelfile for EmbeddingGemma is a bare `{{ .Prompt }}`, so the instruction
#: has to be part of the text or it is not sent at all.
#:
#: Named per family rather than applied to every Ollama model, because the prefixes are not
#: a generic trick: `nomic-embed-text` was trained on `search_query: ` and
#: `search_document: `, and a model trained without prompts reads one as part of the text it
#: is meant to be embedding.
TASK_PROMPTED_OLLAMA_MODELS: Final = frozenset({"embeddinggemma"})

#: The strings Google documents for EmbeddingGemma retrieval. The document form takes `none`
#: for the title because a chunk already opens with its policy's title, and naming it twice
#: is not the documented shape either.
EMBEDDINGGEMMA_QUERY_PROMPT: Final = "task: search result | query: {text}"
EMBEDDINGGEMMA_DOCUMENT_PROMPT: Final = "title: none | text: {text}"


def ollama_model_family(model: str) -> str:
    """`embeddinggemma:latest` and `embeddinggemma:300m` are one model with two tags."""

    return model.split(":", 1)[0]


@dataclass(frozen=True, slots=True)
class SupportedOllamaModel:
    """An Ollama model ArchCompass has deliberately approved for reasoning."""

    name: str
    label: str
    recommended: bool = False


OLLAMA_MODELS: Final = (
    SupportedOllamaModel(
        name="gemma4:26b-mlx",
        label="Gemma 4 26B MLX",
        recommended=True,
    ),
    SupportedOllamaModel(
        name="gemma4:12b-mlx",
        label="Gemma 4 12B MLX",
    ),
    SupportedOllamaModel(
        name="gemma4:e4b-mlx",
        label="Gemma 4 e4B MLX",
    ),
)


def probe_deterministic(defaults: ProviderDefaults) -> ProbeResult:
    del defaults
    return ProbeResult(
        available=True,
        models=[
            AvailableModel(name=DETERMINISTIC_MODEL, label="deterministic substitute")
        ],
    )


def probe_google(defaults: ProviderDefaults) -> ProbeResult:
    try:
        api_key = resolve_api_key(defaults.api_key_env, provider="google")
    except ConfigurationError as error:
        return ProbeResult(available=False, detail=str(error))
    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=2_000),
        )
        page = client.models.list(
            config=types.ListModelsConfig(query_base=True, page_size=100)
        ).page
    except errors.APIError as error:
        return ProbeResult(available=False, detail=str(error))
    except (httpx.HTTPError, ConnectionError, KeyError, TypeError, ValueError) as error:
        return ProbeResult(available=False, detail=str(error))
    found: dict[str, AvailableModel] = {}
    for model in page:
        name = (model.name or "").removeprefix("models/")
        if name not in GOOGLE_MODELS:
            continue
        found[name] = AvailableModel(
            name=name,
            label=model.display_name or "",
            input_token_limit=model.input_token_limit,
            output_token_limit=model.output_token_limit,
            thinking_modes=GOOGLE_THINKING_MODES if model.thinking else (None,),
        )
    if not found:
        return ProbeResult(
            available=False,
            detail="the configured key reaches none of the supported Google models",
        )
    return ProbeResult(
        available=True,
        models=[found[name] for name in GOOGLE_MODELS if name in found],
    )


def probe_ollama(defaults: ProviderDefaults) -> ProbeResult:
    base_url = defaults.resolved_base_url()
    if not base_url:
        return ProbeResult(
            available=False,
            detail="this provider sets no base URL",
        )

    client = Client(host=base_url, timeout=2.0)

    try:
        listed = client.list()
    except (ResponseError, httpx.HTTPError, ConnectionError, ValueError) as error:
        return ProbeResult(
            available=False,
            detail=f"{base_url}: {error}",
        )

    supported = {model.name: model for model in OLLAMA_MODELS}
    found: dict[str, AvailableModel] = {}

    for entry in listed.models:
        model_name = entry.model
        if not model_name:
            continue

        support = supported.get(model_name)
        if support is None:
            continue

        try:
            capabilities = client.show(model_name).capabilities or []
        except (ResponseError, httpx.HTTPError, ConnectionError, ValueError):
            capabilities = []

        found[model_name] = AvailableModel(
            name=model_name,
            label=support.label,
            thinking_modes=(True, False) if "thinking" in capabilities else (None,),
        )

    if not found:
        return ProbeResult(
            available=False,
            detail=f"{base_url} has none of the supported Ollama models",
        )

    return ProbeResult(
        available=True,
        models=[found[model.name] for model in OLLAMA_MODELS if model.name in found],
    )


DETERMINISTIC_DESCRIPTOR = ProviderDescriptor(
    name="fake",
    label="Deterministic",
    probe=probe_deterministic,
    defaults=ProviderDefaults(),
)
GOOGLE_DESCRIPTOR = ProviderDescriptor(
    name="google",
    label="Google",
    probe=probe_google,
    defaults=ProviderDefaults(
        api_key_env="GOOGLE_API_KEY",
        context_window_tokens=1_048_576,
        max_output_tokens_thinking=65_536,
        concurrent_requests=4,
    ),
)
OLLAMA_DESCRIPTOR = ProviderDescriptor(
    name="ollama",
    label="Ollama",
    probe=probe_ollama,
    defaults=ProviderDefaults(
        base_url="http://127.0.0.1:11434",
        base_url_env="ARCHCOMPASS_OLLAMA_URL",
    ),
)
