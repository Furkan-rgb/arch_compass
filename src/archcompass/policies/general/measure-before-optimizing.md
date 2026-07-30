---
id: measure-before-optimizing
title: Optimize from measurements, design for performance only where it is structural
scope: general
strength: guidance
tags: [performance, measurement, simplicity]
source:
  author: ArchCompass
  inspiration: ["Donald Knuth", "John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Complexity spent on unmeasured performance is pure cost. Measure first and
  optimize the proven path, reserving design-time performance work for
  structural choices — data layout, round trips, algorithmic shape — that cannot
  be retrofitted later.
---
## Intent
Spend complexity on performance only where measurement shows it pays, while still making
the structural choices that no later optimization can recover.
## Guidance
Treat any performance change without a measurement as an unjustified increase in
complexity. State what the system must achieve, measure where time actually goes under a
representative load, change the proven path, and measure again to confirm the change earned
its cost: a hot-looking function that turns out to be five percent of runtime does not
justify an unreadable rewrite. Separately, recognize the small set of decisions that are
structural rather than local — how many boundary crossings a request makes, how data is
laid out and grouped, whether an operation is linear or quadratic in something that grows.
Those belong to design time because no profiler lets you retrofit them cheaply. Everything
else waits for evidence.
## Signals
Caches, pooling, and hand-tuned loops appear in code with no benchmark and no recorded
baseline. A change is described as faster without saying faster at what, measured how.
Readability was traded away in a path that runs once per request while a loop issuing one
query per row passes review unremarked. Performance discussion happens entirely in terms of
which construct is faster in general, rather than what this system's profile shows.
## Diagnostic questions
What measurement identifies this as the bottleneck, and under what load? What did this
optimization cost in clarity, and what did it buy when measured afterwards? Is this a local
hot spot we can revisit later, or a structural choice that fixes the system's shape?
## Likely consequences
Measured optimization concentrates complexity in the few places that carry the load and
leaves the rest of the system simple, so most of the code stays easy to change. Unmeasured
optimization pays the complexity everywhere and collects the benefit nowhere, and it
obscures the real bottleneck, which is usually a boundary crossing or a data access pattern
rather than the arithmetic someone tightened.
## Exceptions
Structural decisions have to be made before evidence exists, because the evidence arrives
only after they are expensive to change; a design that requires one remote call per item in
a list is worth rejecting on inspection alone. Well-understood practices that cost nothing
in clarity, such as reserving a known capacity or avoiding an obviously redundant pass, need
no ceremony.
## Positive example
A report endpoint is slow, and profiling against production-shaped data shows most of the
time in serializing fields nobody displays. Narrowing the projection removes the cost in a
few lines, the elaborate caching layer that had been proposed is never built, and the code
reads exactly as it did before.
## Counterexample
A team memoizes results across a request-scoped object graph to avoid recomputation, adding
invalidation rules and a subtle staleness bug. Measurement afterwards shows the
recomputation was under one percent of request time, while the same request made forty
separate calls to a remote service — the actual cost, left untouched because nobody
profiled it.
## Related policies
See `delay-premature-abstraction`, `program-strategically`, and `design-it-twice`.
