"""The shipped policy index, and the two ways it can be wrong without saying so."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

import pytest

from archcompass.configuration import EmbeddingModelConfig
from archcompass.domain import Policy, PolicyScope, PolicyStrength
from archcompass.domain.errors import (
    ConfigurationError,
    PolicyEmbeddingsMissingError,
)
from archcompass.policies.adapters.prebuilt import (
    MANIFEST_SCHEMA,
    MANIFEST_TABLE,
    coverage,
    read_manifest,
    verify,
)
from archcompass.policies.adapters.sqlite_index import SQLitePolicyIndex, desired_chunks
from archcompass.reasoning.adapters.factory import embedding_identity

_DIMENSIONS = 4


class CountingEmbeddings:
    """Vectors derived from the text, and a tally of how much was asked for.

    The tally is the assertion in most of these tests: what the shipped index buys is not a
    different answer but the same one without the requests, so "did it embed anything" is the
    property, and a mock that only returned vectors could not report it.
    """

    def __init__(self) -> None:
        self.documents: list[str] = []
        self.queries: list[str] = []

    def _vector(self, text: str) -> list[float]:
        return [float(len(text) % 7), float(text.count("a")), 1.0, 0.5]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documents.extend(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vector(text)


def _policy(policy_id: str, body: str) -> Policy:
    return Policy(
        id=policy_id,
        title=policy_id.replace("-", " ").title(),
        body=body,
        scope=PolicyScope.GENERAL,
        strength=PolicyStrength.PREFERRED,
        content_hash=f"hash-of-{body}",
        tags=(),
        applies_to=None,
        source=Path(f"{policy_id}.md"),
    )


def _corpus() -> tuple[Policy, ...]:
    return (
        _policy("keep-it-simple", "An introduction.\n\n## A section\n\nSome text."),
        _policy("name-things-well", "Another policy body."),
    )


def _config(
    model: str = "test-embedding", dimensions: int = _DIMENSIONS
) -> EmbeddingModelConfig:
    return EmbeddingModelConfig(
        provider="fake",
        model=model,
        dimensions=dimensions,
        base_url=None,
        api_key_env=None,
    )


def _connect(path: Path):
    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA journal_mode = DELETE")
        return connection

    return connect


def _build_shipped_index(
    path: Path, corpus: Sequence[Policy], config: EmbeddingModelConfig
) -> CountingEmbeddings:
    """Write an index the way `scripts/build_policy_index.py` does, manifest and all."""

    embeddings = CountingEmbeddings()
    identity = embedding_identity(config)
    index = SQLitePolicyIndex(
        _connect(path),
        embeddings,
        embedding_identity=identity,
        dimensions=config.dimensions,
    )
    index.synchronize(tuple(corpus))
    with sqlite3.connect(path) as connection:
        connection.execute(MANIFEST_SCHEMA)
        connection.execute(
            f"INSERT INTO {MANIFEST_TABLE}(embedding_identity, dimensions, chunk_count) "
            "VALUES (?, ?, ?)",
            (identity, config.dimensions, len(desired_chunks(tuple(corpus), identity))),
        )
    return embeddings


def test_a_shipped_index_spares_the_workspace_every_embedding(tmp_path: Path) -> None:
    corpus = _corpus()
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, corpus, config)

    embeddings = CountingEmbeddings()
    index = SQLitePolicyIndex(
        _connect(tmp_path / "workspace.sqlite3"),
        embeddings,
        embedding_identity=embedding_identity(config),
        dimensions=config.dimensions,
        prebuilt=shipped,
    )
    index.synchronize(corpus)

    assert embeddings.documents == []


def test_a_shipped_index_still_answers_searches(tmp_path: Path) -> None:
    corpus = _corpus()
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, corpus, config)

    index = SQLitePolicyIndex(
        _connect(tmp_path / "workspace.sqlite3"),
        CountingEmbeddings(),
        embedding_identity=embedding_identity(config),
        dimensions=config.dimensions,
        prebuilt=shipped,
    )
    index.synchronize(corpus)

    found = index.search("a section about something", limit=2)

    assert {match.policy_id for match in found} == {item.id for item in corpus}


def test_a_shipped_index_built_for_another_model_is_not_used(tmp_path: Path) -> None:
    corpus = _corpus()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, corpus, _config(model="some-other-embedding"))

    embeddings = CountingEmbeddings()
    index = SQLitePolicyIndex(
        _connect(tmp_path / "workspace.sqlite3"),
        embeddings,
        embedding_identity=embedding_identity(_config()),
        dimensions=_DIMENSIONS,
        prebuilt=shipped,
    )
    index.synchronize(corpus)

    # Every chunk embedded here, rather than a search quietly scoring against vectors from a
    # model these queries will never be compared with.
    assert len(embeddings.documents) == len(
        desired_chunks(corpus, embedding_identity(_config()))
    )


def test_an_edited_policy_is_embedded_and_shadows_the_shipped_chunk(
    tmp_path: Path,
) -> None:
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, _corpus(), config)

    edited = (
        _corpus()[0],
        _policy("name-things-well", "A body that has since been rewritten."),
    )
    embeddings = CountingEmbeddings()
    index = SQLitePolicyIndex(
        _connect(tmp_path / "workspace.sqlite3"),
        embeddings,
        embedding_identity=embedding_identity(config),
        dimensions=config.dimensions,
        prebuilt=shipped,
    )
    index.synchronize(edited)

    # The shipped index no longer covers this corpus, so none of it is counted: the whole
    # corpus is embedded here rather than the one changed chunk being patched over vectors
    # whose provenance nobody can now state.
    assert "A body that has since been rewritten." in "".join(embeddings.documents)
    found = index.search("rewritten", limit=2)
    assert {match.policy_id for match in found} == {item.id for item in edited}


def test_a_shipped_index_holding_a_policy_the_corpus_dropped_is_refused(
    tmp_path: Path,
) -> None:
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, _corpus(), config)

    smaller = (_corpus()[0],)

    found = coverage(shipped, smaller, config)

    assert not found.complete
    assert found.extra
    assert "not in the corpus" in found.explain(
        path=shipped, identity=embedding_identity(config)
    )


def test_coverage_names_a_missing_policy(tmp_path: Path) -> None:
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, (_corpus()[0],), config)

    found = coverage(shipped, _corpus(), config)

    assert not found.complete
    assert any(chunk.startswith("name-things-well") for chunk in found.missing)


def test_coverage_is_complete_for_the_corpus_it_was_built_from(tmp_path: Path) -> None:
    config = _config()
    shipped = tmp_path / "policy-index.sqlite3"
    _build_shipped_index(shipped, _corpus(), config)

    found = coverage(shipped, _corpus(), config)

    assert found.complete
    assert found.manifest is not None
    assert found.manifest.embedding_identity == embedding_identity(config)
    verify(shipped, _corpus(), config)


def test_verify_refuses_an_absent_index(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="no prebuilt policy index"):
        verify(tmp_path / "nothing.sqlite3", _corpus(), _config())


def test_a_file_that_is_not_an_index_has_no_manifest(tmp_path: Path) -> None:
    stray = tmp_path / "policy-index.sqlite3"
    stray.write_text("not a database", encoding="utf-8")

    assert read_manifest(stray) is None


def test_sqlite_index_refuses_missing_embeddings_when_generation_is_disallowed(
    tmp_path: Path,
) -> None:
    corpus = _corpus()
    config = _config()
    index = SQLitePolicyIndex(
        _connect(tmp_path / "workspace.sqlite3"),
        CountingEmbeddings(),
        embedding_identity=embedding_identity(config),
        dimensions=config.dimensions,
        allow_generation=False,
    )

    with pytest.raises(
        PolicyEmbeddingsMissingError, match="No prebuilt policy embeddings found"
    ):
        index.synchronize(corpus)
