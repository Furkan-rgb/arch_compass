---
id: make-relationships-discoverable
title: Make important relationships explicit and discoverable
scope: general
strength: guidance
tags: [discoverability, dependencies, configuration]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  Dependencies, ownership, and wiring should be visible in types, composition, or
  queryable metadata rather than carried by convention, import side effects, or
  naming coincidence. A relationship a maintainer cannot find is a relationship
  they will break.
---
## Intent
Help maintainers find dependencies, ownership, and configuration without relying on hidden
convention, so that the structure a reader infers matches the structure that runs.
## Guidance
Represent important relationships in something a reader or a tool can follow: a type, an
explicit composition step, a declared registration, or metadata that can be queried.
Prefer passing a collaborator to discovering one, and prefer one visible composition root
over registration that happens as a side effect of importing a module. Where convention
does the work — a naming pattern, a directory layout, a plugin discovery rule — state the
convention in one place and make violations detectable rather than silent. The test is
mechanical: someone changing this component should be able to find everything that depends
on it by searching, not by running the system and watching what breaks. Relationships that
only exist at runtime deserve the most explicitness, because static reading cannot recover
them.
## Signals
Behaviour depends on import side effects, so removing an unused-looking import changes what
the system does. Components are located by naming coincidence or by string lookup in a
registry, so no reference exists to follow. Registration happens in a module that nothing
appears to call. Deleting a file produces a runtime failure in an unrelated feature.
Answering "who uses this" requires instrumenting the running system because search returns
nothing.
## Diagnostic questions
How would a new maintainer locate and verify this relationship, and how long would it take?
If this component were deleted, would anything fail before production? Is this wiring
visible in code that someone reads, or only in behaviour that someone observes?
## Likely consequences
Unknown unknowns decrease: the questions a maintainer does not know to ask get answered by
the structure itself, and structural evidence — search results, type references, a wiring
file — becomes reliable enough to act on. Refactoring gets cheaper because impact can be
assessed before the change. Where relationships are hidden, every change carries residual
risk that some convention was violated invisibly, and teams compensate with caution rather
than confidence.
## Exceptions
Well-established language and framework conventions need not be restated everywhere; a
reader who knows the ecosystem already has them. Genuinely dynamic extension points —
plugins loaded from configuration, handlers resolved by message type — are legitimate, but
the mechanism and the set of registered participants should be inspectable at runtime and
described in one place.
## Positive example
Provider implementations are constructed and registered in a single composition root, and
the registry is a plain mapping a reader can open. Adding a provider means editing that one
file, and searching for the registry type shows every place a provider is chosen.
## Counterexample
Importing an unrelated module silently mutates a global registry, so the set of available
providers depends on which modules happen to have been imported. A cleanup that removes an
apparently unused import drops a provider, the failure appears only when a request selects
it, and nothing in the diff suggested a relationship existed.
## Related policies
See `explicit-source-of-truth`, `apply-consistency-deliberately`, `design-in-observability`,
and `assign-clear-ownership`.
