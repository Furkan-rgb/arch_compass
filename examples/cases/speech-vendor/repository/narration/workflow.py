"""One narration job, start to finish."""

from __future__ import annotations

from library.storage import BookStore
from narration.delivery import AudioSink
from narration.planning import VoiceResolver
from preflight.voices import VoiceValidator
from provider.speech import SpeechProvider


class NarrationService:
    """Reads a book, narrates every chapter, writes the audio out."""

    def __init__(
        self,
        books: BookStore,
        speech: SpeechProvider,
        voices: VoiceResolver,
        checks: VoiceValidator,
        sink: AudioSink,
    ) -> None:
        self._books = books
        self._speech = speech
        self._voices = voices
        self._checks = checks
        self._sink = sink

    def narrate(self, book_id: str, voice: str) -> int:
        self._checks.check(voice)
        chosen = self._voices.resolve(voice)
        chapters = self._books.chapters(book_id)
        for number, text in enumerate(chapters, start=1):
            self._sink.write(book_id, number, self._speech.synthesize(text, chosen))
        return len(chapters)
