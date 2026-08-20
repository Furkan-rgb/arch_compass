"""Books and their chapter text."""

from __future__ import annotations

import sqlite3
from typing import Protocol


class BookStore(Protocol):
    """Where a book's chapters are kept."""

    def add(self, book_id: str, title: str, chapters: list[str]) -> None: ...

    def chapters(self, book_id: str) -> list[str]: ...


class SqliteBookStore(BookStore):
    """Chapters in a local SQLite file."""

    def __init__(self, database_path: str) -> None:
        self._connection = sqlite3.connect(database_path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS chapters ("
            "book_id TEXT, number INTEGER, title TEXT, body TEXT, "
            "PRIMARY KEY (book_id, number))"
        )

    def add(self, book_id: str, title: str, chapters: list[str]) -> None:
        self._connection.executemany(
            "INSERT OR REPLACE INTO chapters VALUES (?, ?, ?, ?)",
            [
                (book_id, number, title, body)
                for number, body in enumerate(chapters, start=1)
            ],
        )
        self._connection.commit()

    def chapters(self, book_id: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT body FROM chapters WHERE book_id = ? ORDER BY number", (book_id,)
        )
        return [row[0] for row in rows]
