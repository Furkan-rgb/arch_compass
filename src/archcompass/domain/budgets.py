"""Mandated V1.2 evidence and context ceilings.

These values are contract, not configuration. The master plan fixes them so that a
persisted conversation turn has a known bound regardless of workspace settings.

Configuration may *lower* a ceiling — that is a useful test and troubleshooting
seam — but never raise one, so every configurable budget is bounded above by the
constant of the same name here. Values that admit exactly one setting are not
exposed as configuration at all.
"""

from __future__ import annotations

from typing import Final

# Per-turn retrieval ceilings.
MAX_ACTIONS_PER_QUESTION: Final = 8
MAX_FINDINGS: Final = 12
MAX_ATLAS_NODES: Final = 24
MAX_POLICIES: Final = 8
MAX_NEIGHBOURHOOD_DEPTH: Final = 2
MAX_EXCERPT_LINES: Final = 120
MAX_TOTAL_EXCERPT_LINES: Final = 180
MAX_RETRIEVED_TEXT_CHARACTERS: Final = 24_000

# Bounded conversation context.
RECENT_MESSAGE_LIMIT: Final = 8
MAX_SUMMARY_CHARACTERS: Final = 6_000

# Rolling summary coverage: the first twelve messages, then fixed batches of eight.
# Neither admits an alternative value, so neither is configurable.
SUMMARIZE_AFTER_MESSAGES: Final = 12
SUMMARIZE_EVERY_MESSAGES: Final = 8
