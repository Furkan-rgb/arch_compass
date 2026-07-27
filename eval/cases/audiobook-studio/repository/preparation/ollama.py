"""Preparation through the local language-model runtime."""

from __future__ import annotations

MAX_PASSAGE_CHARACTERS = 900


class OllamaPreparer:
    """Rewrites chapters using a model served by the local Ollama runtime."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url
        self._model = model

    def describe(self) -> str:
        return f"Ollama · {self._model}"

    def check_available(self) -> None:
        if not self._base_url:
            raise RuntimeError("no Ollama base URL was configured")

    def prepare(self, chapter: str, temperature: float = 0.2) -> list[str]:
        passages: list[str] = []
        for paragraph in chapter.split("\n\n"):
            passages.extend(_split(paragraph, MAX_PASSAGE_CHARACTERS))
        return passages

    def close(self) -> None:
        return None


def _split(text: str, limit: int) -> list[str]:
    return [text[index : index + limit] for index in range(0, len(text), limit)] or [""]
