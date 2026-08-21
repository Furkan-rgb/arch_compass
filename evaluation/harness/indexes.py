"""The retrievers under test, and the baselines that make their scores mean something.

Every one of these satisfies `DensePolicyIndex`, so the production `DensePolicyRetriever`
drives a lexical baseline and a random floor without knowing it. A recall figure with
nothing beside it is unreadable — 0.78 is excellent against a floor of 0.09 and a poor
showing against a keyword search that reaches 0.81 for free.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from hashlib import sha256

import numpy as np
from langchain_core.embeddings import Embeddings

from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain import Policy

# The production chunker, imported rather than reimplemented. A copy here would let the
# evaluation keep scoring a chunking the product had stopped using.
from archcompass.policies.adapters.sqlite_index import _chunks as heading_chunks
from archcompass.ports.dense_policy_index import DensePolicyMatch
from archcompass.reasoning.adapters.factory import (
    TaskPromptedEmbeddings,
    build_embeddings,
    embedding_identity,
)

__all__ = [
    "Bm25PolicyIndex",
    "InMemoryDenseIndex",
    "RandomPolicyIndex",
    "heading_chunks",
    "ollama_config",
    "ollama_embeddings",
    "ollama_identity",
    "whole_document_chunks",
]


def ollama_config(
    *,
    model: str = "embeddinggemma",
    dimensions: int = 768,
    base_url: str = "http://localhost:11434",
) -> EmbeddingModelConfig:
    """What a review would be configured with, so everything below agrees with it."""

    return EmbeddingModelConfig(
        provider="ollama",
        model=model,
        dimensions=dimensions,
        base_url=base_url,
    )


def ollama_identity(
    *,
    model: str = "embeddinggemma",
    dimensions: int = 768,
) -> str:
    """The product's own name for these vectors, never a string written out by hand.

    The notebook needs it to namespace the SQLite index. Assembling it here would let the
    evaluation index under one name while a review reads under another — and the whole
    point of the name is that it changes when the vectors do.
    """

    return embedding_identity(ollama_config(model=model, dimensions=dimensions))


def ollama_embeddings(
    *,
    model: str = "embeddinggemma",
    dimensions: int = 768,
    base_url: str = "http://localhost:11434",
    task_prompts: bool = True,
) -> Embeddings:
    """The local embedding model, built through the same factory a review builds it with.

    `task_prompts=False` hands back what the factory wrapped. The prompts are the product's
    behaviour now, so the ablation is no longer "add them" but "take them away", and taking
    them away has to mean unwrapping the shipped object rather than assembling a second one
    — a hand-built `OllamaEmbeddings` here would keep scoring a path nothing runs.
    """

    built = build_embeddings(
        ollama_config(model=model, dimensions=dimensions, base_url=base_url)
    )
    if task_prompts or not isinstance(built, TaskPromptedEmbeddings):
        return built
    return built.inner


def whole_document_chunks(policy: Policy) -> tuple[str, ...]:
    """One vector per policy: the ablation the production heading split is measured against."""

    return (f"{policy.title}\n\n{policy.body.strip()}".strip(),)


@dataclass
class _EmbeddingCache:
    """One embedding per distinct text per variant, so ablations cost one pass, not four.

    Keyed by the text itself rather than by position: the heading and whole-document
    chunkings share the introduction of every policy, and the four query variants share
    most of their words with each other.
    """

    embeddings: Embeddings
    documents: dict[str, list[float]] = field(default_factory=dict[str, list[float]])
    queries: dict[str, list[float]] = field(default_factory=dict[str, list[float]])
    document_calls: int = 0
    query_calls: int = 0

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        wanted = [text for text in dict.fromkeys(texts) if text not in self.documents]
        for start in range(0, len(wanted), 64):
            batch = wanted[start : start + 64]
            self.document_calls += 1
            self.documents.update(zip(batch, self.embeddings.embed_documents(batch), strict=True))
        return [self.documents[text] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if text not in self.queries:
            self.query_calls += 1
            self.queries[text] = self.embeddings.embed_query(text)
        return self.queries[text]


class InMemoryDenseIndex:
    """The same arithmetic as the shipped SQLite index, with the chunker as a parameter.

    It exists for two reasons the production index cannot serve. Chunking is a variable
    here and a constant there, and an ablation sweep re-embeds nothing because the cache
    outlives the index. The notebook checks it against `SQLitePolicyIndex` on identical
    inputs before trusting a number that came out of it.
    """

    def __init__(
        self,
        embeddings: Embeddings,
        *,
        embedding_identity: str,
        dimensions: int,
        chunker: Callable[[Policy], tuple[str, ...]] = heading_chunks,
        cache: _EmbeddingCache | None = None,
    ) -> None:
        self._cache = cache or _EmbeddingCache(embeddings)
        self._embedding_identity = embedding_identity
        self._dimensions = dimensions
        self._chunker = chunker
        self._policy_ids: tuple[str, ...] = ()
        self._matrix = np.zeros((0, dimensions), dtype=np.float32)

    @property
    def identity(self) -> str:
        return f"memory:{sha256(self._embedding_identity.encode()).hexdigest()[:24]}"

    @property
    def embedding_identity(self) -> str:
        return self._embedding_identity

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def chunk_count(self) -> int:
        return len(self._policy_ids)

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        texts: list[str] = []
        owners: list[str] = []
        for policy in sorted(corpus, key=lambda item: item.id):
            for text in self._chunker(policy):
                texts.append(text)
                owners.append(policy.id)
        vectors = self._cache.embed_documents(texts)
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape[1] != self._dimensions:
            raise ValueError(
                f"{self._embedding_identity} returned {matrix.shape[1]} dimensions; "
                f"this index expects {self._dimensions}"
            )
        self._policy_ids = tuple(owners)
        self._matrix = _unit(matrix)

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]:
        if limit < 1 or not self._policy_ids:
            return ()
        vector = _unit(np.asarray([self._cache.embed_query(query)], dtype=np.float32))
        # Cosine similarity, then the best chunk per policy — the `MAX(...) GROUP BY
        # policy_id` the SQLite index does in the query, done here in the array.
        scores = (self._matrix @ vector[0]).astype(float)
        best: dict[str, float] = {}
        for policy_id, score in zip(self._policy_ids, scores, strict=True):
            if score > best.get(policy_id, -2.0):
                best[policy_id] = score
        return _ranked(best, limit)


_WORD = re.compile(r"[a-z0-9]+")

#: Words that appear in most policies and most queries and separate nothing. Short and
#: hand-written on purpose: a baseline tuned until it wins stops being a baseline.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have", "in", "is",
    "it", "its", "of", "on", "or", "that", "the", "their", "them", "there", "they", "this",
    "to", "was", "were", "what", "when", "where", "which", "who", "will", "with"
})


def _tokens(text: str) -> list[str]:
    return [word for word in _WORD.findall(text.casefold()) if word not in _STOPWORDS]


class Bm25PolicyIndex:
    """Okapi BM25 over the same chunks, as the honest lexical baseline.

    Same shape as the dense index in every respect that could otherwise explain a
    difference: same chunker, same best-chunk-wins reduction, same port. What is left when
    those are held equal is the thing being measured — whether the embedding understands a
    description that shares no vocabulary with the policy that answers it.
    """

    def __init__(
        self,
        *,
        chunker: Callable[[Policy], tuple[str, ...]] = heading_chunks,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._chunker = chunker
        self._k1 = k1
        self._b = b
        self._owners: list[str] = []
        self._frequencies: list[Counter[str]] = []
        self._lengths: list[int] = []
        self._average_length = 0.0
        self._document_frequency: Counter[str] = Counter()

    @property
    def identity(self) -> str:
        return f"bm25:k1={self._k1}:b={self._b}"

    @property
    def embedding_identity(self) -> str:
        return "lexical-baseline"

    @property
    def dimensions(self) -> int:
        return 0

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        self._owners = []
        self._frequencies = []
        self._lengths = []
        self._document_frequency = Counter()
        for policy in sorted(corpus, key=lambda item: item.id):
            for text in self._chunker(policy):
                tokens = _tokens(text)
                self._owners.append(policy.id)
                self._frequencies.append(Counter(tokens))
                self._lengths.append(len(tokens))
                self._document_frequency.update(set(tokens))
        self._average_length = (
            sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        )

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]:
        if limit < 1 or not self._owners:
            return ()
        total = len(self._owners)
        terms = _tokens(query)
        best: dict[str, float] = {}
        for position, counts in enumerate(self._frequencies):
            length = self._lengths[position]
            score = 0.0
            for term in terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                seen = self._document_frequency[term]
                idf = math.log(1.0 + (total - seen + 0.5) / (seen + 0.5))
                denominator = frequency + self._k1 * (
                    1 - self._b + self._b * length / (self._average_length or 1.0)
                )
                score += idf * frequency * (self._k1 + 1) / denominator
            owner = self._owners[position]
            if score > best.get(owner, -1.0):
                best[owner] = score
        return _ranked({key: value for key, value in best.items() if value > 0.0}, limit)


class RandomPolicyIndex:
    """The floor. Deterministic per query, so a rerun of the notebook reproduces it."""

    def __init__(self, *, seed: int = 20260820) -> None:
        self._seed = seed
        self._policy_ids: tuple[str, ...] = ()

    @property
    def identity(self) -> str:
        return f"random:{self._seed}"

    @property
    def embedding_identity(self) -> str:
        return "none"

    @property
    def dimensions(self) -> int:
        return 0

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        self._policy_ids = tuple(sorted(policy.id for policy in corpus))

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]:
        if limit < 1 or not self._policy_ids:
            return ()
        digest = sha256(f"{self._seed}\0{query}".encode()).digest()
        generator = np.random.default_rng(int.from_bytes(digest[:8], "big"))
        draw = generator.permutation(len(self._policy_ids))
        best = {
            self._policy_ids[position]: float(len(self._policy_ids) - rank)
            for rank, position in enumerate(draw)
        }
        return _ranked(best, limit)


def _unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def _ranked(scores: dict[str, float], limit: int) -> tuple[DensePolicyMatch, ...]:
    """Highest score first, ties broken by policy id — the order the SQL query produces."""

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return tuple(DensePolicyMatch(policy_id, float(score)) for policy_id, score in ordered)
