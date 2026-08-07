from typing import Protocol


class Feed(Protocol):
    def fetch(self, name: str) -> list[str]: ...

    def close(self) -> None: ...
