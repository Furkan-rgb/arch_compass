---
id: assign-clear-ownership
title: Give each responsibility one clear owner
scope: general
strength: guidance
tags: [responsibility, ownership, boundaries]
source:
  author: ArchCompass
  inspiration: [responsibility-driven design literature]
---
## Intent
Make it clear where behavior and decisions belong.
## Guidance
Assign ownership according to knowledge and invariants, not convenience or call order.
## Signals
Several modules can answer the same domain question or none can answer it completely.
## Diagnostic questions
Which module has the information and authority to maintain this invariant?
## Likely consequences
Changes have an obvious destination and duplicated decisions decline.
## Exceptions
Shared protocols intentionally distribute responsibility but should still name each participant's role.
## Positive example
The provider owns capability discovery; the workflow owns job sequencing.
## Counterexample
A miscellaneous manager owns behavior simply because it is globally reachable.
## Related policies
See `organize-by-responsibility` and `hide-implementation-details`.
