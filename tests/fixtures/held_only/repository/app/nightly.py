"""The one feed this repository ships."""

from app.ports import SettlementFeed


class NightlyFileFeed:
    def next_batch(self) -> list[str]:
        return []

    def acknowledge(self, batch: str) -> None:
        del batch


def run(feed: SettlementFeed) -> None:
    for batch in feed.next_batch():
        feed.acknowledge(batch)
