"""Content-addressed policy embeddings stored in the workspace SQLite database."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Final

import sqlite_vec
from langchain_core.embeddings import Embeddings

from archcompass.domain import Policy
from archcompass.domain.errors import PolicyEmbeddingsMissingError
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

#: The schema name a shipped index is attached under. Its rows are read and never written:
#: the file lives in the installed package, where nothing at run time has any business
#: writing, and on the hosted image the process could not write it if it tried.
PREBUILT_SCHEMA: Final = "prebuilt"

#: The workspace's own database. Named in every statement that touches the chunk table
#: rather than left implicit, because with a second database attached an unqualified name is
#: resolved by searching them in order — correct today, and a silent change of meaning the
#: day somebody attaches something before this one.
_MAIN: Final = "main"

#: One chunk as the index stores it, minus the vector: who it belongs to, what it says, and
#: the digest that decides whether the stored vector is still the right one.
type ChunkEntry = tuple[str, str, str, str, str, str | None]


def namespace_for(embedding_identity: str) -> str:
    """The partition of the chunk table one embedding model's vectors live in.

    Vectors from two models are not comparable, so they are not merely tagged apart — they
    are looked up apart. A workspace that switches models finds nothing under the new
    namespace and indexes from scratch, rather than silently scoring against the old.
    """

    return sha256(embedding_identity.encode()).hexdigest()[:24]


def desired_chunks(
    corpus: tuple[Policy, ...], embedding_identity: str
) -> dict[str, ChunkEntry]:
    """Every chunk this corpus should have vectors for, by id, each with its digest.

    A module function rather than a method because two callers need the same answer: the
    index, deciding what to embed, and the checker that asks whether the shipped index is
    still complete. A checker that agreed with `_synchronize` only by having the same four
    lines copied into it would keep agreeing right up until the day somebody changed one.
    """

    desired: dict[str, ChunkEntry] = {}
    for policy in corpus:
        for position, text in enumerate(_chunks(policy), start=1):
            chunk_id = f"{policy.id}:{position}"
            digest = sha256(
                f"{embedding_identity}\0{policy.content_hash}\0{text}".encode()
            ).hexdigest()
            desired[chunk_id] = (
                policy.id,
                digest,
                text,
                policy.scope.value,
                policy.strength.value,
                policy.applies_to,
            )
    return desired


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
        prebuilt: Path | None = None,
        allow_generation: bool = True,
    ) -> None:
        if dimensions < 1:
            raise ValueError("embedding dimensions must be positive")
        self._connect = connect
        self._embeddings = embeddings
        self._embedding_identity = embedding_identity
        self._dimensions = dimensions
        self._namespace = namespace_for(embedding_identity)
        self._allow_generation = allow_generation
        #: A read-only index shipped with the corpus it was built from, or nothing. It saves
        #: the whole of a cold workspace's indexing — which on a metered free tier is minutes
        #: of waiting, paid again by every hosted visitor, for vectors that are identical for
        #: all of them.
        self._prebuilt = prebuilt
        #: Whether the shipped rows are being counted. Decided per synchronize rather than
        #: once here, because it is a fact about this corpus and not about the file: a
        #: workspace pointed at policies the shipped index was not built from must not have
        #: its searches answered from it. Written under `_synchronizing` and read by `search`,
        #: which the retriever only ever calls after synchronizing.
        self._shipped_in_use = False
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
        if self._prebuilt is not None:
            # Attached by plain path rather than a `file:…?mode=ro` URI, which SQLite only
            # honours when the main connection was itself opened with URI filenames on —
            # and that is the workspace database's business, not this adapter's. Nothing
            # here writes to the schema, and the shipped file is mode 0444, which makes
            # SQLite refuse a write even if some later edit forgets.
            connection.execute(
                f"ATTACH DATABASE ? AS {PREBUILT_SCHEMA}", (str(self._prebuilt),)
            )
        return connection

    def _setup(self) -> None:
        with self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS main.policy_embedding_chunks (
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
                """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS main.policy_embedding_policy "
                "ON policy_embedding_chunks(namespace, policy_id)"
            )

    def synchronize(self, corpus: tuple[Policy, ...]) -> None:
        with self._synchronizing:
            self._synchronize(corpus)

    def _synchronize(self, corpus: tuple[Policy, ...]) -> None:
        desired = desired_chunks(corpus, self._embedding_identity)

        with self._connection() as connection:
            own = {
                row[0]: row[1]
                for row in connection.execute(
                    f"SELECT chunk_id, content_hash FROM {_MAIN}.policy_embedding_chunks "
                    "WHERE namespace = ?",
                    (self._namespace,),
                )
            }
            shipped = self._shipped_digests(connection)
            # All or nothing, and decided before anything is embedded. A shipped index
            # holding a chunk this corpus does not want is one built from a different
            # corpus — a workspace pointed at its own policies, or a package whose
            # `general/` moved on without the index being rebuilt. Counting the part that
            # happens to overlap would leave `search` scoring against policies that are not
            # in the corpus, which displaces real matches out of the top K rather than
            # failing where somebody would see it.
            self._shipped_in_use = bool(shipped) and set(shipped) <= set(desired)
            if not self._shipped_in_use:
                shipped = {}
            # A workspace's own row wins: it is the one `_store` wrote for the text the
            # corpus has now, where the shipped copy may be a policy edit behind.
            stored = {**shipped, **own}
            missing = [
                (chunk_id, *entry)
                for chunk_id, entry in desired.items()
                if stored.get(chunk_id) != entry[1]
            ]
            if missing and not self._allow_generation:
                raise PolicyEmbeddingsMissingError(
                    f"No prebuilt policy embeddings found for '{self._embedding_identity}' "
                    f"({len(missing)} chunk(s) missing). Please generate embeddings first "
                    "using 'uv run python scripts/build_policy_index.py'."
                )
            self._embed_missing(connection, missing)
            # Only ever our own rows. The shipped ones are not ours to delete, and nothing
            # asks them to be: where they no longer match, `_shipped_in_use` has already
            # taken the whole file out of play.
            stale = set(own) - set(desired)
            connection.executemany(
                f"DELETE FROM {_MAIN}.policy_embedding_chunks "
                "WHERE namespace = ? AND chunk_id = ?",
                ((self._namespace, chunk_id) for chunk_id in stale),
            )

    def _shipped_digests(self, connection: sqlite3.Connection) -> dict[str, str]:
        """What the attached index holds for this embedding model, or nothing."""

        if self._prebuilt is None:
            return {}
        return {
            row[0]: row[1]
            for row in connection.execute(
                f"SELECT chunk_id, content_hash FROM {PREBUILT_SCHEMA}."
                "policy_embedding_chunks WHERE namespace = ?",
                (self._namespace,),
            )
        }

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
        if (
            isinstance(embeddings, BatchDocumentEmbeddings)
            and embeddings.supports_batch()
        ):
            texts = [entry[3] for entry in missing]
            try:
                self._store(
                    connection, missing, embeddings.embed_documents_batched(texts)
                )
                return
            except BatchUnavailableError as refusal:
                # The batch facility is not available to this key. Indexing the slow way is
                # a worse afternoon than indexing the fast way, and a better one than not
                # having an index.
                _log.warning("%s", refusal)
        for start in range(0, len(missing), _EMBEDDING_BATCH):
            batch = missing[start : start + _EMBEDDING_BATCH]
            self._store(
                connection, batch, self._embed_chunk([entry[3] for entry in batch])
            )

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
                INSERT INTO main.policy_embedding_chunks(
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
                f"""
                SELECT policy_id, MAX(1.0 - vec_distance_cosine(embedding, ?)) AS score
                FROM ({self._chunk_source()})
                GROUP BY policy_id
                ORDER BY score DESC, policy_id ASC
                LIMIT ?
                """,
                (blob, *self._chunk_source_parameters(), limit),
            ).fetchall()
        return tuple(
            DensePolicyMatch(str(policy_id), float(score)) for policy_id, score in rows
        )

    def _chunk_source(self) -> str:
        """The vectors a search scores against: this workspace's, and the shipped ones.

        The shipped arm excludes any chunk the workspace has its own row for, so a policy
        edited here is scored on what it says now rather than on both what it says and what
        it used to. That is the same precedence `_synchronize` applies when it decides what
        to embed, written twice because SQL cannot borrow the dictionary merge.
        """

        own = (
            f"SELECT policy_id, embedding FROM {_MAIN}.policy_embedding_chunks "
            "WHERE namespace = ?"
        )
        if not self._shipped_in_use:
            return own
        return f"""
            {own}
            UNION ALL
            SELECT shipped.policy_id, shipped.embedding
            FROM {PREBUILT_SCHEMA}.policy_embedding_chunks AS shipped
            WHERE shipped.namespace = ?
              AND NOT EXISTS (
                  SELECT 1 FROM {_MAIN}.policy_embedding_chunks AS mine
                  WHERE mine.namespace = shipped.namespace
                    AND mine.chunk_id = shipped.chunk_id
              )
        """

    def _chunk_source_parameters(self) -> tuple[str, ...]:
        return (self._namespace,) * (2 if self._shipped_in_use else 1)
