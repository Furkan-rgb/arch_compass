---
id: prefer-deep-modules
title: Prefer modules whose interfaces are simpler than their implementations
scope: general
strength: guidance
tags: [deep-modules, interfaces, complexity]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Concentrate useful behavior behind a small conceptual surface.
## Guidance
Judge a module by how much complexity it absorbs relative to the concepts it exposes.
## Signals
An interface has nearly as many concepts and options as the implementation.
## Diagnostic questions
Does the caller need to understand the module's internal workflow to use it correctly?
## Likely consequences
More implementation change remains local and callers carry less incidental knowledge.
## Exceptions
Small transparent value objects can be intentionally shallow.
## Positive example
A resumable job store exposes start, checkpoint, resume, and status while owning persistence details.
## Counterexample
Splitting four sequential steps into four public classes adds navigation without hiding decisions.
## Related policies
See `keep-interfaces-simple` and `pull-complexity-downward`.
