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

DETERMINISTIC_MODEL = "deterministic-architecture-v4"
GOOGLE_MODELS: Final = (
    "gemini-3.6-flash",
    "gemini-2.5-pro",
    "gemini-3.5-flash-lite",
)


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
            thinking_modes=(True, False) if model.thinking else (None,),
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
    probe=probe_deterministic,
    defaults=ProviderDefaults(),
)
GOOGLE_DESCRIPTOR = ProviderDescriptor(
    name="google",
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
    probe=probe_ollama,
    defaults=ProviderDefaults(
        base_url="http://127.0.0.1:11434",
        base_url_env="ARCHCOMPASS_OLLAMA_URL",
    ),
)
