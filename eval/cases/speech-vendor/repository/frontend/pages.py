"""The page a listener picks a voice on before starting a book."""

from __future__ import annotations

from frontend.catalogue import VoiceListSource


class VoicePicker:
    """The voice selector, as the values a template renders."""

    def __init__(self, voices: VoiceListSource) -> None:
        self._voices = voices

    def options(self) -> list[tuple[str, str]]:
        return [(voice, self._voices.label(voice)) for voice in self._voices.available()]
