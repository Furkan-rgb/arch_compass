"""SQLite persistence for clean-break Finding cache records.

One table, and now one expression of what a judgement is.

There used to be two. `cache_key` was a hash of the judgement's inputs, built before the
call; `finding_identity` was a second hash built afterwards out of the stamps the finding
carried, so that a review could find the row it had made durable. They were meant to name
the same thing and did not. The key carries the `ArchitectureCase` and a hash of the stamps
cannot — the finding records which model, prompt and retrieval judged it, never which case
it was judged under — so two judgements of one candidate under two different cases were one
identity. Measured on the workspace that found it: 231 rows, 137 carrying an identity, only
124 of them distinct. Thirteen pairs, and three of those pairs had reached different
verdicts.

`record_sources` matched on that identity `AND source_review_id IS NULL`, so a review
claimed whichever row of a pair happened to be unclaimed — first null wins, and provenance
is the one thing `docs/charter.md` promises about a verdict.

The fix is not a better second hash, because that is the fix that has already failed here.
`a30648e` made both sides read one corpus fingerprint. `366b7e5` made both sides read one
model identity and one prompt identity, and argued for it in almost these words. Both came
back, because a second expression of a value is a second place to forget a term, and the
next term is always forgotten by someone who never read the argument.

So there is no second expression. The identity of a judgement is this table's own primary
key: `get` and `put` stamp it onto the `Finding` they hand back, and `record_sources` puts
that same string back into a `WHERE cache_key = ?`. Nothing recomputes it, so nothing can
recompute it differently, and a term added to `CachingArchitectureJudge.key` is carried here
without anyone having to notice. That is the shape that held for `database._verify_unchanged`,
which stopped naming a migration and hashed the migration itself.

It also makes the race impossible rather than unlikely: `cache_key` is the primary key, so
each update touches at most one row, and the row it touches is the row that answered.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Final

from archcompass.domain import Finding, Review
from archcompass.persistence.sqlite.codecs import DataclassRecordCodec
from archcompass.persistence.sqlite.database import Transaction

#: The SQLite release that learned `ALTER TABLE … DROP COLUMN`. Older libraries answer the
#: statement with a syntax error, and this is the only `DROP COLUMN` in the repository, so
#: the version is stated here beside the one statement that needs it rather than anywhere a
#: reader would have to go and look for it.
#:
#: It cannot be a dependency instead. `sqlite3` is the standard library bound to whatever
#: `libsqlite3` the interpreter was linked against, so no entry in `pyproject.toml` and no
#: `requires-python` bound can express it — CPython 3.12's own floor is 3.15.2. A line in
#: `pyproject.toml` claiming a minimum would read as a constraint an installer enforces and
#: be nothing of the kind, and the only enforcement left after that is an assertion at
#: startup, which is the failure this guard exists to avoid.
_DROP_COLUMN_SINCE: Final = (3, 35, 0)


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
            # Dropped rather than left in place holding its old values. A column named
            # `finding_identity` beside `cache_key` is an invitation to write a second hash
            # into it, which is the whole of what went wrong, and the 137 values in it were
            # never a sound join — thirteen pairs of rows shared one. Nothing is lost that
            # was right: every row keeps its key, and `source_review_id` keeps whatever it
            # was already attributed to. The drop happens here rather than in a migration
            # because a migration would have to `CREATE TABLE IF NOT EXISTS` the old shape
            # first — migrations run before the repositories build their own tables — and a
            # second declaration of this table is the same mistake in a different column.
            #
            # Skipped rather than attempted on a library too old to know the statement,
            # because the two costs are not comparable. What the drop buys is that no later
            # reader can write a second hash into a dead column — a hazard to code that has
            # not been written yet, and one a review catches, since nothing names the column
            # any more. What an unguarded `DROP COLUMN` costs on such a library is every
            # process that opens a workspace, on the first line of the finding cache, before
            # a single review can be read. A dead column is survivable; a product that will
            # not open is not.
            #
            # Nothing goes wrong in the meantime. The column was declared nullable, `put`
            # names the columns it inserts, and `get` and `record_sources` name the columns
            # they read, so a surviving `finding_identity` holds NULL for every new row and
            # is read by nothing. Nor is the drop abandoned: this runs on every open, so the
            # first open by a library that does know the statement drops the column — old
            # values, the rows an old library added, and all. The order does not matter
            # either way, because once the column is gone `PRAGMA table_info` stops
            # mentioning it and an old library never reaches the statement at all.
            if (
                "finding_identity" in columns
                and sqlite3.sqlite_version_info >= _DROP_COLUMN_SINCE
            ):
                connection.execute(
                    "ALTER TABLE core_finding_cache DROP COLUMN finding_identity"
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
        finding = replace(
            self._codec.decode(str(row[0]), description="Cached finding"), cache_key=key
        )
        source = None if row[1] is None else str(row[1])
        return finding if source is None else replace(finding, reused_from_review_id=source)

    def put(self, key: str, finding: Finding) -> Finding:
        # The key is deliberately not written into `finding_json`. The row already holds it,
        # in the column the row is found by, and a copy inside the document would be a second
        # place for it to disagree with itself — which is the defect this table is recovering
        # from, in miniature. `cache_key` is cleared on the way in for the same reason, so
        # that a finding read under one key can never be stored carrying another.
        document = self._codec.encode(replace(finding, cache_key=""))
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO core_finding_cache(cache_key, finding_json) VALUES (?, ?) "
                "ON CONFLICT(cache_key) DO NOTHING",
                (key, document),
            )
            row = connection.execute(
                "SELECT finding_json FROM core_finding_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        assert row is not None
        return replace(
            self._codec.decode(str(row[0]), description="Cached finding"), cache_key=key
        )

    def record_sources(self, review: Review) -> None:
        """Attach the first immutable review that made each cached finding durable.

        Matched on the row's own key, which the finding is carrying because this class put it
        there. That is what makes a revised finding still find its row: the join used to be
        the whole encoded document, and any later `replace` — a settled hinge, an
        investigation identity stamped after the judgement — moved the bytes and lost the
        row. It is also what keeps two judgements that differ only in their case apart, which
        a hash of the finding's own stamps could not do.

        A finding with no key was never in this cache: it is one a tool-using judgement
        produced, or one built outside the cache entirely. Skipped rather than matched,
        because no row's primary key is the empty string and pretending otherwise would only
        make the intent harder to read.
        """

        with self._transaction() as connection:
            connection.executemany(
                "UPDATE core_finding_cache SET source_review_id = ? "
                "WHERE cache_key = ? AND source_review_id IS NULL",
                [
                    (review.id, finding.cache_key)
                    for finding in review.findings
                    if finding.cache_key and finding.reused_from_review_id is None
                ],
            )
