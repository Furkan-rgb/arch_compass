"""Tests for the narration path."""

from __future__ import annotations

from pathlib import Path

from preparation.ollama import OllamaPreparer
from synthesis.qwen import QwenSynthesis


def test_a_chapter_is_split_into_passages() -> None:
    preparer = OllamaPreparer("http://127.0.0.1:11434", "gemma3:12b")

    passages = preparer.prepare("First paragraph.\n\nSecond paragraph.")

    assert len(passages) == 2


def test_a_builtin_voice_is_recognised() -> None:
    speaker = QwenSynthesis(Path("models/checkpoint"))

    voice = speaker.load_voice("builtin:warm")

    assert speaker.narrate("hello", voice)
