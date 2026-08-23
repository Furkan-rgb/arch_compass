"""SQLite persistence for clean-break Finding cache records."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

from archcompass.domain import Finding, Review
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction


def _finding_identity(finding: Finding) -> str:
    """What this finding is about, apart from what it concluded.

    `record_sources` used to find a cached row by its whole encoded document. That held
    only while a finding's bytes never changed between being cached and being recorded,
    and a second pass that settles a hinge changes them: the finding the review holds is
    no longer the finding the cache stored, so the match found nothing and every
    investigated finding silently lost the review that made it durable.

    So the join is on what does not move. The candidate, the policies it was judged
    against and the model and prompt that judged it are the whole of what a cache key
    describes; the verdict, the reasoning and the hinge are what the judgement *reached*,
    and those are exactly the fields a later pass is allowed to revise.
    """

    return sha256(
        "\0".join(
            (
                str(finding.candidate.id),
                finding.retrieval_identity,
                finding.model_identity,
                finding.prompt_identity,
            )
        ).encode()
    ).hexdigest()


class SQLiteCoreFindingCache:
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction
        self._codec = DataclassRecordCodec(Finding)
        with self._transaction() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_finding_cache (
                    cache_key TEXT PRIMARY KEY,
                    finding_json TEXT NOT NULL,
                    source_review_id TEXT,
                    finding_identity TEXT
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
            # Rows written before this column existed keep a null identity and are simply
            # never matched again. Backfilling would mean decoding every cached document
            # at startup to compute a hash whose only use is attaching provenance to a
            # reuse that has not happened yet, and the next fresh judgement writes the
            # row again with its identity in place.
            if "finding_identity" not in columns:
                connection.execute(
                    "ALTER TABLE core_finding_cache ADD COLUMN finding_identity TEXT"
                )

    def get(self, key: str) -> Finding | None:
        with self._transaction() as connection:
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
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO core_finding_cache(cache_key, finding_json, finding_identity) "
                "VALUES (?, ?, ?) ON CONFLICT(cache_key) DO NOTHING",
                (key, document, _finding_identity(finding)),
            )
            row = connection.execute(
                "SELECT finding_json FROM core_finding_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        assert row is not None
        return self._codec.decode(str(row[0]), description="Cached finding")

    def record_sources(self, review: Review) -> None:
        """Attach the first immutable review that made each cached finding durable.

        Matched on `_finding_identity` rather than on the encoded document, because a
        review may hold a finding that has been revised since it was cached — a hinge
        settled by a later pass is the same judgement about the same candidate, and the
        review that made it durable is the one being recorded now.
        """

        with self._transaction() as connection:
            connection.executemany(
                "UPDATE core_finding_cache SET source_review_id = ? "
                "WHERE finding_identity = ? AND source_review_id IS NULL",
                [
                    (review.id, _finding_identity(finding))
                    for finding in review.findings
                    if finding.reused_from_review_id is None
                ],
            )
