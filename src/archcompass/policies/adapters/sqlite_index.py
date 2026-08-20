"""Content-addressed policy embeddings stored in the workspace SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from threading import Lock

import sqlite_vec
from langchain_core.embeddings import Embeddings

from archcompass.domain import Policy
from archcompass.ports.dense_policy_index import (
    BatchDocumentEmbeddings,
    DensePolicyMatch,
)
from archcompass.reasoning.adapters.google_batch import BatchUnavailableError
from archcompass.retrying import call_with_retry

_log = logging.getLogger("archcompass.batch")

#: How many chunks are embedded per call. Not a throughput knob — one call for the whole
#: corpus is faster where it works. It is a ceiling on how much a single request asks a
#: provider to hold at once, because the corpus is 486 chunks and both providers refuse
#: that differently: a hosted one counts every text against a per-minute allowance, and a
#: local runner was killed outright by the request under memory pressure. Bounding it also
#: means a failure half way through keeps the chunks already written, so the next attempt
#: resumes rather than restarts.
_EMBEDDING_BATCH = 64


def _chunks(policy: Policy) -> tuple[str, ...]:
    """Split at Markdown H2 headings without losing the policy-level introduction."""

    sections: list[list[str]] = [[]]
    for line in policy.body.splitlines():
        if line.startswith("## ") and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    return tuple(
        f"{policy.title}\n\n{'\n'.join(section).strip()}".strip()
        for section in sections
        if "\n".join(section).strip()
    )


class SQLitePolicyIndex:
    """A small exact cosine index; SQLite owns durability and sqlite-vec owns distance."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        embeddings: Embeddings,
        *,
        embedding_identity: str,
        dimensions: int,
    ) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self._connect = connect
        self._embeddings = embeddings
        self._embedding_identity = embedding_identity
        self._dimensions = dimensions
        self._namespace = sha256(embedding_identity.encode()).hexdigest()[:24]
        #: One writer for the chunk table, because a review has many readers of it at
        #: once. The graph fans a candidate out per `Send`, and every one of them
        #: synchronizes before it queries — so without this, the first review of a
        #: workspace embeds the whole corpus once per candidate, concurrently. That is
        #: not merely wasteful: it exhausted a Google free tier inside one review and
        #: took a local Ollama runner down with a reset connection. Holding the lock,
        #: the second caller finds the chunks already stored and embeds nothing.
        self._synchronizing = Lock()
        self._setup()

    @property
    def identity(self) -> str:
        return f"sqlite-vec:{self._namespace}"

    @property
    def embedding_identity(self) -> str:
        return self._embedding_identity

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _connection(self) -> sqlite3.Connection:
        connection = self._connect()
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return connection

    def _setup(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS policy_embedding_chunks (
                    namespace TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    policy_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    strength TEXT NOT NULL,
                    applies_to TEXT,
                    embedding_identity TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    embedding BLOB NOT NULL,
                    PRIMARY KEY (namespace, chunk_id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS policy_embedding_policy "
                "ON policy_embedding_chunks(namespace, policy_id)"
            )

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        with self._synchronizing:
            self._synchronize(corpus)

    def _synchronize(self, corpus: tuple[Policy, ...]) -> None:
        desired: dict[str, tuple[str, str, str, str, str, str | None]] = {}
        for policy in corpus:
            for position, text in enumerate(_chunks(policy), start=1):
                chunk_id = f"{policy.id}:{position}"
                digest = sha256(
                    f"{self._embedding_identity}\0{policy.content_hash}\0{text}".encode()
                ).hexdigest()
                desired[chunk_id] = (
                    policy.id,
                    digest,
                    text,
                    policy.scope.value,
                    policy.strength.value,
                    policy.applies_to,
                )

        with self._connection() as connection:
            stored = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT chunk_id, content_hash FROM policy_embedding_chunks "
                    "WHERE namespace = ?",
                    (self._namespace,),
                )
            }
            missing = [
                (chunk_id, *entry)
                for chunk_id, entry in desired.items()
                if stored.get(chunk_id) != entry[1]
            ]
            self._embed_missing(connection, missing)
            stale = set(stored) - set(desired)
            connection.executemany(
                "DELETE FROM policy_embedding_chunks WHERE namespace = ? AND chunk_id = ?",
                ((self._namespace, chunk_id) for chunk_id in stale),
            )

    def _embed_missing(
        self,
        connection: sqlite3.Connection,
        missing: list[tuple[str, str, str, str, str, str, str | None]],
    ) -> None:
        """Embed every chunk the index does not already hold.

        Building an index is bulk work with nobody waiting on it, which is exactly the shape
        a batch endpoint is for — and it is where a hosted free tier says no, since the
        corpus is hundreds of chunks against a limit counted per minute. Where the provider
        offers a batch the whole corpus goes in one submission; where it does not, the
        chunked loop it always used stays, because a self-hosted Ollama has no limit to
        escape and no batch to escape into.
        """

        if not missing:
            return
        embeddings = self._embeddings
        if isinstance(embeddings, BatchDocumentEmbeddings) and embeddings.supports_batch():
            texts = [entry[3] for entry in missing]
            try:
                self._store(connection, missing, embeddings.embed_documents_batched(texts))
                return
            except BatchUnavailableError as refusal:
                # The batch facility is not available to this key. Indexing the slow way is
                # a worse afternoon than indexing the fast way, and a better one than not
                # having an index.
                _log.warning("%s", refusal)
        for start in range(0, len(missing), _EMBEDDING_BATCH):
            batch = missing[start : start + _EMBEDDING_BATCH]
            self._store(connection, batch, self._embed_chunk([entry[3] for entry in batch]))

    def _embed_chunk(self, texts: list[str]) -> list[list[float]]:
        return call_with_retry(
            lambda: self._embeddings.embed_documents(texts),
            subject=f"Embedding {len(texts)} policy chunks",
        )

    def _store(
        self,
        connection: sqlite3.Connection,
        batch: list[tuple[str, str, str, str, str, str, str | None]],
        vectors: list[list[float]],
    ) -> None:
        for (
            chunk_id,
            policy_id,
            digest,
            text,
            scope,
            strength,
            applies_to,
        ), vector in zip(batch, vectors, strict=True):
            if len(vector) != self._dimensions:
                raise ValueError(
                    f"{self._embedding_identity} returned {len(vector)} dimensions; "
                    f"the configured index expects {self._dimensions}"
                )
            connection.execute(
                """
                INSERT INTO policy_embedding_chunks(
                    namespace, chunk_id, policy_id, content_hash, scope, strength,
                    applies_to, embedding_identity, dimensions, text, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace, chunk_id) DO UPDATE SET
                    policy_id=excluded.policy_id,
                    content_hash=excluded.content_hash,
                    scope=excluded.scope,
                    strength=excluded.strength,
                    applies_to=excluded.applies_to,
                    embedding_identity=excluded.embedding_identity,
                    dimensions=excluded.dimensions,
                    text=excluded.text,
                    embedding=excluded.embedding
                """,
                (
                    self._namespace,
                    chunk_id,
                    policy_id,
                    digest,
                    scope,
                    strength,
                    applies_to,
                    self._embedding_identity,
                    self._dimensions,
                    text,
                    sqlite_vec.serialize_float32(vector),
                ),
            )

    def search(self, query: str, *, limit: int) -> tuple[DensePolicyMatch, ...]:
        if limit < 1:
            return ()
        vector = call_with_retry(
            lambda: self._embeddings.embed_query(query),
            subject="Embedding a policy search",
        )
        if len(vector) != self._dimensions:
            raise ValueError(
                f"{self._embedding_identity} returned {len(vector)} dimensions; "
                f"the configured index expects {self._dimensions}"
            )
        blob = sqlite_vec.serialize_float32(vector)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT policy_id, MAX(1.0 - vec_distance_cosine(embedding, ?)) AS score
                FROM policy_embedding_chunks
                WHERE namespace = ?
                GROUP BY policy_id
                ORDER BY score DESC, policy_id ASC
                LIMIT ?
                """,
                (blob, self._namespace, limit),
            ).fetchall()
        return tuple(DensePolicyMatch(str(policy_id), float(score)) for policy_id, score in rows)
