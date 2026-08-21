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
from archcompass.reasoning.adapters.providers import (
    EMBEDDINGGEMMA_DOCUMENT_PROMPT,
    EMBEDDINGGEMMA_QUERY_PROMPT,
    GOOGLE_FIXED_SAMPLING_MODELS,
    TASK_PROMPTED_OLLAMA_MODELS,
    google_thinking_level,
    ollama_model_family,
)


class TaskPromptedEmbeddings(Embeddings):
    """A model's own task prompts, applied where the provider has no field to carry them.

    Google takes `task_type` on the request, so its embeddings already say whether a text is
    a query or a document to be found. Ollama takes text and nothing else, which leaves the
    prefix as the only way to say it — and for a model trained with these prompts, saying
    nothing is not a neutral default but an input shaped unlike anything it was trained on.

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
        # The chosen depth, as the level Gemini 3 takes. Absent where nothing was asked
        # for, because a request that names no level gets the model's dynamic thinking —
        # which is a behaviour somebody can choose, not a gap to be filled in with a
        # default of ours.
        level = google_thinking_level(config.thinking)
        thinking = {} if level is None else {"reasoning_effort": level}
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
            **thinking,
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
        embeddings = OllamaEmbeddings(
            model=config.model,
            base_url=config.base_url,
            dimensions=config.dimensions,
        )
        if not _sends_task_prompts(config):
            return embeddings
        return TaskPromptedEmbeddings(
            embeddings,
            query=EMBEDDINGGEMMA_QUERY_PROMPT,
            document=EMBEDDINGGEMMA_DOCUMENT_PROMPT,
        )
    raise ConfigurationError(f"Unsupported LangChain embedding provider: {config.provider}")
