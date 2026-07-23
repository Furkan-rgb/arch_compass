---
id: avoid-duplicated-knowledge
title: Keep each architectural fact in one authoritative place
scope: general
strength: guidance
tags: [knowledge, duplication, change-amplification]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Prevent one conceptual change from requiring synchronized edits.
## Guidance
Consolidate duplicated rules, mappings, and capability knowledge under their natural owner.
## Signals
The same list, constant, validation rule, or conditional appears in unrelated modules.
## Diagnostic questions
Are these copies accidental, cached, or intentionally independent?
## Likely consequences
Changes become atomic and contradictory definitions are less likely.
## Exceptions
Deliberate denormalization is valid when synchronization and ownership are explicit.
## Positive example
Built-in voices are declared by the provider and consumed by preflight and presentation.
## Counterexample
Unrelated code is merged merely because two fragments happen to look alike.
## Related policies
See `explicit-source-of-truth` and `assign-clear-ownership`.

