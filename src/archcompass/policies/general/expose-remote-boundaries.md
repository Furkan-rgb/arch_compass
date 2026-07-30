---
id: expose-remote-boundaries
title: Do not disguise remote calls as local calls
scope: general
strength: guidance
tags: [distribution, boundaries, failure-modes, interfaces]
source:
  author: ArchCompass
  inspiration: ["Jim Waldo et al., A Note on Distributed Computing (1994)", "Peter Deutsch, fallacies of distributed computing"]
description: >-
  An interface that crosses a network must look like it does. Latency, partial failure
  and unavailability belong in its contract rather than beneath a local-method veneer,
  because a caller that cannot see the boundary has no place to handle what happens at
  it.
---
## Intent
Keep the cost and the failure modes of leaving the process visible to the code that
pays for them, so the decisions they force are made where their meaning is known.
## Guidance
Design an interface that crosses a network around the three facts that distinguish it
from a local call: it can be slow, it can fail after the work was done, and it can be
unavailable for a while. Give the operation a deadline supplied or bounded by the
caller, a result type that admits unavailability, and a granularity that carries a
whole unit of work in one round trip rather than inviting a loop. A local abstraction
over a remote dependency is still right — the dependency belongs behind a port — but
the port's signature must admit what the network can do to it. Never let a round trip
hide behind a property read, a lazy attribute, or an iterator that fetches per element;
uniform syntax across the boundary is acceptable, a uniform contract is a lie. When a
remote failure is translated into the same error type as a local one, callers lose the
only distinction that would have told them to retry.
## Signals
A getter, attribute access, or comparison triggers a network round trip. A loop calls a
repository or client per element, so the number of calls is a function of the data. Call
sites pass no deadline and the client library's default timeout is unset or unknown. The
interface returns the same exception for a validation failure and for a connection
refused. Tests double the dependency with an in-memory object that answers instantly and
never fails, so no test exercises the boundary at all.
## Diagnostic questions
Can a reader tell from the call site that this crosses a process boundary? What does this
caller do when the call takes ten seconds, or returns an error after the remote work had
already committed? Which layer owns the deadline and the retry budget for this call, and
does it know the business consequence of giving up?
## Likely consequences
A visible boundary puts timeouts, retries, and fallbacks in the layer that understands
what the failure means to the user, and keeps call patterns coarse because the cost is on
screen. A hidden one produces chatty access patterns that pass every small-data test,
failure handling that lands wherever an exception happens to be caught, and stalls that
propagate because nobody chose a deadline.
## Exceptions
An in-memory implementation of a port legitimately has none of these characteristics; the
port's contract is still written for the remote case, and the in-memory version simply
never exercises it. A generated client that mirrors a remote API operation for operation
is fine when its signatures carry deadlines and failure — the objection is to
transparency, not to code generation.
## Positive example
A pricing dependency is reached through a port with one operation that takes a batch of
line items and a deadline, and returns either priced lines or an explicit unavailable
outcome. When pricing is down, the checkout flow chooses between holding the order and
quoting from a cached table, because the choice reached code that knows what each option
costs the customer.
## Counterexample
A data-access layer exposes remote rows as ordinary object attributes, so rendering one
page walks a collection and issues a query per element. Nothing in the source marks a
boundary, there is no signature that could carry a deadline, and the page that returns in
milliseconds against three test rows times out in production against three hundred.
## Related policies
See `design-for-partial-failure`, `contain-dependencies`, and `keep-interfaces-simple`.
