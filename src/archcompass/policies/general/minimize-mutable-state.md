---
id: minimize-mutable-state
title: Minimize and localize mutable state
scope: general
strength: guidance
tags: [state, immutability, complexity]
source:
  author: ArchCompass
  inspiration: ["Ben Moseley & Peter Marks, Out of the Tar Pit"]
description: >-
  Every value that can change multiplies the situations a reader has to hold in
  mind. Prefer immutable values, derive what can be derived, and confine the
  state that must mutate to a single owner behind a narrow interface.
---
## Intent
Keep the number of states a reader or caller must consider small, so that behavior can be predicted from the code in front of them rather than reconstructed from a history of assignments.
## Guidance
Treat mutability as a cost paid per variable rather than a free default. Construct values complete and leave them alone, and express change as a new value instead of an edit in place. Derive anything computable from something already stored instead of storing it a second time, because two facts that must agree eventually disagree. Where mutation is genuinely required — a cache, a counter, an accumulating buffer, a pool of connections — give it exactly one owner, keep it private behind that owner's operations, and make the window in which it is inconsistent no longer than a single call. Prefer local mutation inside a function, which nobody else can observe, over a field; prefer a field over module-level or process-level state, which every part of the system can reach. When a mutable structure must cross a boundary, hand out a snapshot rather than the structure itself.
## Signals
A function's result depends on how many times it has already been called. Objects expose setters that must be called in a particular sequence, so a half-initialized instance is a legal thing to be holding. The same fact is stored in two places alongside code whose job is to keep them in step. Tests reset module-level or class-level variables between cases, or fail when their order changes. A defect can only be reproduced by replaying the operations that preceded it.
## Diagnostic questions
How many distinct states can this object be in, and is every one of them valid? Could this stored field be computed on demand from the values it was derived from? Who else can observe this variable between the moment it is written and the moment it is consistent again?
## Likely consequences
Code built from immutable values reads locally: a value means the same thing whenever you look at it, so review, concurrency and debugging all get cheaper, and equality and caching become trivial. Sprawling mutable state produces defects that appear only under particular orderings, and each additional mutable field multiplies the combinations that must be reasoned about, tested and defended against.
## Exceptions
Hot paths sometimes require mutating a large structure in place; do it inside a boundary where no caller can observe the difference, and say so at that boundary. Long-lived operational state such as caches, pools and metrics counters is mutable by nature — the policy asks for one owner and a narrow interface, not for its removal.
## Positive example
An ingestion pipeline represents each record as an immutable value and each stage as a function returning a new one, so a failed batch is replayed from any stage's input without unwinding anything. The only mutable thing in the pipeline is the checkpoint offset, owned by the runner and written in one place; someone tracing a corrupted record follows the values, not the assignments.
## Counterexample
A report builder hands callers an object whose fields are set one at a time before render is called, and render itself mutates the object to cache intermediate totals. Two call sites set the fields in different orders, a third omits a setter that later became mandatory, and the cached totals go stale whenever a field is set after the first render — three defects that exist only because the object has a life story.
## Related policies
See `give-state-one-writer`, `keep-effects-at-the-edges`, and `eliminate-errors-by-design`.
