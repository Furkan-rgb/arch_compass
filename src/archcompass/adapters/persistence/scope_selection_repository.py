"""Which folders a repository is reviewed without, one row per repository.

Written when an index names a scope, read whenever anything has to reproduce that analysis —
which includes the freshness check, and that is why the choice is stored at all. A scope that
lived only in the request that made it would leave the atlas it produced permanently stale:
the check recomputes the fingerprint, and a fingerprint over more files is a different digest.

Keyed by the canonical root path, which is what every stored atlas already holds.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.errors import UnreadableStoredRecordError


class SQLiteScopeSelectionRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def record(self, root_path: str, excluded_paths: Sequence[str]) -> None:
        """Remember this scope for this repository, replacing whatever was chosen before.

        Replaced rather than merged: the list is the whole of the answer to "what is this
        repository reviewed without", so a caller who removes a folder from it means the
        folder is reviewed again, not that the removal was ignored.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO scope_selections(root_path, excluded_paths, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(root_path) DO UPDATE SET
                    excluded_paths = excluded.excluded_paths,
                    updated_at = excluded.updated_at
                """,
                (
                    root_path,
                    json.dumps(list(excluded_paths)),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    def get(self, root_path: str) -> tuple[str, ...] | None:
        """The folders this repository is reviewed without, or `None` if nobody has chosen.

        An empty tuple is a stored choice to review everything; `None` is the absence of any
        choice. The two lead to the same analysis today and to different ones the moment
        somebody changes their mind, so they are kept apart.
        """

        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT excluded_paths FROM scope_selections WHERE root_path = ?",
                (root_path,),
            ).fetchone()
        if row is None:
            return None
        try:
            stored = json.loads(row["excluded_paths"])
        except json.JSONDecodeError as error:
            raise UnreadableStoredRecordError(
                f"The folders excluded from {root_path} are not readable; index the "
                f"repository again to choose them afresh."
            ) from error
        if not isinstance(stored, list):
            raise UnreadableStoredRecordError(
                f"The folders excluded from {root_path} are not a list of paths; index the "
                f"repository again to choose them afresh."
            )
        entries: list[str] = []
        for item in stored:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(item, str):
                raise UnreadableStoredRecordError(
                    f"The folders excluded from {root_path} are not a list of paths; index "
                    f"the repository again to choose them afresh."
                )
            entries.append(item)
        return tuple(entries)
