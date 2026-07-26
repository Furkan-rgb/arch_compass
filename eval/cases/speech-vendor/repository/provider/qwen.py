"""Qwen, the vendor this service has narrated with since it was written."""

from __future__ import annotations

from provider.speech import SpeechProvider

#: The voices this Qwen account has. Every voice name anywhere in the service is one of
#: these.
BUILT_IN_VOICES = ["serena", "ryan", "chelsie", "ethan"]


class QwenSpeechProvider(SpeechProvider):
    """Qwen's hosted synthesis API."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def synthesize(self, text: str, voice: str) -> bytes:
        # Stands in for the HTTP request the real client sends.
        return f"{self._endpoint}|{voice}|{text}".encode()
