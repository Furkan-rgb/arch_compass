---
id: eliminate-errors-by-design
title: Eliminate error cases through the design when practical
scope: general
strength: guidance
tags: [errors, validation, invariants]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Prefer designs in which invalid states or operations cannot arise.
## Guidance
Validate at boundaries, use explicit types, and make state transitions atomic.
## Signals
Callers repeatedly check the same precondition or recover from preventable partial state.
## Diagnostic questions
Can ownership, types, or transaction boundaries remove this failure mode?
## Likely consequences
Less defensive code is distributed across callers.
## Exceptions
External failures such as unavailable models must remain explicit and recoverable.
## Positive example
An append operation checks the expected case revision in the same transaction.
## Counterexample
Exceptions are swallowed and described as eliminated.
## Related policies
See `keep-interfaces-simple` and `explicit-source-of-truth`.
