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
---
## Intent
Ensure modules can be understood, tested, and replaced in some order.
## Guidance
When two modules need each other, extract the shared concept both depend on, invert one edge behind an interface owned by the higher-level side, or merge them if they are genuinely one unit.
## Signals
Imports are deferred into function bodies to dodge circular-import errors, tests only pass with both modules loaded, or a change in either module reliably breaks the other.
## Diagnostic questions
If these modules must always change and ship together, are they actually one module, and if not, which direction of the cycle represents the real dependency?
## Likely consequences
The dependency order gives an incremental path for builds, tests, comprehension, and eventual replacement.
## Exceptions
Mutually recursive definitions inside one module boundary are ordinary; the policy governs edges between separately owned modules.
## Positive example
The domain package defines a repository interface and persistence implements it, so domain code never imports the adapter that serves it.
## Counterexample
The orders module imports billing for prices while billing imports orders for line items, and both hide it with function-local imports.
## Related policies
See `depend-toward-stability`, `contain-dependencies`, and `assign-clear-ownership`.
