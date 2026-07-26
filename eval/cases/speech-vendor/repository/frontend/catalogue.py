"""The voices the picker offers, and how each one is spelled for a reader."""

from __future__ import annotations

from typing import Protocol

#: What the picker shows. Kept here so a page renders without waiting on a vendor call.
BUILT_IN_VOICES = ["serena", "ryan", "chelsie", "ethan"]

#: How each voice is written in the picker.
DISPLAY_NAMES = {
    "serena": "Serena — warm",
    "ryan": "Ryan — neutral",
    "chelsie": "Chelsie — bright",
    "ethan": "Ethan — low",
}


class VoiceListSource(Protocol):
    """Where the picker gets the voices it offers."""

    def available(self) -> list[str]: ...

    def label(self, voice: str) -> str: ...


class QwenVoiceList(VoiceListSource):
    """The picker's list, spelled out for the Qwen account."""

    def available(self) -> list[str]:
        return list(BUILT_IN_VOICES)

    def label(self, voice: str) -> str:
        return DISPLAY_NAMES.get(voice, voice.title())
