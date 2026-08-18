"""Reasoning-model selection stored in the application database."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from archcompass.boundary.base import utc_now
from archcompass.boundary.model_catalog import (
    EmbeddingModelSelection,
    ReasoningModelSelection,
)


class SQLiteCoreModelSelectionRepository:
    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_reasoning_model_choice (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    thinking INTEGER,
                    selected_at TEXT NOT NULL,
                    failed_at TEXT,
                    failure_detail TEXT NOT NULL DEFAULT '',
                    input_token_limit INTEGER,
                    output_token_limit INTEGER
                )
                """
            )

    def get(self) -> ReasoningModelSelection | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT provider, model, thinking, selected_at, failed_at, "
                "failure_detail, input_token_limit, output_token_limit "
                "FROM core_reasoning_model_choice WHERE id = 1"
            ).fetchone()
        return None if row is None else ReasoningModelSelection.model_validate(dict(row))

    def set(self, selection: ReasoningModelSelection) -> ReasoningModelSelection:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO core_reasoning_model_choice(
                    id, provider, model, thinking, selected_at, failed_at,
                    failure_detail, input_token_limit, output_token_limit
                ) VALUES (1, ?, ?, ?, ?, NULL, '', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider, model=excluded.model,
                    thinking=excluded.thinking, selected_at=excluded.selected_at,
                    failed_at=NULL, failure_detail='',
                    input_token_limit=excluded.input_token_limit,
                    output_token_limit=excluded.output_token_limit
                """,
                (
                    selection.provider,
                    selection.model,
                    None if selection.thinking is None else int(selection.thinking),
                    selection.selected_at.isoformat(),
                    selection.input_token_limit,
                    selection.output_token_limit,
                ),
            )
        stored = self.get()
        assert stored is not None
        return stored

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM core_reasoning_model_choice WHERE id = 1")

    def record_failure(self, detail: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE core_reasoning_model_choice SET failed_at = ?, "
                "failure_detail = ? WHERE id = 1",
                (utc_now().isoformat(), detail),
            )

    def clear_failure(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE core_reasoning_model_choice SET failed_at = NULL, "
                "failure_detail = '' WHERE id = 1"
            )


class SQLiteEmbeddingModelSelectionRepository:
    """The independently selected policy-embedding model."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS embedding_model_choice (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    selected_at TEXT NOT NULL
                )
                """
            )

    def get(self) -> EmbeddingModelSelection | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT provider, model, dimensions, selected_at "
                "FROM embedding_model_choice WHERE id = 1"
            ).fetchone()
        return None if row is None else EmbeddingModelSelection.model_validate(dict(row))

    def set(self, selection: EmbeddingModelSelection) -> EmbeddingModelSelection:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO embedding_model_choice(
                    id, provider, model, dimensions, selected_at
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider=excluded.provider,
                    model=excluded.model,
                    dimensions=excluded.dimensions,
                    selected_at=excluded.selected_at
                """,
                (
                    selection.provider,
                    selection.model,
                    selection.dimensions,
                    selection.selected_at.isoformat(),
                ),
            )
        stored = self.get()
        assert stored is not None
        return stored

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM embedding_model_choice WHERE id = 1")
