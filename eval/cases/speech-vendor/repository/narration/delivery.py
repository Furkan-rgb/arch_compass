"""Where a narrated chapter goes once it exists."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class AudioSink(Protocol):
    """Somewhere finished audio can be put."""

    def write(self, book_id: str, chapter: int, audio: bytes) -> None: ...


class FileAudioSink(AudioSink):
    """Audio as one file per chapter on local disk."""

    def __init__(self, directory: str) -> None:
        self._directory = Path(directory)

    def write(self, book_id: str, chapter: int, audio: bytes) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / f"{book_id}-{chapter:03d}.wav").write_bytes(audio)
