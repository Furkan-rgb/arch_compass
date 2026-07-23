"""Model-provider ports."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def identity(self) -> tuple[str, str, int]: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...
