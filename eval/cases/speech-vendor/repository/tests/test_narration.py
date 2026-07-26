"""Narration tests.

Every collaborator is substituted here, so nothing in this file counts as a second
implementation of anything — the detector excludes tests when it counts implementations,
and says so in its own limitations.

Note what is not covered: no test compares the voices the picker offers against the ones
narration will actually use. That is the seam the copies drifted at.
"""

from __future__ import annotations

from frontend.catalogue import QwenVoiceList
from frontend.pages import VoicePicker
from narration.workflow import NarrationService
from preflight.voices import QwenVoiceValidator


class StubBookStore:
    def __init__(self, chapters: list[str]) -> None:
        self._chapters = chapters

    def add(self, book_id: str, title: str, chapters: list[str]) -> None:
        self._chapters = chapters

    def chapters(self, book_id: str) -> list[str]:
        return list(self._chapters)


class RecordingSpeech:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def synthesize(self, text: str, voice: str) -> bytes:
        self.calls.append((text, voice))
        return text.encode()


class PassThroughResolver:
    def resolve(self, requested: str) -> str:
        return requested


class AllowAnyVoice:
    def check(self, voice: str) -> None:
        return None


class RecordingSink:
    def __init__(self) -> None:
        self.written: list[tuple[str, int, bytes]] = []

    def write(self, book_id: str, chapter: int, audio: bytes) -> None:
        self.written.append((book_id, chapter, audio))


def _service(speech: RecordingSpeech, sink: RecordingSink) -> NarrationService:
    return NarrationService(
        books=StubBookStore(["chapter one", "chapter two"]),
        speech=speech,
        voices=PassThroughResolver(),
        checks=AllowAnyVoice(),
        sink=sink,
    )


def test_narrates_every_chapter_in_order() -> None:
    speech = RecordingSpeech()
    sink = RecordingSink()

    narrated = _service(speech, sink).narrate("book-1", "ryan")

    assert narrated == 2
    assert [voice for _, voice in speech.calls] == ["ryan", "ryan"]
    assert [chapter for _, chapter, _ in sink.written] == [1, 2]


def test_rejects_a_voice_the_service_does_not_have() -> None:
    try:
        QwenVoiceValidator().check("nobody")
    except ValueError as error:
        assert "nobody" in str(error)
    else:
        raise AssertionError("an unknown voice should be refused")


def test_the_picker_labels_every_voice_it_offers() -> None:
    options = VoicePicker(QwenVoiceList()).options()

    assert [voice for voice, _ in options] == ["serena", "ryan", "chelsie", "ethan"]
    assert all(label for _, label in options)
