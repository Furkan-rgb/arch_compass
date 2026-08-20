"""Settings the application reads at startup."""

from __future__ import annotations

# The backends the wiring may be pointed at, and what each needs. Naming them here is the
# composition root's job: something has to choose, and hiding the choice helps nobody.
SYNTHESIS_BACKEND = "qwen"
SYNTHESIS_CHECKPOINT = "models/Qwen3-TTS-12Hz-1.7B-CustomVoice"
PREPARATION_BACKEND = "ollama"
PREPARATION_MODEL = "gemma3:12b"
PREPARATION_BASE_URL = "http://127.0.0.1:11434"

# Output settings, unrelated to any backend.
SAMPLE_RATE = 24_000
CHAPTER_TIMEOUT = 600.0
