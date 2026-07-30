---
id: design-for-partial-failure
title: Design every remote interaction for partial failure
scope: general
strength: guidance
tags: [distribution, failure-modes, resilience, timeouts]
source:
  author: ArchCompass
  inspiration: ["Michael Nygard, Release It!"]
description: >-
  Every call that leaves the process needs a decided answer for timeout, retry, and
  degraded operation. A dependency going down should move the system into a state it
  was designed to occupy, not into an unhandled path discovered during the outage.
---
## Intent
Make a dependency's failure a state the system was designed to occupy, rather than an
accident it encounters for the first time in production.
## Guidance
For each call that leaves the process, decide four things before it ships: how long the
caller waits, what it does when that time expires, whether the call may be retried and
against what budget, and how the system behaves while the dependency stays down. Set a
timeout on everything, because an unset timeout is an infinite one, and keep it shorter
than the deadline of the work above it so a caller never waits past its own usefulness.
Bound retries with a total budget and jittered backoff, so a struggling dependency is not
finished off by the callers trying to reach it. Isolate resources per dependency —
separate connection pools, worker allocations, or concurrency limits — so one slow
dependency cannot consume the capacity that every other dependency needs. Then give the
caller a named degraded path: a cached answer, a reduced answer, deferred work, or a
refusal that upstream can act on.
## Signals
Calls with no timeout argument and no deadline inherited from the caller. Retry loops
with a fixed count, no backoff, and no shared budget, so one user request can multiply
into a dozen calls. One shared client, thread pool, or connection pool serving every
dependency. Failure handling that exists only in a catch-all at the top of the request.
No test exercises the dependency being slow — only the dependency being absent — because
slowness is inconvenient to simulate.
## Diagnostic questions
What happens to this request if the dependency answers in thirty seconds instead of
thirty milliseconds? If this dependency is unavailable for an hour, what does the system
do, and is that behavior in the design rather than only in a runbook? Which resources
does this call hold while it waits, and who else is waiting for them?
## Likely consequences
Designed failure keeps an outage local: the dependency degrades, the caller returns a
known reduced answer, and capacity remains for everything unrelated. Undesigned failure
spreads, because waiting requests hold threads and connections, work queues behind them,
and one dependency's slowness becomes the caller's outage and then its caller's.
Recovery is faster too, since a system with explicit degraded states resumes when the
dependency returns instead of needing to be restarted out of a stuck state.
## Exceptions
Some calls have no honest degraded answer: an authorization check, or a read of the
system of record for the very entity being edited. There the design work is a fast,
accurate refusal rather than a fabricated fallback, and a fallback would be worse than
the failure. Batch work with a generous deadline and no waiting user may legitimately
prefer long, patient retries to shedding.
## Positive example
A checkout path calls an inventory dependency with a two-hundred-millisecond deadline, at
most two retries drawn from a per-request budget, and its own connection pool. When
inventory stalls, only the inventory pool saturates, the path records the order with a
pending reservation for later reconciliation, and payment and catalog traffic proceed
untouched.
## Counterexample
An order service calls a tax calculator through a shared client left at default settings,
with no timeout and no isolation. The calculator degrades to eight-second responses under
load, every worker in the order service ends up blocked on it, the health check stops
answering, and the orchestrator restarts a service whose only real problem was one
dependency it had never decided how to wait for.
## Related policies
See `expose-remote-boundaries`, `make-operations-idempotent`, `aggregate-error-handling`,
and `bound-queues-and-buffers`.
