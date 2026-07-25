# ADR 0003 — Derive context budgets from the model window; phrasing belongs to the classifier

**Status:** Accepted
**Date:** 2026-07-25
**Supersedes:** the frozen ceilings and resolution mandate in master plan §16 (edited alongside)
**Related:** ADR 0001 (composed synthesis), ADR 0002 (legacy purge)

## Context

Master plan §16 — the V1.2 milestone section — froze implementation choices into
constitutional language: a "24,000 retrieved characters" ceiling, "deterministic finding
resolution by … numeric or word ordinal, and unambiguous recent reference", and
"retaining deprecated stored rows" for a removed feature. The section was written by the
same process that produced the implementation, so it reads as spec but functions as a
log of what got built.

The owner asked what the 24,000-character budget was for, whether it was still needed,
and authorized removing mechanisms that exist only because §16 froze them, judged
against the plan's actual principles: bounded contexts (§7, invariants 8/9), validated
references (invariant 14), honest audit (§12).

## What the audit found

**The 24,000-character budget** bounded the serialized evidence retrieved per
conversation turn. Its purpose — keeping the assembled context inside the model window —
is real; its value was frozen before the prompt was measurable and demonstrably fought
the system's own data: one projected finding of the project's evaluation fixture
serializes to ~15,000 characters, so a two-finding turn exhausted the budget before any
Atlas artifact was reached. A test passed only because it happened to ask about the
smaller finding. Since WS5, the transport guard measures the real request against the
real window, which makes a frozen application-layer copy of that constraint redundant
*as a hard limit* — but a budget is still wanted as a *focus* mechanism (§7: the model
should not receive everything that fits).

**A second frozen cap** surfaced immediately: `MAX_CONVERSATION_CONTEXT_CHARACTERS =
56_000` on the assembled context, same disease one layer up.

**The English phrasing parser** in the conversation service (`_ORDINAL_WORDS`,
`_is_comparison`, phrase→question-type tables, demonstrative resolution) re-implemented
the classifier's job with keyword tables and converted ordinary phrasing into hard
errors — eleven of the twenty raise sites in the service were phrasing-driven. The
deterministic provider mirrored five of those rules and raised first. WS4b existed
solely to soften failures this parser created.

**The `report_follow_ups` table** was retained by a §16 mandate for rows that were never
read after the feature's API and UI were removed.

## Decision

1. **Budgets derive from the model configuration.** `domain/budgets.py` computes the
   per-turn retrieved-evidence budget as half of `(context_window − max_output) ×
   chars_per_token`, and the assembled-context cap as nine tenths of it, both floored at
   1,000 characters. The shares are declared constants with stated purpose; the
   transport guard remains the hard backstop. A workspace may still narrow the evidence
   budget explicitly (`max_retrieved_text_characters`), which is also the test seam.
   With the default 32k window the evidence budget is 32,768 characters — the eval
   fixture's findings fit again, and a larger window means a larger budget without a
   code change.
2. **Phrasing interpretation belongs to the classifier.** The service deterministically
   resolves only explicit references — canonical `FIND-nnn` IDs and exact titles, a
   shared title resolving to every finding that carries it — and grounds the plan in the
   pinned report's evidence. The keyword tables are deleted from the service, and the
   deterministic provider's mirrored raise sites become graceful degradation: an
   unresolvable reference yields a smaller plan, never a failed turn. Downstream
   validation against closed identity sets is unchanged (invariant 14 intact).
3. **The deprecated table is dropped** by migration 007. Nothing read it; ArchCompass
   has never been released. This amends ADR 0002's "no migration deletes stored rows"
   consequence with the owner's explicit authorization — recorded here rather than
   silently contradicted.

## Consequences

- No conversation turn can fail because of how a question was phrased. The failure
  modes WS4b was chartered to soften no longer exist, so **WS4b is retired**: a real
  classifier can already produce a digest-cited clarifying answer within the existing
  schema when a reference is genuinely ambiguous.
- Asking about two findings at once, or about a title two findings share, now answers
  about both — previously a hard error. Covering explicitly named findings is
  resolution, not guessing, so §16's "ambiguity fails explicitly" principle is
  preserved where it applies: to genuinely unresolvable input, which now simply
  resolves to less.
- Master plan §16, AGENTS.md, and the subsystem docs are edited to describe principles
  (derived budgets, classifier-owned phrasing) rather than frozen values.
- Two evaluation-matrix tests that pinned the removed raises were rewritten to assert
  the new behaviour; the other 46 matrix tests passed unchanged, confirming the parser
  removal touched mandate, not machinery.
- Durable-row shape caps (excerpt snapshot text, audit list lengths, the 12-finding
  report cap, summary batch sizes) are deliberately untouched: they bound persisted
  rows, not model context, and nothing observed fights them. They can be revisited if
  evidence appears.
