---
id: separate-commands-from-queries
title: Separate operations that change state from operations that answer questions
scope: general
strength: guidance
tags: [command-query-separation, interfaces, state]
source:
  author: ArchCompass
  inspiration: ["Bertrand Meyer, Object-Oriented Software Construction"]
description: >-
  An operation that both mutates and reports forces callers to cause a change in
  order to observe one, and makes calls unsafe to repeat, reorder or remove.
  Queries return answers and change nothing; commands change state and return at
  most an acknowledgment.
---
## Intent
Keep observing a system free of consequence, so that reading state is always safe and changing it is always deliberate.
## Guidance
Give every operation one of two jobs. A query computes an answer and leaves the observable state exactly as it found it, so it may be called twice, called from a diagnostic, or deleted without altering behavior. A command changes state and returns at most an acknowledgment — a status, an identifier for what it created, or nothing — and is never the only way to learn something. When an operation seems to need both, split it: a query that reports what currently holds or what would happen, and a command that performs the change. Where the read and the write are genuinely atomic, name the operation for its effect — claim, reserve, take, pop — so that no reader mistakes it for a question. Internal mutation that no caller can observe, such as a memoized result or a lazily opened resource, does not make a query into a command.
## Signals
A method named get, find, is or has writes a row, advances a cursor, or publishes an event. Calling a reporting operation twice returns different answers with no command in between. Adding a debug log changes behavior, or removing one breaks a test. A command returns a rich object that callers depend on for state they cannot obtain any other way, so they issue writes in order to perform reads. Test setup performs mutations purely to observe the outcome of an earlier step.
## Diagnostic questions
If this call were made twice in a row, or not at all, what would differ? Can a caller learn this fact without changing anything? Does the name of this operation tell a reader which of the two kinds it is?
## Likely consequences
Separating the two makes reads safe to cache, retry, parallelize and reorder, and reduces writes to a small, auditable set of places where the system actually changes. Blending them turns every observation into a potential mutation: retries become dangerous, monitoring becomes a load-bearing side effect, and understanding a sequence of calls requires reading each implementation rather than each signature.
## Exceptions
Some primitives are inherently both — dequeue, compare-and-set, allocate-next-identifier — and splitting them introduces a race worse than the coupling. Keep those few, name them for their effect, and treat them as commands that happen to return a value. Recording an access for auditing or rate accounting is a legitimate side effect of a read when it is invisible to the result and not relied upon by callers.
## Positive example
A job store exposes pending_count and next_ready as queries and claim as a command returning a lease identifier. A dashboard polls the queries as often as it likes without touching the queue, and an audit of everything that can modify job state has exactly one operation to read.
## Counterexample
A rate limiter offers is_allowed, which also decrements the caller's remaining budget. A retry wrapper consults it before each attempt and an admission log prints it for diagnostics, so the effective limit lands at a third of the configured one — a defect invisible in any single call site.
## Related policies
See `make-operations-idempotent`, `keep-interfaces-simple`, and `minimize-mutable-state`.
