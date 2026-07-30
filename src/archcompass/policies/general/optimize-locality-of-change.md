---
id: optimize-locality-of-change
title: Keep one conceptual change local
scope: general
strength: guidance
tags: [locality, change-amplification, dependencies]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  Measure a design by how many places one decision forces you to edit. Knowledge
  that changes together belongs together, so a single conceptual change lands in
  one module instead of rippling through every layer it passes.
---
## Intent
Reduce the coordinated edits a single decision forces. A structure earns its boundaries
when one conceptual change lands in one place.
## Guidance
Group knowledge that changes together and separate responsibilities that change
independently. The unit to design around is the decision, not the file: when adding a
format, a rule, or a backend means editing a validator, a workflow, a presentation layer,
and a composition root, all four encode the same knowledge and the boundaries between
them are not paying for themselves. Prefer seams where a new case arrives as data — one
registration, one table entry, one more implementation of an existing contract — rather
than as a coordinated patch across layers. Where a change must genuinely touch several
places, keep that set explicit and small enough that a reviewer sees all of it in one
diff. Locality is not centralization; collapsing unrelated responsibilities into one
module makes changes local only by making everything share fate.
## Signals
Adding one provider requires changes in presentation, validation, workflow, and root
composition. A checklist or a comment exists telling maintainers which other files to
update when they add a case. Reviews keep catching changes that updated three of the four
required places and missed the fourth. Version-control history shows the same file set
changing together again and again with no module that contains them.
## Diagnostic questions
Which files change together, and is there one responsibility behind those edits? If a new
case arrived tomorrow, how many places would a maintainer have to find, and how would they
know they had found them all? Is the repetition here genuinely shared knowledge, or the
same word appearing in unrelated contexts?
## Likely consequences
Feature changes touch fewer locations, and partial updates — the case added in three
places out of four — become far less likely. Change amplification compounds: a design
where each decision costs five edits slows with every feature until the cost of a change
is dominated by locating its sites rather than making it.
## Exceptions
Cross-cutting security or compliance changes may intentionally affect many boundaries; a
requirement that must hold everywhere is supposed to be visible everywhere. Deliberate
duplication across a stable published contract, with independent consumers on either side,
can also be cheaper than the coupling that removing it would introduce.
## Positive example
Adding a provider requires one adapter and one composition registration. That adapter owns
the provider's capability description, its defaults, and its error translation, so the
workflow, the validation layer, and the presentation layer never learn the new provider
exists.
## Counterexample
A large central module is justified only because all changes are now in one file.
Unrelated features share its state and its release risk, every edit needs review from
people who own none of the other concerns, and the apparent locality is just the absence
of any boundary at all.
## Related policies
See `avoid-duplicated-knowledge`, `contain-dependencies`, and
`split-or-join-by-shared-knowledge`. When the amplification comes from a shared
abstraction that no longer fits its callers, see `back-out-of-wrong-abstractions`.
