---
id: record-design-rationale
title: Record consequential design decisions where maintainers will find them
scope: general
strength: guidance
tags: [documentation, decisions, rationale, adr]
source:
  author: ArchCompass
  inspiration:
    - "John Ousterhout, A Philosophy of Software Design (2nd ed.)"
    - "Michael Nygard, architecture decision records"
description: >-
  Code shows what was built, never what was rejected or why. Capture the
  constraints, the alternatives considered, and the conditions that would
  justify revisiting a decision, in a place linked from the code it governs.
---
## Intent
Preserve the constraints and rejected alternatives that the code alone cannot express, so
a deliberate structure is not mistaken for an accidental one.
## Guidance
When a decision is expensive to reverse or its reasons are invisible in the code, record
why the boundary sits where it does and which alternative was rejected, in a discoverable
place linked from the code it governs. Write the forces, not the conclusion: what
constrained the choice, what was tried or ruled out, and what would have to change for the
decision to be revisited. Keep the record next to what it explains, or reachable from it
in one hop, because rationale that lives somewhere a maintainer would not think to look is
the same as no rationale. Record at the moment of deciding, while the alternatives are
still in mind; reconstructed reasoning is usually a defence of what already exists.
## Signals
Settled decisions are re-litigated in every review, a new maintainer simplifies away a
deliberate seam, or the only explanation of a structure lives in an old thread or one
person's memory. A module has an obviously redundant layer that everyone is afraid to
remove. Answers to design questions begin with the phrase we tried that once. Comments
assert that something must not change without saying what breaks if it does.
## Diagnostic questions
If the author left today, what would stop the next refactor from undoing this decision,
and where would a maintainer look first for the reason? Is this choice cheap to reverse,
or does it constrain years of future work? What would have to become true for this
decision to be wrong, and is that written anywhere?
## Likely consequences
Decisions survive turnover, reviews argue against recorded reasoning instead of guesses,
and deliberate seams stop being dismantled by accident. Without a record, every expensive
decision is rediscovered at full price — by re-deriving it, or by undoing it and hitting
the same wall that motivated it.
## Exceptions
Do not document what the code already states, and routine reversible choices need no
ceremony. A rationale that is only restating the diff adds maintenance cost and dilutes
the records that matter; keep the practice for decisions whose reasons are genuinely
invisible.
## Positive example
A decision record explains why report generation is synchronous, which asynchronous design
was rejected and on what grounds, and what measured latency would justify revisiting the
choice. The module links to it, so the next maintainer proposing a queue finds the
argument before writing the code.
## Counterexample
A comment says do not change this without a reason, so the next refactor changes it. The
comment named no constraint, so it read as superstition, and the seam it protected was
removed by someone acting in good faith.
## Related policies
See `make-relationships-discoverable`, `design-it-twice`, and `explicit-source-of-truth`.
Decisions that are expensive to unmake deserve both a record and the scrutiny described in
`preserve-reversibility`.
