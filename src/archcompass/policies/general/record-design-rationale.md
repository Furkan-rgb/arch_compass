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
---
## Intent
Preserve the constraints and rejected alternatives that the code alone cannot express.
## Guidance
When a decision is expensive to reverse or its reasons are invisible in the code, record why the boundary sits where it does and which alternative was rejected, in a discoverable place linked from the code it governs.
## Signals
Settled decisions are re-litigated in every review, a new maintainer simplifies away a deliberate seam, or the only explanation of a structure lives in an old thread or one person's memory.
## Diagnostic questions
If the author left today, what would stop the next refactor from undoing this decision, and where would a maintainer look first for the reason?
## Likely consequences
Decisions survive turnover, reviews argue against recorded reasoning instead of guesses, and deliberate seams stop being dismantled by accident.
## Exceptions
Do not document what the code already states, and routine reversible choices need no ceremony.
## Positive example
A decision record explains why report generation is synchronous and what measured latency would justify revisiting, and the module links to it.
## Counterexample
A comment says do not change this without a reason, so the next refactor changes it.
## Related policies
See `make-relationships-discoverable`, `design-it-twice`, and `explicit-source-of-truth`.
