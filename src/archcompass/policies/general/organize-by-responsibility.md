---
id: organize-by-responsibility
title: Organize by responsibility rather than temporal sequence
scope: general
strength: guidance
tags: [temporal-decomposition, cohesion, ownership]
source:
  author: ArchCompass
  inspiration:
    - "John Ousterhout, temporal decomposition"
    - "David Parnas, information hiding"
---
## Intent
Avoid modules that are merely named after when code runs.
## Guidance
Place each step with the owner of its knowledge and let workflows coordinate those owners.
## Signals
Modules named `before`, `during`, or `after` mix unrelated validation, provider, and persistence rules.
## Diagnostic questions
What invariant or knowledge makes the code in this module belong together?
## Likely consequences
Responsibilities remain cohesive even when workflow order changes.
## Exceptions
A workflow or pipeline object may explicitly own sequencing without owning every step's details.
## Positive example
Preflight coordinates provider validation rather than reimplementing provider capability rules.
## Counterexample
Every execution phase becomes a layer that all features must modify.
## Related policies
See `assign-clear-ownership` and `pull-complexity-downward`.
