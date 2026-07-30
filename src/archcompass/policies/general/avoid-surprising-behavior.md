---
id: avoid-surprising-behavior
title: Let interfaces do what their names and conventions promise
scope: general
strength: guidance
tags: [least-astonishment, interfaces, consistency, usability]
source:
  author: ArchCompass
  inspiration: ["principle of least astonishment"]
description: >-
  An interface is misused in proportion to how far its behavior departs from what
  its name, signature and the system's conventions suggest. Side effects behind
  reads, order-dependent setup and per-call-site defaults are defects even when
  documented.
---
## Intent
Keep the cost of using an interface close to the cost of reading its signature, so that correct use is the default and misuse takes effort.
## Guidance
Let a name, a signature and the surrounding conventions be an accurate summary of what an operation does. An operation named for reading should not write, one named for a resource should not touch another, and one that fails should fail the way the rest of the system fails. Follow local convention for argument order, units, time zones, absence and error signalling even where a different choice would be marginally better in isolation, because a reader's expectations are set by the other ninety per cent of the codebase, not by this call. Make defaults the safe choice rather than the convenient one, and avoid behavior that varies with call order, ambient configuration or global state the call site cannot see. Where a surprise is genuinely unavoidable, put it in the name rather than a comment; documentation does not travel to the call site, and a warning in a docstring is not a substitute for an operation that behaves as it reads.
## Signals
A property access opens a connection, writes a log record, or lazily mutates the object it belongs to. Two functions in the same module take the same pair of arguments in opposite orders. The same condition yields null in one implementation, an empty collection in another and an exception in a third. Setup calls must happen in an order that only a failing test reveals. Call sites are wrapped in defensive code whose only purpose is to undo something the callee did on its own initiative.
## Diagnostic questions
What would a competent reader assume this call does, and where does the implementation differ? Is anything happening here that is not visible in the name, the arguments and the return type? Does this operation spell the idea the same way the rest of the system spells it?
## Likely consequences
An interface that behaves as it reads is used correctly by people who never open its implementation, and review can concentrate on whether a call is right rather than on what the call does. Surprising interfaces are misused steadily and quietly: each defect is small, each fix is usually another wrapper, and the accumulated workarounds eventually become the reason the interface can never be corrected.
## Exceptions
A deliberate departure from convention is legitimate when the convention is genuinely wrong and the departure is applied consistently and visibly across the whole system rather than in one corner of it. Performance-motivated surprises such as a lazily loaded field or an internal cache are acceptable precisely when no caller can observe the difference except in timing.
## Positive example
A configuration store's read operation is pure and returns the already-resolved value, while reloading from disk is a separate, explicitly named operation invoked at startup and on a signal. Someone adding a configuration read inside a hot loop cannot accidentally introduce a file access, because reading has never had one.
## Counterexample
An account object's balance accessor refreshes from the ledger and takes a lock while doing so. A nightly report reads balances in a loop, serializes behind that lock and runs for forty minutes; the author of the loop had no reason to suspect that reading a field was a remote call.
## Related policies
See `apply-consistency-deliberately`, `keep-interfaces-simple`, `name-for-meaning`, and `separate-commands-from-queries`.
