"""SQLite persistence for clean-break Finding cache records."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import replace

from archcompass.domain import Finding, Review
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec


class SQLiteCoreFindingCache:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        self._codec = DataclassRecordCodec(Finding)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_finding_cache (
                    cache_key TEXT PRIMARY KEY,
                    finding_json TEXT NOT NULL,
                    source_review_id TEXT
                )
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(core_finding_cache)")
            }
            if "source_review_id" not in columns:
                connection.execute(
                    "ALTER TABLE core_finding_cache ADD COLUMN source_review_id TEXT"
                )

    def get(self, key: str) -> Finding | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT finding_json, source_review_id FROM core_finding_cache "
                "WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        finding = self._codec.decode(str(row[0]), description="Cached finding")
        source = None if row[1] is None else str(row[1])
        return finding if source is None else replace(finding, reused_from_review_id=source)

    def put(self, key: str, finding: Finding) -> Finding:
        document = self._codec.encode(finding)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO core_finding_cache(cache_key, finding_json) VALUES (?, ?) "
                "ON CONFLICT(cache_key) DO NOTHING",
                (key, document),
            )
            row = connection.execute(
                "SELECT finding_json FROM core_finding_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        assert row is not None
        return self._codec.decode(str(row[0]), description="Cached finding")

    def record_sources(self, review: Review) -> None:
        """Attach the first immutable review that made each cached finding durable."""

        with self._connect() as connection:
            connection.executemany(
                "UPDATE core_finding_cache SET source_review_id = ? "
                "WHERE finding_json = ? AND source_review_id IS NULL",
                [
                    (review.id, self._codec.encode(finding))
                    for finding in review.findings
                    if finding.reused_from_review_id is None
                ],
            )
