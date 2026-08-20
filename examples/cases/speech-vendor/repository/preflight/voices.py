"""Rejecting a job we cannot narrate, before any audio is paid for."""

from __future__ import annotations

from typing import Protocol

#: The voices a request may name. Written out here so a bad request is refused without
#: spending a vendor call on it.
BUILT_IN_VOICES = ["serena", "ryan", "chelsie", "ethan"]


class VoiceValidator(Protocol):
    """Whether a requested voice is one this service can narrate with."""

    def check(self, voice: str) -> None: ...


class QwenVoiceValidator(VoiceValidator):
    """Checks a request against the Qwen account's voices."""

    def check(self, voice: str) -> None:
        if voice not in BUILT_IN_VOICES:
            raise ValueError(f"Unknown Qwen voice: {voice}")
