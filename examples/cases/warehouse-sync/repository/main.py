"""Wire the service together and run one reconciliation."""

from __future__ import annotations

from reporting.digest import rebuild_until_complete
from storage.ledger import SqliteStockLedger
from sync.reconcile import Reconciler
from warehouse.northwind import NorthwindFeed


def main() -> str:
    feed = NorthwindFeed("https://northwind.example.com/api")
    ledger = SqliteStockLedger("stock.db")
    changed = Reconciler(feed, ledger).run()
    return rebuild_until_complete(changed)


if __name__ == "__main__":
    print(main())
