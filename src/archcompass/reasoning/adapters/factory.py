"""Provider-specific construction behind LangChain's common model interfaces."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from archcompass.configuration import (
    EmbeddingModelConfig,
    ReasoningModelConfig,
    resolve_api_key,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.adapters.google_batch import (
    GoogleBatchEmbeddings,
    GoogleEmbeddings,
)
from archcompass.reasoning.adapters.openai_compatible import (
    OPENAI_COMPATIBLE_PROVIDERS,
)
from archcompass.reasoning.adapters.providers import GOOGLE_FIXED_SAMPLING_MODELS


def build_chat_model(config: ReasoningModelConfig) -> BaseChatModel:
    if config.provider == "google":
        # A model that fixes its own sampling is sent no temperature at all. Passing one
        # would be discarded on the way out and reported as a warning on every single
        # call, which reads as a misconfiguration and is really just a parameter the model
        # does not take.
        sampling = (
            {}
            if config.model in GOOGLE_FIXED_SAMPLING_MODELS
            else {"temperature": 0.0}
        )
        # `retries=0` leaves retrying to `archcompass.retrying`, which is the only place
        # that can wait for the length of a quota window, say in the log that it is
        # waiting, and fail as a `ProviderError` the API already knows how to report.
        return ChatGoogleGenerativeAI(
            model=config.model,
            api_key=SecretStr(resolve_api_key(config.api_key_env, provider="google")),
            max_tokens=config.max_output_tokens,
            request_timeout=config.timeout_seconds,
            retries=0,
            **sampling,
        )
    if config.provider in OPENAI_COMPATIBLE_PROVIDERS:
        # One branch for every vendor of this API, because the only thing that varies
        # between them is already on the configuration: where to send it and which variable
        # holds the key. A branch per vendor would be the same four lines with a different
        # string in them, waiting to drift apart.
        #
        # `max_retries=0` for the reason Google gets `retries=0`: the SDK would retry
        # silently, on its own schedule, without the log line or the `ProviderError` that
        # makes an exhausted quota legible — and `archcompass.retrying` is already wrapped
        # around every structured call.
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=SecretStr(
                resolve_api_key(config.api_key_env, provider=config.provider)
            ),
            temperature=0.0,
            max_completion_tokens=config.max_output_tokens,
            timeout=config.timeout_seconds,
            max_retries=0,
        )
    if config.provider == "ollama":
        return ChatOllama(
            model=config.model,
            base_url=config.base_url,
            temperature=0,
            num_ctx=config.context_window_tokens,
            num_predict=config.max_output_tokens,
            reasoning=config.thinking,
            sync_client_kwargs={"timeout": config.timeout_seconds},
        )
    raise ConfigurationError(f"Unsupported LangChain reasoning provider: {config.provider}")


def build_embeddings(config: EmbeddingModelConfig) -> Embeddings:
    if config.provider == "google":
        key = resolve_api_key(config.api_key_env, provider="google")
        # Interactive for a search, batched for building the index — one object, because
        # the index needs both and only knows it wants embeddings.
        return GoogleEmbeddings(
            GoogleGenerativeAIEmbeddings(
                model=config.model,
                api_key=SecretStr(key),
                output_dimensionality=config.dimensions,
            ),
            GoogleBatchEmbeddings(
                api_key=key,
                model=config.model,
                dimensions=config.dimensions,
            ),
        )
    if config.provider == "ollama":
        return OllamaEmbeddings(
            model=config.model,
            base_url=config.base_url,
            dimensions=config.dimensions,
        )
    raise ConfigurationError(f"Unsupported LangChain embedding provider: {config.provider}")
