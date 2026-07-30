---
id: migrate-incrementally
title: Change running systems through incremental, coexisting steps
scope: general
strength: guidance
tags: [migration, incremental-change, strangler-fig]
source:
  author: ArchCompass
  inspiration: ["Martin Fowler, StranglerFigApplication", "expand/contract pattern"]
description: >-
  Change live systems in steps that each leave them working: route through a
  seam, run the old and new paths side by side, and move consumers one at a
  time. A cutover that cannot be paused cannot be rolled back.
---
## Intent
Keep change in a live system recoverable by letting old and new paths coexist, so risk
arrives in small pieces instead of all at once.
## Guidance
Replace a running system in steps that each leave it working. Introduce a seam in front of
whatever is changing, build the new path behind it, and move traffic or data across one
slice at a time — one consumer, one endpoint, one tenant — verifying each slice before
starting the next. For schema and contract change, expand first: add the new shape while
the old one still works, write both, migrate readers, and contract only once nothing reads
the old shape. Every intermediate state must be one you are willing to operate for weeks,
because you probably will. Plan the reversal of each step alongside the step itself; a
migration whose progress cannot be paused has no rollback, only a recovery.
## Signals
The plan contains one deployment where the old system stops and the new one starts.
Migration scripts must run to completion inside a maintenance window, and no behavior is
described for a partial run. A schema change drops or renames a field in the same release
that begins using it. Rollback is documented as restoring from backup, which usually means
the rollback has never been rehearsed.
## Diagnostic questions
Can the system run correctly with this change half applied? What is the smallest slice we
can move and observe before moving the rest? If we stopped here indefinitely, is the
resulting state one we can operate and explain?
## Likely consequences
Incremental migration turns one large risk into a series of small ones, each observable,
pausable, and reversible, and it surfaces surprises while the blast radius is a single
consumer wide. Big-bang cutovers concentrate every unknown into a window under time
pressure, where discovering a problem and deciding to abandon must happen in the same hour.
## Exceptions
A system with no live data and no external consumers can be replaced outright; coexistence
machinery has real cost and buys nothing where there is nothing to preserve. A change
forced by a security or correctness emergency may justify a single step, with the
coexisting path skipped deliberately and the exposure named rather than ignored.
## Positive example
A team splitting an order service routes all traffic through a thin facade, moves read
endpoints to the new implementation while writes still go to the old store, then dual-writes
for two weeks with a comparison job reporting divergence. Reads and writes cut over
separately, and the old store is retired a month after the last read of it.
## Counterexample
An identity system is replaced over a weekend: the schema is transformed in place, every
service is redeployed against the new tables, and the old rows are deleted to reclaim
space. A field-mapping error surfaces on Monday in accounts that staging never exercised,
and because the source shape no longer exists, the correction has to be reconstructed from
downstream reports.
## Related policies
See `plan-for-data-longevity`, `program-strategically`, and `preserve-reversibility`.
