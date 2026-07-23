"""Immutable policy indexes and sqlite-vec similarity retrieval."""

from __future__ import annotations

import re
from hashlib import sha256
from pathlib import Path

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.retrieval.policy_markdown import load_policy_sources
from archcompass.domain.errors import PolicyFormatError, PolicyNotFoundError
from archcompass.domain.policy import (
    PolicyChunk,
    PolicyDocument,
    PolicyIndexVersion,
    PolicyScope,
    RetrievedPolicy,
)
from archcompass.ports.models import EmbeddingProvider


class SQLitePolicyStore:
    def __init__(
        self,
        database: SQLiteDatabase,
        embeddings: EmbeddingProvider,
        *,
        max_sections_per_policy: int = 3,
    ) -> None:
        if not 1 <= max_sections_per_policy <= 3:
            raise ValueError("max_sections_per_policy must be between one and three")
        self._database = database
        self._embeddings = embeddings
        self._max_sections_per_policy = max_sections_per_policy

    def rebuild(self, sources: list[Path]) -> PolicyIndexVersion:
        parsed = load_policy_sources(sources)
        self._require_policies(parsed)
        return self._build(parsed)

    def ensure_current(self, sources: list[Path]) -> PolicyIndexVersion:
        parsed = load_policy_sources(sources)
        self._require_policies(parsed)
        provider, model, dimensions = self._embeddings.identity
        corpus_hash = self._corpus_hash(parsed)
        current = self.current_version()
        if (
            current is not None
            and current.embedding_provider == provider
            and current.embedding_model == model
            and current.dimensions == dimensions
            and current.corpus_hash == corpus_hash
        ):
            return current
        return self._build(parsed)

    def _build(
        self,
        parsed: list[tuple[PolicyDocument, list[PolicyChunk]]],
    ) -> PolicyIndexVersion:
        provider, model, dimensions = self._embeddings.identity
        version = PolicyIndexVersion(
            embedding_provider=provider,
            embedding_model=model,
            dimensions=dimensions,
            corpus_hash=self._corpus_hash(parsed),
        )
        chunks = [chunk for _, policy_chunks in parsed for chunk in policy_chunks]
        vectors = self._embeddings.embed([chunk.text for chunk in chunks])
        if any(len(vector) != dimensions for vector in vectors):
            raise ValueError(f"Embedding provider did not return {dimensions}-dimension vectors")
        table = self._vector_table(dimensions, version.version_id)
        with self._database.connect(load_vectors=True) as connection:
            connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} "
                f"USING vec0(embedding float[{dimensions}])"
            )
            connection.execute(
                """
                INSERT INTO policy_index_versions(
                    version_id, embedding_provider, embedding_model,
                    dimensions, corpus_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    version.version_id,
                    provider,
                    model,
                    dimensions,
                    version.corpus_hash,
                    version.created_at.isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO policies(version_id, policy_id, policy_json) VALUES (?, ?, ?)",
                [
                    (version.version_id, policy.id, policy.model_dump_json())
                    for policy, _ in parsed
                ],
            )
            for chunk, vector in zip(chunks, vectors, strict=True):
                connection.execute(
                    """
                    INSERT INTO policy_chunks(version_id, chunk_id, policy_id, chunk_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        version.version_id,
                        chunk.chunk_id,
                        chunk.policy_id,
                        chunk.model_dump_json(),
                    ),
                )
                cursor = connection.execute(
                    """
                    INSERT INTO policy_vector_rows(version_id, chunk_id, dimensions)
                    VALUES (?, ?, ?)
                    """,
                    (version.version_id, chunk.chunk_id, dimensions),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not assign a policy vector row ID")
                rowid = cursor.lastrowid
                connection.execute(
                    f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
                    (rowid, self._serialize(vector)),
                )
            connection.commit()
        return version

    @staticmethod
    def _corpus_hash(
        parsed: list[tuple[PolicyDocument, list[PolicyChunk]]],
    ) -> str:
        return sha256(
            "\0".join(policy.content_hash for policy, _ in parsed).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _require_policies(
        parsed: list[tuple[PolicyDocument, list[PolicyChunk]]],
    ) -> None:
        if not parsed:
            raise PolicyFormatError("Policy preflight found no policy documents")

    def current_version(self) -> PolicyIndexVersion | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM policy_index_versions
                ORDER BY created_at DESC, rowid DESC LIMIT 1
                """
            ).fetchone()
        return None if row is None else PolicyIndexVersion.model_validate(dict(row))

    def list_policies(self, version_id: str | None = None) -> list[PolicyDocument]:
        version = self._resolve_version(version_id)
        with self._database.connect() as connection:
            rows = connection.execute(
                "SELECT policy_json FROM policies WHERE version_id = ? ORDER BY policy_id",
                (version.version_id,),
            ).fetchall()
        return [PolicyDocument.model_validate_json(row["policy_json"]) for row in rows]

    def get_policy(self, policy_id: str, version_id: str | None = None) -> PolicyDocument:
        version = self._resolve_version(version_id)
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT policy_json FROM policies WHERE version_id = ? AND policy_id = ?",
                (version.version_id, policy_id),
            ).fetchone()
        if row is None:
            raise PolicyNotFoundError(f"Policy {policy_id} was not found")
        return PolicyDocument.model_validate_json(row["policy_json"])

    def retrieve(
        self,
        query: str,
        *,
        top_k: int,
        version_id: str | None = None,
        max_sections_per_policy: int | None = None,
    ) -> list[RetrievedPolicy]:
        if top_k < 1:
            raise ValueError("top_k must be at least one")
        section_limit = (
            self._max_sections_per_policy
            if max_sections_per_policy is None
            else max_sections_per_policy
        )
        if not 1 <= section_limit <= 3:
            raise ValueError("max_sections_per_policy must be between one and three")
        version = self._resolve_version(version_id)
        vector = self._embeddings.embed([query])[0]
        if len(vector) != version.dimensions:
            raise ValueError("Query embedding dimension differs from the policy index")
        table = self._vector_table(version.dimensions, version.version_id)
        candidates: list[tuple[PolicyDocument, PolicyChunk, float]] = []
        seen_rowids: set[int] = set()
        with self._database.connect(load_vectors=True) as connection:
            total_chunks = int(
                connection.execute(
                    "SELECT COUNT(*) FROM policy_vector_rows WHERE version_id = ?",
                    (version.version_id,),
                ).fetchone()[0]
            )
            if total_chunks == 0:
                return []
            window = min(total_chunks, max(top_k * section_limit, top_k))
            while True:
                nearest = sorted(
                    connection.execute(
                        f"""
                        SELECT rowid, distance FROM {table}
                        WHERE embedding MATCH ?
                        ORDER BY distance LIMIT ?
                        """,
                        (self._serialize(vector), window),
                    ).fetchall(),
                    key=lambda row: (float(row["distance"]), int(row["rowid"])),
                )
                for row in nearest:
                    rowid = int(row["rowid"])
                    if rowid in seen_rowids:
                        continue
                    seen_rowids.add(rowid)
                    joined = connection.execute(
                        """
                        SELECT p.policy_json, c.chunk_json
                        FROM policy_vector_rows v
                        JOIN policy_chunks c
                          ON c.version_id = v.version_id AND c.chunk_id = v.chunk_id
                        JOIN policies p
                          ON p.version_id = c.version_id AND p.policy_id = c.policy_id
                        WHERE v.rowid = ? AND v.version_id = ?
                        """,
                        (rowid, version.version_id),
                    ).fetchone()
                    if joined is None:
                        continue
                    candidates.append(
                        (
                            PolicyDocument.model_validate_json(joined["policy_json"]),
                            PolicyChunk.model_validate_json(joined["chunk_json"]),
                            float(row["distance"]),
                        )
                    )
                ranked = self._rank_policies(candidates, section_limit=section_limit)
                exhausted = len(nearest) >= total_chunks
                if len(ranked) >= top_k:
                    cutoff = ranked[top_k - 1].distance
                    farthest = float(nearest[-1]["distance"])
                    if exhausted or farthest > cutoff:
                        return ranked[:top_k]
                if exhausted:
                    return ranked
                next_window = min(total_chunks, max(window * 2, window + 1))
                if next_window == window:
                    return ranked[:top_k]
                window = next_window

    @staticmethod
    def _rank_policies(
        candidates: list[tuple[PolicyDocument, PolicyChunk, float]],
        *,
        section_limit: int,
    ) -> list[RetrievedPolicy]:
        unique_sections: dict[
            tuple[str, str], tuple[PolicyDocument, PolicyChunk, float]
        ] = {}
        for policy, chunk, distance in candidates:
            section_key = " ".join(chunk.section.split()).casefold()
            key = (policy.id, section_key)
            existing = unique_sections.get(key)
            if existing is None or (
                distance,
                chunk.ordinal,
                chunk.chunk_id,
            ) < (
                existing[2],
                existing[1].ordinal,
                existing[1].chunk_id,
            ):
                unique_sections[key] = (policy, chunk, distance)

        grouped: dict[str, list[tuple[PolicyDocument, PolicyChunk, float]]] = {}
        for candidate in unique_sections.values():
            grouped.setdefault(candidate[0].id, []).append(candidate)

        by_policy: list[RetrievedPolicy] = []
        for policy_id in sorted(grouped):
            matches = sorted(
                grouped[policy_id],
                key=lambda item: (
                    item[2],
                    " ".join(item[1].section.split()).casefold(),
                    item[1].ordinal,
                    item[1].chunk_id,
                ),
            )
            if matches:
                policy = matches[0][0]
                selected = matches[:section_limit]
                by_policy.append(
                    RetrievedPolicy(
                        policy=policy,
                        chunks=[item[1] for item in selected],
                        distance=matches[0][2],
                    )
                )

        scope_rank = {
            PolicyScope.REPOSITORY: 0,
            PolicyScope.ACCEPTED_ADR: 1,
            PolicyScope.ORGANISATION: 2,
            PolicyScope.USER: 3,
            PolicyScope.GENERAL: 4,
        }
        return sorted(
            by_policy,
            key=lambda item: (
                item.distance,
                scope_rank[item.policy.scope],
                item.policy.id,
            ),
        )

    def _resolve_version(self, version_id: str | None) -> PolicyIndexVersion:
        if version_id is None:
            version = self.current_version()
            if version is None:
                raise PolicyNotFoundError("No policy index has been built")
            return version
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM policy_index_versions WHERE version_id = ?", (version_id,)
            ).fetchone()
        if row is None:
            raise PolicyNotFoundError(f"Policy index {version_id} was not found")
        return PolicyIndexVersion.model_validate(dict(row))

    @staticmethod
    def _vector_table(dimensions: int, version_id: str) -> str:
        if dimensions < 1 or dimensions > 65536:
            raise ValueError("Unsupported embedding dimension")
        if re.fullmatch(r"pidx_[0-9a-f]{32}", version_id) is None:
            raise ValueError("Invalid policy index version ID")
        return f"policy_vectors_d{dimensions}_{version_id}"

    @staticmethod
    def _serialize(vector: list[float]) -> bytes:
        from sqlite_vec import serialize_float32

        return serialize_float32(vector)
