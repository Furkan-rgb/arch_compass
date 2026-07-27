"""Concatenate rendered passages and write the finished file with its tags."""

from __future__ import annotations

SAMPLE_RATE = 24_000
FILE_WRITE_TIMEOUT = 30.0


def stitch(passages: list[bytes]) -> bytes:
    return b"".join(passages)


def write_audiobook(path: str, audio: bytes, *, title: str, narrator: str) -> None:
    tags = {
        "title": title,
        "artist": narrator,
        # The backend's name, written into the file this module produces.
        "encoded_by": "Qwen3-TTS",
        "comment": f"Narrated with Qwen3-TTS at {SAMPLE_RATE} Hz",
    }
    _write(path, audio, tags)


def _write(path: str, audio: bytes, tags: dict[str, str]) -> None:
    return None
