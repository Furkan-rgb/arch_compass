---
id: preserve-reversibility
title: Prefer decisions you can revisit cheaply
scope: general
strength: guidance
tags: [decisions, reversibility, options]
source:
  author: ArchCompass
  inspiration: ["Andrew Hunt & David Thomas, The Pragmatic Programmer", "Mary & Tom Poppendieck, Lean Software Development"]
description: >-
  The cost of a decision includes the cost of unmaking it. Commit quickly where
  reversal is cheap, and defer, contain, and document the choices that would be
  expensive to undo.
---
## Intent
Keep the cost of being wrong low by favoring decisions that can be revisited, and spend
deliberation where reversal is expensive.
## Guidance
Price every decision twice: what it costs to make and what it costs to unmake. Choices that
are cheap to reverse — a module layout, a naming scheme, an internal algorithm — should be
made quickly and revised freely. Choices that are expensive to reverse — a persisted data
model, a published interface, a boundary other teams will build against — should be
deferred until the evidence is in, then weighed against at least one serious alternative
before committing. Where a commitment cannot wait, reduce its reach: put the choice behind
a seam, keep the number of places that know about it small, and write down why it was made
so a later reader can judge whether the reasons still hold. The aim is not indecision but
holding the expensive doors open longer than the cheap ones.
## Signals
A choice made in an afternoon now appears in stored records, external contracts, and other
teams' code. Design discussions treat "we already built it this way" as the argument for
continuing. Payload and column shapes were chosen for what was convenient to emit rather
than what consumers will need to read for years. Nobody can state what would have to become
true for the decision to be reopened.
## Diagnostic questions
If this turns out to be wrong in six months, what does undoing it involve? Are we
committing now because the information is available, or because a decision was due? Which
parts of this design can we still change without coordinating with anyone outside the
component?
## Likely consequences
Reversible designs let a team learn from production instead of from argument, and mistakes
cost a refactor rather than a migration. Systems that accumulate irreversible commitments
early spend their later years working around decisions taken when the least was known, and
every subsequent design conversation starts from constraints nobody chose deliberately.
## Exceptions
Some commitments are the point: a public contract is valuable precisely because it will not
change, and hedging it with versions and toggles buys optionality nobody asked for. Under a
hard external deadline an irreversible choice with a known cost may beat an open option
with an unknown one, provided the cost is stated at the time rather than discovered later.
## Positive example
A team must choose an event format for a new stream. They ship the first consumers reading
through a small translation layer they own, so the wire format stays private while the
fields settle; when the format is finally published they have three real consumers' worth
of evidence and only one place to change.
## Counterexample
An identifier scheme is picked in the first week as a composite of tenant, region, and
sequence number, and stamped into stored rows, log lines, and an exported report. When a
tenant later needs to move regions, the identifier has become a fact about the world that
cannot be restated, and the remedy is a permanent mapping table nobody wanted to own.
## Related policies
See `design-it-twice`, `record-design-rationale`, `delay-premature-abstraction`, and
`design-for-replaceability`.
