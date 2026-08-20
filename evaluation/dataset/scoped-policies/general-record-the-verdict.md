---
id: general-record-the-verdict
title: Record the decision a review reached and what would reopen it
scope: general
strength: required
tags: [decisions, rationale, reviews]
source:
  author: ArchCompass evaluation
  inspiration: [evaluation fixture]
description: >-
  When a review concludes that a structure is acceptable, the conclusion and the conditions
  that would change it are written down beside the code. An unrecorded acceptance is
  rediscovered as a question every time somebody new reads the same structure.
---
## Intent
Stop the same structural question being re-argued from zero by each reader who meets it.
## Guidance
Record what was judged, what was decided, and the specific condition that would make the
decision wrong — a second implementation appearing, a dependant count crossing a threshold,
a vendor contract ending. Keep it where the code is, and link it from the structure it
governs. State the condition in terms something can check.
## Signals
The same abstraction is questioned in three separate reviews with no record of the first
two. A decision is remembered by one person. A standing exception exists with no written
reason and nobody willing to remove it.
## Diagnostic questions
Where would a new maintainer find why this shape was accepted? What would have to become
true for the decision to be wrong? Who would notice if it did?
## Likely consequences
Reviews get shorter, because settled questions stay settled and the argument resumes only
when the recorded condition actually changes. Without the record, structure drifts by
accumulated re-litigation.
## Exceptions
A decision that is cheap to reverse and easy to see does not need a record; the cost of
writing it down should stay below the cost of rediscovering it.
## Positive example
A note beside the port says one implementation is deliberate while the vendor contract
runs, names the expiry date, and says the port is reconsidered if no second provider exists
by then.
## Counterexample
An abstraction with a single implementation was accepted twice and questioned a third time,
and the only trace of either acceptance is a closed review thread.
## Related policies
record-design-rationale, preserve-reversibility, design-it-twice
