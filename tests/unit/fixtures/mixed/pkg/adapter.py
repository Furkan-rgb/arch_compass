"""A structural implementation: no inheritance, matching operations."""

from pkg.ports import Feed

BATCH_SIZE = 50


class HttpFeed:
    def fetch(self, name: str) -> list[str]:
        if not name:
            return []
        return [name] * BATCH_SIZE

    def close(self) -> None:
        return None


def build() -> Feed:
    return HttpFeed()
