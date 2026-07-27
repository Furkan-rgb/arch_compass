"""The one speech backend written so far.

Structural conformance: it does not inherit :class:`SynthesisProvider`, which is how
adapters are ordinarily written against a Protocol.
"""

from __future__ import annotations

from pathlib import Path


class QwenVoice:
    """This backend's own handle, returned where the port declares ``Voice``."""

    def __init__(self, prompt: str) -> None:
        self.prompt = prompt


class QwenBuiltinVoice:
    """A narrator that ships with the checkpoint rather than being cloned."""

    def __init__(self, speaker: str) -> None:
        self.speaker = speaker


class QwenSynthesis:
    """Narration through the locally resident Qwen3-TTS checkpoint."""

    def __init__(self, checkpoint: Path) -> None:
        self._checkpoint = checkpoint
        self._model: object | None = None

    def describe(self) -> str:
        return "Qwen3-TTS"

    def check_available(self) -> None:
        if not self._checkpoint.exists():
            raise RuntimeError("the Qwen checkpoint is not on disk")

    # Returns the concrete handles rather than the abstract one the port declares, and
    # takes an extra optional argument the port does not — both ordinary in an adapter.
    def load_voice(self, spec: str, ref_text: str | None = None) -> QwenVoice | QwenBuiltinVoice:
        if spec.startswith("builtin:"):
            return QwenBuiltinVoice(spec.removeprefix("builtin:"))
        return QwenVoice(ref_text or "")

    def narrate(self, text: str, voice: QwenVoice | QwenBuiltinVoice) -> bytes:
        return text.encode("utf-8")

    def close(self) -> None:
        self._model = None
