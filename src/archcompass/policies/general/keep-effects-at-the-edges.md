---
id: keep-effects-at-the-edges
title: Keep a deterministic core and push effects to the boundary
scope: general
strength: guidance
tags: [purity, side-effects, testability, boundaries]
source:
  author: ArchCompass
  inspiration: ["Gary Bernhardt, Functional Core, Imperative Shell", "hexagonal architecture"]
description: >-
  Decisions belong in deterministic code that computes what should happen, while
  a thin outer layer performs the input and output. The core becomes testable
  without doubles, and the effects become auditable because they are enumerated
  at one boundary.
---
## Intent
Concentrate decision-making in code that computes results from values, and confine input,
output, randomness, and time to a thin outer layer.
## Guidance
Split every operation into deciding and doing. The deciding part receives the data it needs
as arguments and returns a description of what should happen — records to write, messages
to send, the next state — without reading a clock, opening a connection, or mutating
anything outside itself. The doing part, at the boundary, gathers the inputs, calls the
core, and performs the effects the core described. Push effects outward instead of
scattering them through the call graph: when a function three levels down needs the current
time or a remote lookup, pass the value in rather than letting it reach out. The measure of
success is whether the core can be exercised with plain values and checked against plain
values.
## Signals
A function that computes a total also writes an audit record and sends a notification.
Business rules read configuration or the system clock directly from the middle of a call
chain. Tests for logic need a data store, a network stub, or a frozen clock even though the
logic itself is arithmetic and branching. Retrying an operation is unsafe because its
effects are interleaved with the computation that decides whether they are warranted.
## Diagnostic questions
Can this logic be called with values and asserted against values, with no doubles at all?
Which functions in this call path perform effects, and could they be moved outward without
changing the decision? If the operation failed halfway through, how many effects have
already escaped?
## Likely consequences
A deterministic core is exhaustively testable, safe to re-run, and cheap to reason about,
and the effects become auditable because they are enumerated in one place. Systems that
interleave effects with decisions need a running environment to answer any question about
behavior, and partial failure leaves them in states nobody designed, because the effects
happened in whatever order the code happened to take.
## Exceptions
Streaming and incremental processing sometimes cannot buffer a whole decision before
acting; there the boundary moves inward to a small, explicitly effectful component rather
than disappearing. Code whose entire purpose is an effect, such as a writer, a client, or a
scheduler, is the edge, and inserting a pure layer inside it only lengthens the path.
## Positive example
A scheduling routine takes the current roster, the pending requests, and a timestamp as
arguments and returns a list of assignments and a list of rejections. The surrounding job
loads the inputs, calls it, and writes the results in one transaction; the rules are tested
with tables of inputs and expected outputs and have never needed a fake data store.
## Counterexample
An order validator checks each line and, on the first invalid one, logs, increments a
counter, sends the customer an email, and returns false. Testing the rules requires
intercepting three collaborators, and when a later check fails the customer has already
been told the order was rejected for the wrong reason.
## Related policies
See `minimize-mutable-state`, `treat-testability-as-design-feedback`,
`contain-dependencies`, and `separate-model-context-from-provider-transport`.
