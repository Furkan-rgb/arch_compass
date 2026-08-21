"""The stored reasoning selection, through the real SQLite repository.

`ModelCatalogService` is tested against an in-memory stand-in for this store, which is why
the shape it could not persist went unnoticed: a thinking *level* — Gemini 3 has
`minimal`/`low`/`medium`/`high` and no switch — was forced through `int()` on the way in,
so choosing any Gemini 3 model in the picker answered 500.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from archcompass.persistence.model_selection import SQLiteCoreModelSelectionRepository
from archcompass.reasoning.records import ReasoningModelSelection
from archcompass.records import THINKING_LEVELS, ThinkingMode


@pytest.fixture
def connect(tmp_path: Path) -> Callable[[], sqlite3.Connection]:
    database = tmp_path / "workspace.db"

    def open_connection() -> sqlite3.Connection:
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        return connection

    return open_connection


def _selection(thinking: ThinkingMode) -> ReasoningModelSelection:
    return ReasoningModelSelection(
        provider="google", model="gemini-3.6-flash", thinking=thinking
    )


@pytest.mark.parametrize("thinking", [None, True, False, *THINKING_LEVELS])
def test_every_thinking_mode_survives_the_round_trip(
    connect: Callable[[], sqlite3.Connection], thinking: ThinkingMode
) -> None:
    """Both shapes of `ThinkingMode`, stored and read back as themselves.

    A switch and a level share one column, so what matters is that they come back told
    apart: `True` must not read as `"minimal"` and `"high"` must not read as `True`.
    """

    repository = SQLiteCoreModelSelectionRepository(connect)

    stored = repository.set(_selection(thinking))

    assert stored.thinking == thinking
    assert (read := repository.get()) is not None and read.thinking == thinking


def test_a_switch_written_by_an_older_build_still_reads_as_a_switch(
    connect: Callable[[], sqlite3.Connection],
) -> None:
    """The column holds 1 and 0 from every workspace that predates thinking levels."""

    repository = SQLiteCoreModelSelectionRepository(connect)
    repository.set(_selection(True))
    with connect() as connection:
        connection.execute("UPDATE core_reasoning_model_choice SET thinking = 1")

    assert (read := repository.get()) is not None and read.thinking is True


def test_a_mode_the_build_no_longer_recognises_falls_back_to_the_default(
    connect: Callable[[], sqlite3.Connection],
) -> None:
    """A preference that cannot be read is not worth refusing to open the workspace over."""

    repository = SQLiteCoreModelSelectionRepository(connect)
    repository.set(_selection("high"))
    with connect() as connection:
        connection.execute("UPDATE core_reasoning_model_choice SET thinking = 'colossal'")

    assert (read := repository.get()) is not None and read.thinking is None
