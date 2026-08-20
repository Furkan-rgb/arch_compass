"""The seam between this service and whichever vendor turns text into audio."""

from __future__ import annotations

from typing import Protocol


class SpeechProvider(Protocol):
    """One vendor's text-to-speech, reduced to the single call narration makes."""

    def synthesize(self, text: str, voice: str) -> bytes: ...
