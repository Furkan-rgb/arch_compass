"""Provider-specific construction behind LangChain's common model interfaces."""

from __future__ import annotations

from typing import Final

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from archcompass.configuration import (
    EmbeddingModelConfig,
    ReasoningModelConfig,
    resolve_api_key,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.reasoning.adapters import openrouter
from archcompass.reasoning.adapters.providers import (
    EMBEDDINGGEMMA_DOCUMENT_PROMPT,
    EMBEDDINGGEMMA_QUERY_PROMPT,
    TASK_PROMPTED_OLLAMA_MODELS,
    ollama_model_family,
)


class TaskPromptedEmbeddings(Embeddings):
    """A model's own task prompts, applied where the provider has no field to carry them.

    A hosted embedding API carries the distinction itself — OpenRouter takes an `input_type`,
    and the model behind it is told which it is. Ollama takes text and nothing else, which
    leaves the prefix as the only way to say it — and for a model trained with these prompts,
    saying nothing is not a neutral default but an input shaped unlike anything it was
    trained on.

    Wrapping rather than subclassing the provider's own class: what varies is the text going
    in, and every other thing `OllamaEmbeddings` does should keep being done by it.
    """

    def __init__(self, inner: Embeddings, *, query: str, document: str) -> None:
        self._inner = inner
        self._query = query
        self._document = document

    @property
    def inner(self) -> Embeddings:
        """The unprompted model, so the evaluation can still price what the prompts buy."""

        return self._inner

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._inner.embed_documents(
            [self._document.format(text=text) for text in texts]
        )

    def embed_query(self, text: str) -> list[float]:
        return self._inner.embed_query(self._query.format(text=text))


def _sends_task_prompts(config: EmbeddingModelConfig) -> bool:
    return (
        config.provider == "ollama"
        and ollama_model_family(config.model) in TASK_PROMPTED_OLLAMA_MODELS
    )


def embedding_identity(config: EmbeddingModelConfig) -> str:
    """What the stored vectors are, so an index is reused only where they still compare.

    `SQLitePolicyIndex` namespaces its chunks by this string, which is what lets a workspace
    keep an index across runs. Task prompts change the vectors a model returns, so an index
    built before them must not be asked to answer a prompted query: the suffix makes those
    two sets of vectors separate stores rather than one quietly mixed one, and the corpus is
    re-embedded once instead of every query being compared against the wrong neighbourhood.
    """

    base = f"{config.provider}:{config.model}:{config.dimensions}"
    return f"{base}:task-prompted" if _sends_task_prompts(config) else base


def build_chat_model(config: ReasoningModelConfig) -> BaseChatModel:
    if config.provider == openrouter.DESCRIPTOR.name:
        # The same transport as every other vendor of this API, and one difference: the
        # parameters go through `extra_body` rather than through `ChatOpenAI`'s own fields.
        # `openrouter.request_body` says why, and it is the whole of the difference.
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=SecretStr(
                resolve_api_key(config.api_key_env, provider=config.provider)
            ),
            temperature=0.0,
            timeout=config.timeout_seconds,
            max_retries=0,
            extra_body=openrouter.request_body(config.max_output_tokens),
            http_client=openrouter.http_client(config.timeout_seconds),
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


#: How long one embedding request may take.
#:
#: Well under the 360 seconds a reasoning call gets, because an embedding is not a model
#: thinking — it is a forward pass over a few hundred tokens, and one that has not answered
#: in two minutes is not going to. The same number OpenRouter's own embedding path uses.
_EMBEDDING_TIMEOUT_SECONDS: Final = 120.0


def build_embeddings(config: EmbeddingModelConfig) -> Embeddings:
    if config.provider == openrouter.DESCRIPTOR.name:
        return openrouter.OpenRouterEmbeddings(
            api_key=resolve_api_key(config.api_key_env, provider="openrouter"),
            model=config.model,
            dimensions=config.dimensions,
        )
    if config.provider == "ollama":
        embeddings = OllamaEmbeddings(
            model=config.model,
            base_url=config.base_url,
            dimensions=config.dimensions,
            # The one client on the review path that had no deadline at all.
            # `sync_client_kwargs` defaults to `{}`, the ollama client's own default is
            # `timeout=None`, and httpx reads `None` as "wait forever" — so a local embedder
            # that stopped answering hung the review rather than failing it. Retrieval runs
            # once per candidate and before any judging, which is what made it the worst
            # place for it: the run sat with nothing judged, no error, and no timeout to end
            # it. Every sibling here already carries one.
            sync_client_kwargs={"timeout": _EMBEDDING_TIMEOUT_SECONDS},
        )
        if not _sends_task_prompts(config):
            return embeddings
        return TaskPromptedEmbeddings(
            embeddings,
            query=EMBEDDINGGEMMA_QUERY_PROMPT,
            document=EMBEDDINGGEMMA_DOCUMENT_PROMPT,
        )
    raise ConfigurationError(f"Unsupported LangChain embedding provider: {config.provider}")
