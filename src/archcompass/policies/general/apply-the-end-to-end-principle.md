---
id: apply-the-end-to-end-principle
title: Place correctness where it can actually be guaranteed
scope: general
strength: guidance
tags: [end-to-end, layering, reliability, responsibility]
source:
  author: ArchCompass
  inspiration: ["Saltzer, Reed & Clark, End-to-End Arguments in System Design"]
description: >-
  A guarantee belongs to the component that can verify it held. Intermediate layers may
  implement partial versions to improve performance, but a middle-layer promise of
  delivery, integrity, or exactly-once effect is an optimization, never the authority.
---
## Intent
Anchor each correctness guarantee at the only place with enough knowledge to verify it,
and stop intermediate layers from promising what they cannot observe.
## Guidance
For every guarantee the system needs — delivery, ordering, integrity, exactly-once
effect, deduplication — ask which component can check that it actually held. That
component owns the guarantee and its check is authoritative. Intermediate layers may
implement partial versions of the same guarantee, but only as an optimization: a
transport retry reduces how often the endpoint's check has to do real work, it does not
remove the need for the check. Be most careful with guarantees whose failure is invisible
from the middle, since a queue can honestly report that it delivered a message and still
be wrong about whether the receiver did anything with it. The failure mode to watch for is
social rather than technical: once a middle-layer mechanism is believed sufficient, the
end check is deleted as redundant, and the system now depends on a promise no component
is able to keep.
## Signals
A design claims exactly-once and the mechanism cited is a broker or framework setting.
Integrity is checked when data is written but never when it is read back and acted on. A
component reports success as soon as it has handed work to an intermediary. Consumers
skip deduplication on the grounds that the transport does not duplicate. Recovery
procedures assume anything acknowledged by a middle layer definitely completed.
## Diagnostic questions
Which component can observe whether this guarantee actually held, end to end? If the
intermediate mechanism failed silently, would anything notice, and after how long? Is this
middle-layer mechanism reducing the frequency of a problem, or being trusted to eliminate
it?
## Likely consequences
Guarantees anchored at the endpoints survive changes in the middle — a new transport, an
inserted cache, a rerouted path — because the authoritative check never moved. Guarantees
delegated to the middle break the first time an assumption underneath them changes, and
they break quietly, surfacing as wrong data rather than as an error. Relieving
intermediate layers of correctness duties also frees them to be optimized aggressively,
since their job becomes speed rather than truth.
## Exceptions
When an endpoint genuinely cannot check — a constrained device with no storage, a
consumer that cannot re-derive the answer it was given — the guarantee has to live lower,
and then its limits belong in the contract rather than in an assumption. Hop-by-hop
mechanisms also earn their cost when they make end-to-end recovery dramatically cheaper:
retransmitting one damaged chunk beats restarting a large transfer, even though the final
verification still happens at the end.
## Positive example
A file transfer computes a checksum at the sender, and the receiver recomputes it over the
bytes it actually stored before declaring the transfer complete. Compression, chunking,
intermediate caching, and link-level retries can all change along the path, and none of
them is able to turn a corrupted transfer into a reported success.
## Counterexample
An order pipeline relies on the message broker's delivery guarantee and therefore performs
no duplicate check in the consumer. A broker upgrade changes acknowledgment behavior under
network partition, duplicated orders flow through unnoticed, and the only component that
could have recognized the repeat is the one that had been told it did not need to look.
## Related policies
See `different-layer-different-abstraction`, `design-for-partial-failure`, and
`separate-general-from-special-purpose`.
