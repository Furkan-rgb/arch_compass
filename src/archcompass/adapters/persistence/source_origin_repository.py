"""Where a fetched directory came from, so that losing the directory is not losing the code.

One row per directory this workspace fetched. Written when the fetch lands, read when the
directory is asked for and is not there — which, on a deployment that deletes the least
recently used source to stay inside its memory, is an ordinary thing to happen rather than a
fault to report.

Keyed by the directory because that is what every stored atlas already refers to and what a
request arrives holding. The name is derived from the address, so a re-fetch of the same
address lands in the same place and the row still describes it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.checkout import SourceOrigin


class SQLiteSourceOriginRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, origin: SourceOrigin) -> None:
        """Remember where this directory came from, replacing whatever was said before.

        Replaced rather than ignored: a directory is named after its address, so the same
        path arriving twice is the same repository fetched again, and the newer answer —
        which may name a newer revision — is the true one.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO source_origins(root_path, url, revision, fetched_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(root_path) DO UPDATE SET
                    url = excluded.url,
                    revision = excluded.revision,
                    fetched_at = excluded.fetched_at
                """,
                (
                    origin.root_path,
                    origin.url,
                    origin.revision,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    def get(self, root_path: str) -> SourceOrigin | None:
        """What was fetched into this directory, or `None` for one nobody fetched.

        `None` is an ordinary answer: a bundled example was never fetched, and neither was
        a folder somebody picked on their own machine.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT root_path, url, revision FROM source_origins WHERE root_path = ?",
                (root_path,),
            ).fetchone()
        if row is None:
            return None
        return SourceOrigin(
            root_path=row["root_path"], url=row["url"], revision=row["revision"]
        )
