"""The composition root: choose the backends, then narrate a book."""

from __future__ import annotations

from pathlib import Path

import config
import preflight
import synthesis
from assembly import audio
from preparation import build as build_preparer
from synthesis import build as build_synthesis


def narrate_book(chapters: list[str], *, output: str, voice_spec: str) -> None:
    missing = preflight.check_environment()
    if missing:
        raise SystemExit(f"missing packages: {', '.join(missing)}")

    preparer = build_preparer(
        config.PREPARATION_BACKEND,
        base_url=config.PREPARATION_BASE_URL,
        model=config.PREPARATION_MODEL,
    )
    speaker = build_synthesis(
        config.SYNTHESIS_BACKEND,
        checkpoint=Path(config.SYNTHESIS_CHECKPOINT),
    )
    speaker.check_available()
    voice = speaker.load_voice(voice_spec)

    rendered: list[bytes] = []
    for chapter in chapters:
        for passage in preparer.prepare(chapter):
            rendered.append(speaker.narrate(passage, voice))

    audio.write_audiobook(
        output,
        audio.stitch(rendered),
        title="An audiobook",
        narrator=speaker.describe(),
    )
    speaker.close()
    preparer.close()


def available_backends() -> tuple[str, ...]:
    return synthesis.names()
