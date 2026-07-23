---
id: pull-complexity-downward
title: Pull unavoidable complexity into the module that can contain it
scope: general
strength: guidance
tags: [complexity, ownership, usability]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Avoid making every caller solve the same difficult problem.
## Guidance
Let a lower-level owner validate, normalize, default, or coordinate details it understands best.
## Signals
Callers repeat setup order, error translation, or provider-specific normalization.
## Diagnostic questions
Which module has enough knowledge to make this decision once?
## Likely consequences
The owning module may become locally sophisticated while system-wide complexity falls.
## Exceptions
Policy decisions that differ by caller should remain explicit at the application boundary.
## Positive example
A provider adapter normalizes its own voice identifiers before returning them.
## Counterexample
A shared helper guesses business policy because moving code downward looked tidy.
## Related policies
See `hide-implementation-details` and `eliminate-errors-by-design`.

