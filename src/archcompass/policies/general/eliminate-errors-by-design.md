---
id: eliminate-errors-by-design
title: Eliminate error cases through the design when practical
scope: general
strength: guidance
tags: [errors, validation, invariants]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Prefer designs in which invalid states and operations cannot arise at all over
  designs that detect and report them everywhere. Each error case removed by
  construction is a branch, a test, and a defect that no caller ever has to
  handle.
---
## Intent
Prefer designs in which invalid states or operations cannot arise, so that correctness
comes from the shape of the design rather than from vigilance at every call site.
## Guidance
Before adding a check, ask whether the condition being checked could be made impossible.
Validate at the boundary where untrusted input enters and convert it into a representation
that carries its own guarantees inward, so interior code has nothing to re-check. Define
operations so that the awkward case is simply not special: a delete that tolerates a
missing item, a create that is defined for an empty collection, a transition that is
atomic and therefore has no half-applied state. Use explicit types instead of sentinel
values and flags, and give each invariant one place that enforces it. When an error case
cannot be removed, keep it — but keep it at one boundary with a designed response, rather
than distributing partial recovery across callers.
## Signals
Callers repeatedly check the same precondition before calling, which means the callee's
contract is not carrying its weight. The same null, empty, or not-found condition is
handled differently in different places, so the behaviour of the system depends on which
path reached it. Recovery code exists for partial state that a transaction boundary could
have prevented. A function returns a value that must be interpreted before it can be used,
and some call sites forget. Test suites are thick with cases that only exercise defensive
branches no legitimate caller can trigger.
## Diagnostic questions
Can ownership, types, or transaction boundaries remove this failure mode rather than
report it? If this check were deleted, what could construct the bad value, and can that
construction be closed off instead? Is this condition genuinely exceptional, or is it a
normal case the interface has declined to define?
## Likely consequences
Less defensive code is distributed across callers, and the code that remains is about the
domain rather than about self-protection. Every error case removed by construction is a
branch that cannot be reached wrongly, a test that need not exist, and a piece of
knowledge no future caller must acquire. Systems that instead detect everywhere accumulate
inconsistent handling of the same condition, and their behaviour under bad input becomes
an emergent property nobody chose.
## Exceptions
External failures — an unreachable dependency, a timeout, a rejected credential — cannot
be designed away and must remain explicit, surfaced, and recoverable. Trust boundaries
genuinely require checking, because the value arriving is not yet under the design's
control. The policy targets self-inflicted error cases, not the real uncertainty of the
world outside the process.
## Positive example
An append-only case log accepts a new entry together with the revision the writer believed
was current, and rejects the write in the same transaction if the revision has moved. Lost
updates are not detected after the fact and repaired; they cannot be committed, so no
caller carries reconciliation logic.
## Counterexample
A configuration object is constructed empty and then populated by several setters, so
every consumer must check which fields were filled and what to do when they were not.
Exceptions raised by half-configured use are caught at the top level and logged as
handled, which is described as eliminating the error while leaving every invalid
combination constructible.
## Related policies
See `make-illegal-states-unrepresentable`, `validate-at-trust-boundaries`,
`keep-interfaces-simple`, and `explicit-source-of-truth`.
