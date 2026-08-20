---
id: design-for-replaceability
title: Design components to be replaceable, not eternal
scope: general
strength: guidance
tags: [replaceability, boundaries, change]
source:
  author: ArchCompass
  inspiration: ["Neal Ford, Rebecca Parsons & Patrick Kua, Building Evolutionary Architectures"]
description: >-
  Judge a component by what it costs to remove rather than by how long it is
  expected to last. Narrow interfaces, owned data, and internals that never leak
  let a component be rewritten or deleted without an archaeology project.
---
## Intent
Keep the cost of removing a component proportional to its size, so that a design choice
which turns out to be wrong stays recoverable.
## Guidance
Ask what it would take to delete this component, not whether it will still be right in
three years. A replaceable component has one narrow interface, owns its data outright, and
leaks none of its internal vocabulary — its types, its identifiers, its error taxonomy —
into the code around it. Place the seams so that the parts most likely to be wrong, such as
a scoring heuristic, a storage layout, or an external integration, are also the parts
easiest to lift out, and accept a little translation at a boundary when that is what keeps
the boundary clean. When nobody can name what would have to change in order to remove a
component, that silence is the estimate: everything. Treat replacement cost as a design
output you choose, the same way you choose an interface.
## Signals
Callers import types defined inside the component and pass them around as their own
currency. The component's data lives in tables or files that three other components also
write to, so removing it means negotiating with all of them. Its identifiers appear in log
formats, addresses, and stored records that outside parties already depend on. Removing it
would require touching fixtures across unrelated modules, because those tests were written
against its concrete behavior rather than its contract. An interface has exactly one
implementation and nothing depends on the abstraction rather than the concrete type: the
seam exists on paper, has never been asked to hold, and has taken its shape from the only
implementation behind it — so the second one arrives to find the contract already describes
the first.
## Diagnostic questions
If this component were deleted tomorrow, what else stops working? How much of the
surrounding code would have to learn something new to work with a different
implementation? Is the part of this design most likely to be wrong also the part hardest to
extract?
## Likely consequences
Replaceable components make experimentation cheap: a wrong choice costs an afternoon rather
than a quarter of migration. Components that cannot be removed accumulate around themselves
— new features attach to them because that is where the data already lives — until the cost
of replacement exceeds anyone's willingness to pay it, and the design is settled by inertia
instead of judgment.
## Exceptions
A component that encodes a genuinely stable domain concept such as money, identity, or time
earns durability, and designing for its removal spends effort on an event that will not
happen. Foundational infrastructure that everything legitimately depends on will never be
cheap to replace; there the correct response is to keep its interface small, not to pretend
it is disposable.
## Positive example
A ranking component sits behind a single call that takes a request and returns an ordered
list of item identifiers, and keeps its derived features in storage nobody else writes.
Swapping it for a different ranking approach means implementing one function and changing
one wiring line, because no caller ever learned what a feature vector was.
## Counterexample
A pricing engine exposes its internal rule objects, and over two years callers begin
constructing rules directly, reading its intermediate tables for reporting, and relying on
the exact order in which its discounts apply. Replacing it now means reproducing that
ordering as an observable contract, so the second implementation inherits the first one's
accidents.
## Related policies
See `contain-dependencies`, `hide-implementation-details`, and `preserve-reversibility`.
