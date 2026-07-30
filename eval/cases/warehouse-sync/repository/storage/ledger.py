"""The ledger, kept in SQLite.

The only module in this service that knows a database driver exists. Application code is
reviewed for direct driver imports, which is why the boundary in `sync.ports` is here.
"""

from __future__ import annotations

import sqlite3

from sync.ports import StockLedger


class SqliteStockLedger(StockLedger):
    """Stock levels in a local SQLite file."""

    def __init__(self, path: str) -> None:
        self._path = path

    def read_all(self) -> dict[str, int]:
        with sqlite3.connect(self._path) as connection:
            rows = connection.execute("SELECT sku, on_hand FROM stock").fetchall()
        return {str(sku): int(count) for sku, count in rows}

    def write_all(self, levels: dict[str, int]) -> None:
        with sqlite3.connect(self._path) as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO stock (sku, on_hand) VALUES (?, ?)",
                sorted(levels.items()),
            )
