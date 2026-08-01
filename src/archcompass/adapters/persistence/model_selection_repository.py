"""SQLite persistence for the one reasoning model a workspace has chosen."""

from __future__ import annotations

from archcompass.adapters.persistence.database import SQLiteDatabase
from archcompass.domain.base import utc_now
from archcompass.domain.model_catalog import ReasoningModelSelection

_COLUMNS = (
    "profile_id, provider, model, selected_at, failed_at, failure_detail, "
    "input_token_limit, output_token_limit"
)


class SQLiteReasoningModelSelectionRepository:
    """One row, addressed by a constant.

    `WHERE id = 1` throughout rather than a key of its own: the table's `CHECK (id = 1)`
    already makes a second row impossible, so the constant is the whole address and there is
    nothing to look a selection up by.
    """

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(self) -> ReasoningModelSelection | None:
        with self._database.connect() as connection:
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM reasoning_model_selection WHERE id = 1"
            ).fetchone()
        return None if row is None else ReasoningModelSelection.model_validate(dict(row))

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection:
        """Replace the choice, and with it any failure recorded against the old one.

        Choosing is the act that makes a recorded failure historical: it was a fact about
        the model being replaced. Clearing it here rather than leaving it to the next probe
        means the chip stops reporting a failure the moment the reader has acted on it.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO reasoning_model_selection(
                    id, profile_id, provider, model, selected_at, failed_at,
                    failure_detail, input_token_limit, output_token_limit
                )
                VALUES (1, ?, ?, ?, ?, NULL, '', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    profile_id = excluded.profile_id,
                    provider = excluded.provider,
                    model = excluded.model,
                    selected_at = excluded.selected_at,
                    failed_at = NULL,
                    failure_detail = '',
                    input_token_limit = excluded.input_token_limit,
                    output_token_limit = excluded.output_token_limit
                """,
                (
                    selection.profile_id,
                    selection.provider,
                    selection.model,
                    selection.selected_at.isoformat(),
                    selection.input_token_limit,
                    selection.output_token_limit,
                ),
            )
            row = connection.execute(
                f"SELECT {_COLUMNS} FROM reasoning_model_selection WHERE id = 1"
            ).fetchone()
            connection.commit()
        if row is None:
            raise RuntimeError("The reasoning model selection was not persisted")
        return ReasoningModelSelection.model_validate(dict(row))

    def clear(self) -> None:
        with self._database.connect() as connection:
            connection.execute("DELETE FROM reasoning_model_selection WHERE id = 1")
            connection.commit()

    def record_failure(self, detail: str) -> None:
        """Note that a call against the current selection failed.

        Silent when nothing is selected. The failure is a fact about a choice, and a run
        that had no choice to make failed for a reason this row cannot express.
        """

        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE reasoning_model_selection
                SET failed_at = ?, failure_detail = ?
                WHERE id = 1
                """,
                (utc_now().isoformat(), detail),
            )
            connection.commit()

    def clear_failure(self) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                UPDATE reasoning_model_selection
                SET failed_at = NULL, failure_detail = ''
                WHERE id = 1
                """
            )
            connection.commit()
