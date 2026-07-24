from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from archcompass.adapters.models.deterministic import DeterministicEmbeddingProvider
from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.retrieval.policy_markdown import parse_policy
from archcompass.adapters.retrieval.policy_store import SQLitePolicyStore
from archcompass.bootstrap import BUNDLED_POLICY_SOURCE
from archcompass.domain.errors import PolicyFormatError
from archcompass.domain.policy import PolicyApplicabilityContext


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


class TiedEmbeddingProvider:
    @property
    def identity(self) -> tuple[str, str, int]:
        return ("fake", "tied-v1", 4)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def _write_index_policy(
    path: Path,
    *,
    policy_id: str,
    scope: str,
    applies_to: str | None = None,
) -> None:
    template = (BUNDLED_POLICY_SOURCE / "contain-dependencies.md").read_text(encoding="utf-8")
    scope_metadata = f"scope: {scope}"
    if applies_to is not None:
        scope_metadata += f"\napplies_to: {applies_to}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        template.replace("id: contain-dependencies", f"id: {policy_id}", 1).replace(
            "scope: general",
            scope_metadata,
            1,
        ),
        encoding="utf-8",
    )


def test_policy_index_is_versioned_and_retrievable(runtime) -> None:
    first = runtime.policy_store.rebuild([BUNDLED_POLICY_SOURCE])
    second = runtime.policy_store.rebuild([BUNDLED_POLICY_SOURCE])
    assert first.version_id != second.version_id
    assert len(runtime.policy_store.list_policies(first.version_id)) == 18
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


def test_retrieval_returns_exact_unique_top_k_under_tied_embeddings(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    store = SQLitePolicyStore(
        database,
        TiedEmbeddingProvider(),
        max_sections_per_policy=3,
    )
    version = store.rebuild([BUNDLED_POLICY_SOURCE])

    results = store.retrieve("all distances tie", top_k=10, version_id=version.version_id)
    all_policy_ids = [policy.id for policy in store.list_policies(version.version_id)]

    assert [result.policy.id for result in results] == sorted(all_policy_ids)[:10]
    assert len({result.policy.id for result in results}) == 10
    assert all(1 <= len(result.chunks) <= 3 for result in results)


def test_retrieval_ranking_deduplicates_normalized_sections() -> None:
    policy, chunks = parse_policy(BUNDLED_POLICY_SOURCE / "hide-implementation-details.md")
    duplicate = chunks[0].model_copy(
        update={
            "chunk_id": "duplicate-section",
            "section": chunks[0].section.swapcase(),
        }
    )

    ranked = SQLitePolicyStore._rank_policies(
        [
            (policy, chunks[0], 0.2),
            (policy, duplicate, 0.1),
            (policy, chunks[1], 0.3),
            (policy, chunks[2], 0.4),
            (policy, chunks[3], 0.5),
        ],
        section_limit=3,
    )

    assert len(ranked) == 1
    assert len(ranked[0].chunks) == 3
    assert len({" ".join(chunk.section.split()).casefold() for chunk in ranked[0].chunks}) == 3
    assert duplicate in ranked[0].chunks


def test_retrieval_filters_scoped_policies_while_expanding_for_applicable_top_k(
    tmp_path: Path,
) -> None:
    source = tmp_path / "policies"
    _write_index_policy(
        source / "a-wrong-repository.md",
        policy_id="a-wrong-repository",
        scope="repository",
        applies_to="repo_wrong",
    )
    _write_index_policy(
        source / "b-wrong-user.md",
        policy_id="b-wrong-user",
        scope="user",
        applies_to="user_wrong",
    )
    _write_index_policy(
        source / "y-general.md",
        policy_id="y-general",
        scope="general",
    )
    _write_index_policy(
        source / "z-right-repository.md",
        policy_id="z-right-repository",
        scope="repository",
        applies_to="repo_target",
    )
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    store = SQLitePolicyStore(database, TiedEmbeddingProvider())
    version = store.rebuild([source])

    default_results = store.retrieve(
        "all distances tie",
        top_k=2,
        version_id=version.version_id,
    )
    applicable_results = store.retrieve(
        "all distances tie",
        top_k=2,
        version_id=version.version_id,
        applicability=PolicyApplicabilityContext(repository="repo_target"),
    )

    assert [result.policy.id for result in default_results] == ["y-general"]
    assert {result.policy.id for result in applicable_results} == {
        "y-general",
        "z-right-repository",
    }
    assert len(applicable_results) == 2


def test_repository_local_identity_changes_the_corpus_hash_for_identical_bytes(
    tmp_path: Path,
) -> None:
    first_repository = tmp_path / "first-repository"
    second_repository = tmp_path / "second-repository"
    first_policy = first_repository / ".archcompass" / "policies" / "local.md"
    second_policy = second_repository / ".archcompass" / "policies" / "local.md"
    _write_index_policy(
        first_policy,
        policy_id="local-policy",
        scope="repository",
    )
    second_policy.parent.mkdir(parents=True)
    shutil.copyfile(first_policy, second_policy)
    database = SQLiteDatabase(tmp_path / "archcompass.db")
    database.initialize()
    embeddings = CountingEmbeddingProvider()
    store = SQLitePolicyStore(database, embeddings)

    first = store.ensure_current([first_policy.parent])
    second = store.ensure_current([second_policy.parent])

    assert first.corpus_hash != second.corpus_hash
    assert first.version_id != second.version_id
    assert embeddings.calls == 2
    assert (
        store.get_policy("local-policy", first.version_id).applies_to
        != store.get_policy("local-policy", second.version_id).applies_to
    )
