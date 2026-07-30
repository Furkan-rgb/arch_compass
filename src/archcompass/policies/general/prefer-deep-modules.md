---
id: prefer-deep-modules
title: Prefer modules whose interfaces are simpler than their implementations
scope: general
strength: guidance
tags: [deep-modules, interfaces, complexity]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Judge a module by the ratio between the functionality it provides and the
  interface it exposes. Deep modules hide substantial implementation behind a
  small conceptual surface; shallow ones charge callers interface cost without
  absorbing complexity in return.
---
## Intent
Concentrate useful behavior behind a small conceptual surface, so that most of a
module's complexity remains invisible to the code that uses it.
## Guidance
Judge a module by how much complexity it absorbs relative to the concepts it exposes,
not by its size. A deep module offers a few operations whose meaning a caller can hold
in mind, while internally handling the awkward cases: retries, ordering, caching,
partial failure, resource lifecycle. When decomposing a system, prefer fewer, deeper
modules over many thin ones, and resist splitting a module merely because its
implementation is large; implementation size is what the interface is supposed to
shield callers from. When an interface grows a new parameter, mode, or callback, ask
whether the module could instead absorb that variation internally.
## Signals
An interface has nearly as many concepts, options, and configuration knobs as the
implementation has decisions. Callers must invoke several methods in a required order
to accomplish one conceptual operation. Wrapper layers exist that add a name but no
behavior. A class is little more than getters, setters, and forwarding calls, so every
meaningful decision is made by its callers.
## Diagnostic questions
Does the caller need to understand the module's internal workflow to use it correctly?
Could two of these small classes merge into one module with a smaller combined surface?
If the implementation were rewritten, how much caller code would survive unchanged?
## Likely consequences
Deep modules keep implementation change local: callers carry less incidental knowledge,
so rework stays behind the interface. Shallow modules spread each decision across their
callers, and a system of them has high cognitive cost everywhere while hiding almost
nothing.
## Exceptions
Small transparent value objects and data carriers are intentionally shallow; their
purpose is to expose structure, not to hide behavior. A thin adapter that exists only
to translate between two boundaries is acceptable when the translation itself is the
whole job.
## Positive example
A resumable job store exposes start, checkpoint, resume, and status. Internally it owns
serialization, storage layout, crash recovery, and concurrent access, and none of those
decisions appear in its interface; a caller that survives a redesign of the storage
layout never learns it happened.
## Counterexample
A four-step import process is split into four public classes — fetcher, validator,
transformer, writer — each with its own configuration and error contract. Every caller
must instantiate and wire all four in the right order, so the decomposition added
surface area and navigation without hiding a single decision.
## Related policies
See `keep-interfaces-simple`, `pull-complexity-downward`, and
`split-or-join-by-shared-knowledge`.
