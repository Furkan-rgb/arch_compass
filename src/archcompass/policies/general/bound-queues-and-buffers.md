---
id: bound-queues-and-buffers
title: Bound every queue and answer overload with backpressure
scope: general
strength: guidance
tags: [backpressure, queues, overload, resilience]
source:
  author: ArchCompass
  inspiration: ["Michael Nygard, Release It!", "queueing theory"]
description: >-
  An unbounded buffer converts overload into rising latency, memory exhaustion, and a
  later, larger failure. Every queue needs a limit and a decided policy at that limit,
  and the resulting backpressure has to reach the producer.
---
## Intent
Stop overload from turning into unbounded latency and memory growth, and let upstream
learn that the system is saturated while it can still do something about it.
## Guidance
Every place where work waits gets an explicit bound and an explicit policy at that bound:
a request queue, a channel, an in-memory list of pending items, the wait line in front of
a connection pool, the backlog of an elastic worker pool. The policy is a real choice —
reject the arrival, drop the oldest, shed by priority, or block the producer — and it
belongs in the design rather than in whatever the library defaults to. Derive the bound
from the deadline of the work rather than from available memory, because an item that
will be served after its caller has given up should never have been accepted. Propagate
the resulting signal upstream so the producer can slow down, defer, or refuse at its own
edge; backpressure is information, and swallowing it misinforms everyone above. Where
items can expire, discard them on dequeue rather than spending capacity on work nobody is
waiting for.
## Signals
A queue, channel, or executor is constructed with no capacity argument. Latency climbs
steadily under load while the error rate stays at zero, which is what a queue absorbing
excess arrival rate looks like. Memory grows with traffic and is reclaimed only by a
restart. A worker pool is described as elastic with no stated ceiling. Producers have no
way of being told to stop, so the only feedback they ever receive is the consumer dying.
After an incident the backlog is drained and most of the work turns out to be irrelevant.
## Diagnostic questions
What is the largest number of items that can be waiting here, and what happens to the
next arrival? How long can an item sit here before the caller that is waiting for it has
already timed out? What does the producer do when this component says no, and is it able
to say no at all?
## Likely consequences
A bounded queue converts overload into a fast, visible rejection at a known point, so the
system degrades predictably and recovers as soon as arrivals fall below service rate. An
unbounded one hides the same overload as growing latency and pays for it later with
memory exhaustion, a restart, and a backlog of work that has gone stale. Bounds also give
upstream a decision it could not otherwise make — shed low-priority traffic, spill to
durable storage, tell a user to come back — none of which is possible while the queue is
still quietly accepting.
## Exceptions
A durable log used deliberately as a buffer for hours of work is legitimately large, but
its capacity is still finite and its behavior at the limit still has to be chosen. Where
loss is unacceptable and the producer cannot be slowed, as with an inbound feed you do
not control, the bound moves to durable storage with a stated retention policy — that is
a different bound, not an exemption from having one.
## Positive example
An ingestion service accepts uploads into a queue capped at a thousand items with a
thirty-second age limit. When it fills, new uploads are refused with a retry-after
response, clients back off, memory stays flat, and throughput holds at the service rate.
Operators see the rejection rate rise the moment capacity is exceeded, hours before the
same condition would otherwise have appeared as a crash.
## Counterexample
A metrics collector buffers points in an unbounded in-memory list whenever its storage
backend is slow. A twenty-minute backend degradation fills tens of gigabytes, the
collector is killed for memory use, and everything buffered is lost — including precisely
the metrics that would have explained the degradation.
## Related policies
See `design-for-partial-failure`, `eliminate-errors-by-design`, and
`expose-remote-boundaries`.
