"""Provider-specific construction behind LangChain's common model interfaces."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_ollama import ChatOllama, OllamaEmbeddings
from pydantic import BaseModel, Field, SecretStr

from archcompass.configuration import ReasoningModelConfig, resolve_api_key
from archcompass.domain.errors import ConfigurationError


class EmbeddingModelConfig(BaseModel):
    provider: LiteralProvider
    model: str = Field(min_length=1)
    dimensions: int = Field(ge=1)
    base_url: str | None = None
    api_key_env: str | None = None


type LiteralProvider = str


def build_chat_model(config: ReasoningModelConfig) -> BaseChatModel:
    if config.provider == "google":
        return ChatGoogleGenerativeAI(
            model=config.model,
            api_key=SecretStr(resolve_api_key(config.api_key_env, provider="google")),
            temperature=0,
            max_tokens=config.max_output_tokens,
            request_timeout=config.timeout_seconds,
            retries=0,
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
        return GoogleGenerativeAIEmbeddings(
            model=config.model,
            api_key=SecretStr(resolve_api_key(config.api_key_env, provider="google")),
            output_dimensionality=config.dimensions,
        )
    if config.provider == "ollama":
        return OllamaEmbeddings(
            model=config.model,
            base_url=config.base_url,
            dimensions=config.dimensions,
        )
    raise ConfigurationError(f"Unsupported LangChain embedding provider: {config.provider}")
