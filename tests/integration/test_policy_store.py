from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicEmbeddingProvider
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.retrieval.policy_store import SQLitePolicyStore
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.errors import PolicyFormatError


class CountingEmbeddingProvider:
    def __init__(self, *, model: str = "counting-v1", dimensions: int = 64) -> None:
        self.model = model
        self.dimensions = dimensions
        self.calls = 0
        self._delegate = DeterministicEmbeddingProvider(dimensions)

    @property
    def identity(self) -> tuple[str, str, int]:
        return ("fake", self.model, self.dimensions)

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return self._delegate.embed(texts)


def test_policy_index_is_versioned_and_retrievable(runtime) -> None:
    first = runtime.policy_store.rebuild([BUNDLED_POLICY_SOURCE])
    second = runtime.policy_store.rebuild([BUNDLED_POLICY_SOURCE])
    assert first.version_id != second.version_id
    assert len(runtime.policy_store.list_policies(first.version_id)) == 15
    results = runtime.policy_store.retrieve(
        "provider-specific dependency containment",
        top_k=5,
        version_id=first.version_id,
    )
    assert results
    assert all(result.policy.id for result in results)


def test_policy_preflight_reuses_matching_index_and_rebuilds_stale_index(
    tmp_path: Path,
) -> None:
    source = tmp_path / "policies"
    shutil.copytree(BUNDLED_POLICY_SOURCE, source)
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    embeddings = CountingEmbeddingProvider()
    store = SQLitePolicyStore(database, embeddings)

    first = store.ensure_current([source])
    matching = store.ensure_current([source])

    assert matching.version_id == first.version_id
    assert embeddings.calls == 1

    changed_policy = source / "delay-premature-abstraction.md"
    changed_policy.write_text(
        changed_policy.read_text(encoding="utf-8") + "\nAdditional local guidance.\n",
        encoding="utf-8",
    )
    changed_corpus = store.ensure_current([source])

    assert changed_corpus.version_id != first.version_id
    assert changed_corpus.corpus_hash != first.corpus_hash
    assert embeddings.calls == 2

    changed_embeddings = CountingEmbeddingProvider(model="counting-v2", dimensions=32)
    changed_store = SQLitePolicyStore(database, changed_embeddings)
    changed_model = changed_store.ensure_current([source])

    assert changed_model.version_id != changed_corpus.version_id
    assert changed_model.embedding_model == "counting-v2"
    assert changed_model.dimensions == 32
    assert changed_embeddings.calls == 1


def test_policy_preflight_rejects_an_empty_corpus(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    embeddings = CountingEmbeddingProvider()
    store = SQLitePolicyStore(database, embeddings)

    with pytest.raises(PolicyFormatError, match="found no policy documents"):
        store.ensure_current([tmp_path / "missing"])

    assert embeddings.calls == 0
