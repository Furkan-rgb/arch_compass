"""Evidence and context budgets.

Two regimes live here, and the difference matters:

* **Count and shape ceilings** (actions, findings, nodes, policies, depth, excerpt
  lines) are fixed contract values. Configuration may lower one, never raise it, and
  each configurable field is bounded above by the constant of the same name.
* **Character budgets** are derived from the configured reasoning model, because the
  real constraint is the model's context window and a frozen number either fights the
  data (the former 24,000-character ceiling could not fit one projected finding of the
  project's own evaluation fixture) or wastes a larger window. The transport guard
  measures the real request and remains the hard backstop; an explicit configuration
  value may narrow a derived budget but never exceed it.

The retrieval floor is deliberately shared by the context derivation: both protect the
same thing, a turn that can still carry at least a minimal evidence payload.
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

# The serialized-evidence budget is derived, not fixed. The former mandated ceiling of
# 24,000 characters was written before the prompt was measurable and could not fit one
# projected finding of the project's own evaluation fixture; the real constraint is the
# configured model window, which the transport guard enforces as the hard backstop.
MIN_RETRIEVED_TEXT_CHARACTERS: Final = 1_000
#: Share of the model's prompt budget available to retrieved evidence. The remainder is
#: reserved for the pinned case summary, finding digests, recent messages, instructions
#: and the response schema.
RETRIEVED_EVIDENCE_SHARE: Final = 0.5


#: Share of the model's prompt budget the fully assembled conversation context may
#: occupy. The remainder is reserved for the stage instruction and the response
#: schema; the transport guard enforces the true window as the hard backstop.
CONTEXT_PROMPT_SHARE: Final = 0.9


def conversation_context_budget(
    *,
    context_window_tokens: int,
    max_output_tokens: int,
    chars_per_token: float,
) -> int:
    """The serialized cap for one assembled conversation context."""

    prompt_characters = (context_window_tokens - max_output_tokens) * chars_per_token
    derived = int(prompt_characters * CONTEXT_PROMPT_SHARE)
    return max(MIN_RETRIEVED_TEXT_CHARACTERS, derived)


def retrieved_character_budget(
    *,
    context_window_tokens: int,
    max_output_tokens: int,
    chars_per_token: float,
) -> int:
    """The per-turn serialized-evidence budget for the configured model."""

    prompt_characters = (context_window_tokens - max_output_tokens) * chars_per_token
    derived = int(prompt_characters * RETRIEVED_EVIDENCE_SHARE)
    return max(MIN_RETRIEVED_TEXT_CHARACTERS, derived)

#: Report claims one turn may cite. Mirrors the report contract rather than standing
#: on its own.
MAX_REPORT_CLAIMS: Final = 16
#: Exact evidence references one durable turn record may carry.
MAX_EVIDENCE_REFERENCES: Final = 128
#: One transient prose field in an assembled context (a query summary, an
#: unavailability reason). Writers truncate to fit; this is the shape bound that keeps
#: an oversized string from failing a turn silently far from its source.
MAX_TRANSIENT_PROSE_CHARACTERS: Final = 24_000
#: How far back a turn reads earlier turns' evidence references when deciding what is
#: already in scope. Distinct from the row cap above: this bounds a query, not a row.
MAX_PRIOR_EVIDENCE_REFERENCES: Final = 96
#: Durable excerpt-snapshot text, per snapshot and per turn. Bounds a stored row, not
#: model context: reasoning always receives the full excerpt.
MAX_SNAPSHOT_CHARACTERS: Final = 24_000

# Bounded conversation context.
RECENT_MESSAGE_LIMIT: Final = 8
MAX_SUMMARY_CHARACTERS: Final = 6_000

# Rolling summary coverage: the first twelve messages, then fixed batches of eight.
# Neither admits an alternative value, so neither is configurable.
SUMMARIZE_AFTER_MESSAGES: Final = 12
SUMMARIZE_EVERY_MESSAGES: Final = 8
