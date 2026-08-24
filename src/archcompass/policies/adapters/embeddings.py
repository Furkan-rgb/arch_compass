"""Environment-selected embeddings behind the stable PolicyRetriever capability."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from threading import Lock

from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain import (
    ArchitectureCase,
    Candidate,
    CandidateId,
    Policy,
    RetrievalProvenance,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.policies.adapters import prebuilt
from archcompass.policies.adapters.sqlite_index import SQLitePolicyIndex
from archcompass.policies.retrieval import (
    DENSE_RETRIEVER_RELEASE_TOP_K,
    DensePolicyRetriever,
    corpus_fingerprint,
)
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet
from archcompass.reasoning.adapters.factory import build_embeddings, embedding_identity

#: What a workspace embeds with when nothing has said otherwise, and therefore the identity
#: the index this package ships is stamped with. The two are one decision: production
#: retrieval never generates a vector, so the shipped file is the only source a review has
#: and whichever identity it carries is the embedder that works out of the box.
#:
#: OpenRouter rather than Google because it is the hosted boundary now, and because the
#: model behind it is the same one — `google/gemini-embedding-2` is Gemini Embedding 2,
#: reached through a different front door at the same 3,072 dimensions.
#:
#: Every other embedder still works and is reached the same way it always was: pin it with
#: `ARCHCOMPASS_EMBEDDING_*` and build its index with `make policy-index`. That has been
#: true of Ollama since the shipped index existed, and it is now true of Google as well.
DEFAULT_EMBEDDING_PROVIDER = "openrouter"
DEFAULT_EMBEDDING_MODEL = "google/gemini-embedding-2"
DEFAULT_EMBEDDING_DIMENSIONS = 3072
DEFAULT_EMBEDDING_API_KEY_ENV = "OPENROUTER_API_KEY"


def embedding_config_from_environment() -> EmbeddingModelConfig:
    provider = (
        os.environ.get("ARCHCOMPASS_EMBEDDING_PROVIDER", "").strip()
        or DEFAULT_EMBEDDING_PROVIDER
    )
    configured_model = os.environ.get("ARCHCOMPASS_EMBEDDING_MODEL", "").strip()
    configured_dimensions = os.environ.get(
        "ARCHCOMPASS_EMBEDDING_DIMENSIONS", ""
    ).strip()
    if provider == DEFAULT_EMBEDDING_PROVIDER:
        model = configured_model or DEFAULT_EMBEDDING_MODEL
        dimensions = configured_dimensions or str(DEFAULT_EMBEDDING_DIMENSIONS)
    else:
        model = configured_model
        dimensions = configured_dimensions
    if not provider or not model or not dimensions:
        raise ConfigurationError(
            "Policy retrieval is unavailable for the selected embedding provider. "
            "Configure ARCHCOMPASS_EMBEDDING_MODEL and "
            "ARCHCOMPASS_EMBEDDING_DIMENSIONS before starting a review."
        )
    try:
        parsed_dimensions = int(dimensions)
    except ValueError as error:
        raise ConfigurationError(
            "ARCHCOMPASS_EMBEDDING_DIMENSIONS must be a positive whole number."
        ) from error
    return EmbeddingModelConfig(
        provider=provider,
        model=model,
        dimensions=parsed_dimensions,
        base_url=os.environ.get("ARCHCOMPASS_EMBEDDING_BASE_URL") or None,
        api_key_env=(
            os.environ.get("ARCHCOMPASS_EMBEDDING_API_KEY_ENV", "").strip()
            or (
                DEFAULT_EMBEDDING_API_KEY_ENV
                if provider == DEFAULT_EMBEDDING_PROVIDER
                else None
            )
        ),
    )


class SelectedDensePolicyRetriever:
    """The minimum retriever, built lazily so an unconfigured workspace can still open."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        *,
        top_k: int = DENSE_RETRIEVER_RELEASE_TOP_K,
        embedding_config: Callable[[], EmbeddingModelConfig] = (
            embedding_config_from_environment
        ),
        deterministic_mode: Callable[[], bool] | None = None,
    ) -> None:
        self._connect = connect
        self._top_k = top_k
        self._embedding_config = embedding_config
        self._cached: tuple[str, DensePolicyRetriever] | None = None
        self._lock = Lock()
        self._deterministic_mode = deterministic_mode or (lambda: False)

    def retrieve(
        self,
        candidate: Candidate,
        case: ArchitectureCase,
        corpus: tuple[Policy, ...],
    ) -> RetrievedPolicySet:
        if self._deterministic_mode():
            ordered = tuple(sorted(corpus, key=lambda item: item.id))
            return RetrievedPolicySet(
                str(candidate.id),
                tuple(PolicySelection(item) for item in ordered),
                RetrievalProvenance(
                    candidate_id=CandidateId(str(candidate.id)),
                    retriever="full-corpus-test-oracle",
                    version="1",
                    corpus_fingerprint=corpus_fingerprint(corpus),
                    selected_policy_ids=tuple(item.id for item in ordered),
                    query_fingerprint=sha256(str(candidate.id).encode()).hexdigest(),
                ),
            )
        config = self._embedding_config()
        # Not `provider:model:dimensions` assembled here: what the index may reuse is
        # decided by what `build_embeddings` does to the text, and only it knows that.
        identity = embedding_identity(config)
        # Asked here rather than once at construction, because whether the shipped index can
        # answer is a fact about the corpus and the corpus is what arrives at this call. It
        # costs a few hundred hashes and one SQLite read, which is nothing beside the
        # hundreds of provider requests it is deciding whether to avoid.
        shipped = prebuilt.usable(corpus, config)
        with self._lock:
            cache_identity = f"{identity}:k={self._top_k}:shipped={shipped}"
            if self._cached is None or self._cached[0] != cache_identity:
                embeddings = build_embeddings(config)
                index = SQLitePolicyIndex(
                    self._connect,
                    embeddings,
                    embedding_identity=identity,
                    dimensions=config.dimensions,
                    prebuilt=shipped,
                    allow_generation=False,
                )
                self._cached = (
                    cache_identity,
                    DensePolicyRetriever(index, top_k=self._top_k),
                )
            retriever = self._cached[1]
        # Synchronization and the first query happen before the judge is resolved, so an
        # unavailable embedding provider refuses the review before reasoning expenditure.
        return retriever.retrieve(candidate, case, corpus)
