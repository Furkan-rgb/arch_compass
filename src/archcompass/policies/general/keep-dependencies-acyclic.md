---
id: keep-dependencies-acyclic
title: Keep module dependencies acyclic
scope: general
strength: guidance
tags: [dependencies, cycles, layering]
source:
  author: ArchCompass
  inspiration:
    - "John Lakos, Large-Scale C++ Software Design"
    - "Robert C. Martin, acyclic dependencies principle"
description: >-
  Dependencies between modules must form a directed acyclic graph, so the system
  can be built, tested, understood, and replaced in some order. A cycle fuses its
  members into a single unit that can only be changed, reasoned about, and
  released as a whole.
---
## Intent
Ensure modules can be understood, tested, and replaced in some order, rather than only as
one indivisible mass.
## Guidance
Treat a cycle between separately owned modules as a design defect to be removed, not a
build error to be worked around. There are three honest fixes. Extract the concept both
modules actually share into a third module that neither owns and both depend on. Invert
one edge by defining an interface on the side that is more abstract or higher-level, and
letting the other side implement it. Or merge the two modules if they always change
together, because then they were one module wearing two names. Choose the direction by
asking which module could exist without the other and pointing the remaining edge that
way. Deferring imports into function bodies, injecting attributes at runtime, or splitting
a file to satisfy the loader hides the cycle without dissolving it, and leaves the
coupling for the next reader to rediscover.
## Signals
Imports are deferred into function bodies or guarded by type-checking-only blocks to dodge
circular-import errors. Tests for one module cannot run without loading the other, so
there is no unit small enough to test alone. A change in either module reliably breaks the
other, and the two are always released together. The dependency graph has a strongly
connected component that no one can describe in a sentence. New engineers cannot answer
"what does this module depend on" without reading its whole call graph.
## Diagnostic questions
If these modules must always change and ship together, are they actually one module? Which
direction of the cycle represents the real dependency, and what would it take to make the
other direction go through an interface? Can either module be built and tested with the
other absent, and if not, what is the smallest testable unit here?
## Likely consequences
An acyclic graph gives an incremental path for builds, tests, comprehension, and eventual
replacement: any module can be understood knowing only what lies beneath it. Cycles remove
that order, so comprehension requires the whole component, test setup grows to match, and
replacing any member means replacing all of them. Cycles also spread: once one exists, the
next edge that closes another loop costs nothing to add and is invisible in review.
## Exceptions
Mutually recursive definitions inside one module boundary are ordinary — a parser and its
node types, a pair of state-machine functions — and the policy governs edges between
separately owned modules, not statements inside one. A framework may require registration
callbacks that appear to point backwards; the test is whether the two sides can be
released and reasoned about independently.
## Positive example
The domain package defines a repository interface expressed entirely in domain types, and
the persistence package implements it. Domain code never imports persistence, so the
domain can be tested with an in-memory implementation, and swapping the storage engine
touches one package whose only inbound edge is at composition time.
## Counterexample
The orders module imports billing to compute prices while billing imports orders to read
line items, and both hide it with function-local imports. Neither can be tested or
released alone, a change to line-item structure ripples into pricing and back, and the
team eventually treats the pair as one deployable that nobody wants to open.
## Related policies
See `depend-toward-stability`, `contain-dependencies`, `assign-clear-ownership`, and
`design-for-replaceability`.
