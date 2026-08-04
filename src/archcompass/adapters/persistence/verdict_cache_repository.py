"""Verdict persistence keyed by the question rather than by the run.

Writes are first-writer-wins. Two runs asking the same question compute the same key and
would store the same answer under it, so the second write is not a conflict to report; and
where the model was non-deterministic enough to word it differently, the row already there
is the one every earlier reader was shown. Stability is the point of the table, and it
would be a strange kind of stability that let the last writer redefine it.

Nothing here deletes. A cached verdict is true about the structure it judged, and neither
the run that produced it going away nor the case moving on makes it wrong — a question that
has changed simply misses, and misses cost nothing to leave lying around.
"""

from __future__ import annotations

from datetime import datetime

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.adapters.persistence.stored_records import decode_stored_json
from archcompass.domain.review import CandidateVerdict
from archcompass.domain.verdict_cache import CachedVerdict

_REMEDY = (
    "A cached verdict is an optimisation and never the only copy of anything, so deleting "
    "the row is safe: the next review judges that boundary again."
)


class SQLiteVerdictCacheRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(self, cache_key: str) -> CachedVerdict | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT boundary_fingerprint, review_id, created_at, verdict_json
                FROM verdict_cache WHERE cache_key = ?
                """,
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return CachedVerdict(
            cache_key=cache_key,
            boundary_fingerprint=str(row["boundary_fingerprint"]),
            verdict=decode_stored_json(
                CandidateVerdict,
                str(row["verdict_json"]),
                description=f"Cached verdict {cache_key}",
                remedy=_REMEDY,
            ),
            review_id=str(row["review_id"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def put(self, cached: CachedVerdict) -> None:
        """Store this verdict under its key, unless the key already has one."""

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO verdict_cache(
                    cache_key, boundary_fingerprint, review_id, created_at, verdict_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    cached.cache_key,
                    cached.boundary_fingerprint,
                    cached.review_id,
                    cached.created_at.isoformat(),
                    cached.verdict.model_dump_json(),
                ),
            )
            connection.commit()
