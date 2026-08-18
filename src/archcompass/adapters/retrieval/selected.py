"""Environment-selected embeddings behind the stable PolicyRetriever capability."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from threading import Lock

from archcompass.adapters.models.langchain_factory import (
    EmbeddingModelConfig,
    build_embeddings,
)
from archcompass.adapters.retrieval.sqlite_policy_index import SQLitePolicyIndex
from archcompass.application.policy_retrieval import DensePolicyRetriever, corpus_fingerprint
from archcompass.domain.core import (
    ArchitectureCase,
    Candidate,
    CandidateId,
    Policy,
    RetrievalProvenance,
)
from archcompass.domain.errors import ConfigurationError
from archcompass.ports.policy_retrieval import PolicySelection, RetrievedPolicySet


def embedding_config_from_environment() -> EmbeddingModelConfig:
    provider = os.environ.get("ARCHCOMPASS_EMBEDDING_PROVIDER", "").strip()
    model = os.environ.get("ARCHCOMPASS_EMBEDDING_MODEL", "").strip()
    dimensions = os.environ.get("ARCHCOMPASS_EMBEDDING_DIMENSIONS", "").strip()
    if not provider or not model or not dimensions:
        raise ConfigurationError(
            "Policy retrieval is unavailable. Configure ARCHCOMPASS_EMBEDDING_PROVIDER, "
            "ARCHCOMPASS_EMBEDDING_MODEL, and ARCHCOMPASS_EMBEDDING_DIMENSIONS before "
            "starting a review."
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
        api_key_env=os.environ.get("ARCHCOMPASS_EMBEDDING_API_KEY_ENV") or None,
    )


class SelectedDensePolicyRetriever:
    """The minimum retriever, built lazily so an unconfigured workspace can still open."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        *,
        approved_top_k: Callable[[str], int],
        deterministic_mode: Callable[[], bool] | None = None,
    ) -> None:
        self._connect = connect
        self._approved_top_k = approved_top_k
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
        config = embedding_config_from_environment()
        identity = f"{config.provider}:{config.model}:{config.dimensions}"
        top_k = self._approved_top_k(identity)
        with self._lock:
            cache_identity = f"{identity}:k={top_k}"
            if self._cached is None or self._cached[0] != cache_identity:
                embeddings = build_embeddings(config)
                index = SQLitePolicyIndex(
                    self._connect,
                    embeddings,
                    embedding_identity=identity,
                    dimensions=config.dimensions,
                )
                self._cached = (cache_identity, DensePolicyRetriever(index, top_k=top_k))
            retriever = self._cached[1]
        # Synchronization and the first query happen before the judge is resolved, so an
        # unavailable embedding provider refuses the review before reasoning expenditure.
        return retriever.retrieve(candidate, case, corpus)
