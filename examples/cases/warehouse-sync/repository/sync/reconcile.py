"""Bring what we believe the stock to be back in line with what the warehouse says."""

from __future__ import annotations

from sync.ports import StockLedger, WarehouseFeed

#: How many SKUs are reconciled in one pass before the ledger is written back. Sized to the
#: warehouse's page limit.
BATCH_SIZE = 200


class Reconciler:
    """Compare the ledger against the feed and write back what changed."""

    def __init__(self, feed: WarehouseFeed, ledger: StockLedger) -> None:
        self._feed = feed
        self._ledger = ledger

    def run(self) -> dict[str, int]:
        believed = self._ledger.read_all()
        actual = self._feed.current_levels()
        changed = {
            sku: count
            for sku, count in actual.items()
            if believed.get(sku) != count
        }
        for start in range(0, len(changed), BATCH_SIZE):
            page = dict(list(changed.items())[start : start + BATCH_SIZE])
            believed.update(page)
        self._ledger.write_all(believed)
        return changed
