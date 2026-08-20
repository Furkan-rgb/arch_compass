"""Composition root: wires the service together and narrates one book."""

from __future__ import annotations

from frontend.catalogue import QwenVoiceList
from frontend.pages import VoicePicker
from library.storage import SqliteBookStore
from narration.delivery import FileAudioSink
from narration.planning import QwenVoiceResolver
from narration.workflow import NarrationService
from preflight.voices import QwenVoiceValidator
from provider.qwen import QwenSpeechProvider

#: What a listener gets when they start a book without picking a voice. One of Qwen's.
DEFAULT_VOICE = "serena"


def build(database_path: str, endpoint: str, output_directory: str) -> NarrationService:
    return NarrationService(
        books=SqliteBookStore(database_path),
        speech=QwenSpeechProvider(endpoint),
        voices=QwenVoiceResolver(),
        checks=QwenVoiceValidator(),
        sink=FileAudioSink(output_directory),
    )


def main() -> None:
    picker = VoicePicker(QwenVoiceList())
    service = build("narrator.db", "https://qwen.example/v1/tts", "audio")
    print(picker.options())
    service.narrate("book-1", DEFAULT_VOICE)
