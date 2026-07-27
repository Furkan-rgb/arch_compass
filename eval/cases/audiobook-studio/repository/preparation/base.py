"""The text-preparation boundary: turning a chapter into speakable passages."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class NarrationPreparer(Protocol):
    """Rewrites a chapter for narration before any audio is generated."""

    def describe(self) -> str: ...

    def check_available(self) -> None: ...

    def prepare(self, chapter: str) -> list[str]:
        """Split and lightly rewrite *chapter* into passages a narrator can read."""
        ...

    def close(self) -> None: ...
