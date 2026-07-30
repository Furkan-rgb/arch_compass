---
id: give-state-one-writer
title: Give every piece of shared state one writing owner
scope: general
strength: guidance
tags: [data-ownership, state, boundaries, distribution]
source:
  author: ArchCompass
  inspiration: ["single-writer principle", "Sam Newman, Building Microservices"]
description: >-
  State written by several components has no invariant anyone can enforce. Each datum
  gets one component that writes it, and everyone else reads through that component's
  interface or through a copy it publishes.
---
## Intent
Keep invariants enforceable by ensuring that exactly one component decides how a given
piece of state may change.
## Guidance
For each datum, name the single component permitted to write it; everything else reads
through that component's interface or through a derived copy it publishes. The writer
owns the invariants, the validation, the concurrency control, and the storage layout,
none of which it can own if another component can write behind its back. Readers may keep
their own storage as long as it is visibly derived and its staleness is a stated
property. When two components need to write the same data, treat that as evidence the
boundary is drawn wrong: either they are one component, or the datum should be split so
each owns its part, or one of them should be sending requests to the other rather than
writes to the store. Shared write access to one table is the most common form of hidden
coupling precisely because it looks like data access while behaving like an undocumented
interface with no owner.
## Signals
Two services connect to the same schema and both issue writes. A batch job updates rows
an application also updates, coordinated only by running at night. The same invariant is
enforced in more than one codebase, or has been pushed into a database trigger because
application code could not be trusted to hold it. No one can say who is allowed to set a
particular column. A schema change requires synchronized deployment of components that
otherwise have nothing to do with each other.
## Diagnostic questions
Which single component would you change to alter how this field is computed or validated?
If two writers disagree about the value, which one is right, and what in the system
decides? What breaks if a reader's copy is five minutes stale, and does anything quietly
depend on it not being?
## Likely consequences
One writer means invariants live in one place, concurrency is handled once, and the
storage layout can change without a cross-team negotiation. Many writers mean the
invariant is whatever the most recent writer believed, corruption appears at the seams
between them, and every schema change becomes a coordination event. The cost of undoing
shared write access grows with time, because each new writer adds assumptions that were
never recorded anywhere.
## Exceptions
A store that enforces the invariant itself can accept many producers: an append-only
stream with no updates and no cross-record consistency claim is safe to write from
several places. Deliberate multi-writer replication is also legitimate when the merge
rule is chosen and documented — last write wins on a defined clock, or a data type whose
merges converge — as opposed to assumed.
## Positive example
A scheduling component owns the shift records and exposes assign, release, and query. A
reporting component keeps a read-optimized copy fed from the scheduler's published change
stream and labeled with its lag. When overlapping shifts must be forbidden, the rule goes
in one place and there is no path that evades it.
## Counterexample
A billing service and an administrative console both write the subscription table
directly, because adding an endpoint looked slower than adding a query. Only billing
knows that a plan change must also write a proration record, so console-initiated changes
skip it silently, and the gap surfaces a quarter later as a revenue discrepancy nobody
can attribute.
## Related policies
See `assign-clear-ownership`, `explicit-source-of-truth`, `avoid-duplicated-knowledge`,
and `minimize-mutable-state`.
