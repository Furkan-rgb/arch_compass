"""The seams this service reaches the outside world through."""

from __future__ import annotations

from typing import Protocol


class WarehouseFeed(Protocol):
    """One warehouse's stock levels, reduced to the single call reconciliation makes."""

    def current_levels(self) -> dict[str, int]: ...


class StockLedger(Protocol):
    """Where this service keeps what it believes the stock to be."""

    def read_all(self) -> dict[str, int]: ...

    def write_all(self, levels: dict[str, int]) -> None: ...
