---
id: make-operations-idempotent
title: Make retried operations safe to repeat
scope: general
strength: guidance
tags: [idempotency, retries, distribution, state]
source:
  author: ArchCompass
  inspiration: ["Pat Helland, Idempotence Is Not a Medical Condition"]
description: >-
  When a caller cannot learn whether an operation succeeded, its only correct move is to
  ask again. Design the receiving operation so that repeating it cannot double its
  effect, and at-least-once delivery becomes survivable instead of dangerous.
---
## Intent
Make retry a safe answer to uncertainty, so a caller that never learns the outcome of a
request can simply repeat it.
## Guidance
Anywhere a result can be lost between committing the work and reporting it, assume the
request will arrive twice and design the receiver to absorb the repeat. The most general
mechanism is an identifier the client generates for each logically distinct request,
recorded by the receiver in the same transaction as the effect and returned unchanged
when the identifier reappears. Where an identifier is unnatural, use the domain's own key
and write by upsert, or express the change so that applying it twice equals applying it
once — set a value rather than increment it, record a fact rather than adjust a total.
When a step genuinely cannot be repeated, such as dispatching money or sending a message,
put a repeatable record in front of it so the deduplication happens before the
irreversible act. State in the interface which operations are safe to retry; a caller
cannot deduce it from a signature.
## Signals
A retry policy sits in front of an operation that increments counters, appends rows, or
emits messages. Requests carry no client-supplied identifier, so the receiver has no way
to distinguish a retry from a genuinely new request. A scheduled job exists to find and
merge duplicate records, which is evidence that the write path admits them. Reconciliation
code exists to undo doubly applied effects. An operation is described as idempotent in a
comment while its implementation appends a new row per call.
## Diagnostic questions
If the caller times out after the work committed but before the response arrived, what
does the caller do, and what does that do to the state? Which field would let the
receiver recognize this exact request the second time it arrives? Does applying this
change twice leave the same state as applying it once?
## Likely consequences
Idempotent operations make at-least-once delivery survivable, which matters because
at-least-once is what most transports and most retry layers actually provide. Retries
then become a routine mechanism rather than a risk requiring a discussion. Without it,
every ambiguous timeout becomes a manual judgment, duplicates accumulate quietly in the
data, and the eventual response is to remove retries — trading duplicated effects for
lost work, which is rarely the better trade.
## Exceptions
Operations whose repetition is the point are not duplicates: an event recording that a
user clicked again should be stored again, and deduplicating it destroys information.
Read-only operations need no key. Where duplicates are cheap and reliably detectable
further downstream, the deduplication may legitimately live at the consumer, provided one
component owns it and that ownership is written down.
## Positive example
A payment submission accepts a client-generated request identifier, stores it under a
unique constraint in the same transaction as the ledger entry, and on a repeated
identifier returns the stored outcome without touching the ledger. Clients retry timeouts
freely, and the ledger holds one entry no matter how many times the request arrived.
## Counterexample
An order intake endpoint appends a row per call and sits behind a gateway that retries on
timeout. A slow database causes the gateway to retry a request that had already
committed, warehouses receive two identical orders, and the fix becomes a nightly
duplicate-detection job — resolving in hours, imperfectly, what one recorded identifier
would have prevented outright.
## Related policies
See `design-for-partial-failure`, `eliminate-errors-by-design`, and
`give-state-one-writer`.
