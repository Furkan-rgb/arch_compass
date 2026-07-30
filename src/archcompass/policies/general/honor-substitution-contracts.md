---
id: honor-substitution-contracts
title: Every implementation of a contract must be usable wherever the contract is expected
scope: general
strength: guidance
tags: [substitution, contracts, polymorphism, interfaces]
source:
  author: ArchCompass
  inspiration: ["Barbara Liskov, behavioral subtyping"]
description: >-
  An interface is a behavioral promise, not a list of method names. An
  implementation that strengthens preconditions, weakens guarantees, or fails
  where the contract promises an answer forces callers to know which variant they
  hold, which dissolves the abstraction.
---
## Intent
Keep an abstraction worth depending on, so that holding the interface is enough and a caller never has to know which implementation it received.
## Guidance
Treat a contract as covering accepted inputs, returned values, error signalling, ordering, visibility and performance class — not merely method names and types. An implementation may accept more than the contract requires and guarantee more than it promises; it may never demand more of callers or deliver less. In practice that means no new preconditions, no narrower accepted range, no raising where the contract says a value comes back, and no returning empty where the contract promises a result or a stated error. Write the contract's expectations as a test suite that every implementation must pass, and treat that suite, rather than prose, as the definition. When a candidate implementation cannot satisfy it, the answer is a different abstraction, not a documented caveat; if a caller has to ask what it is holding — a type check, a capability flag, a setting naming the variant — substitution has already failed.
## Signals
Code branches on the concrete type of something it received through an interface. An implementation raises not-supported for part of the interface it claims to provide. A caller guards a call with a check that only matters for one backend. A shared test suite passes for one implementation and is skipped for another. Interface documentation accumulates per-implementation notes about which methods are safe, what empty input does, or which variant is synchronous.
## Diagnostic questions
Could a caller swap one implementation for another without reading either? Does every implementation accept everything the contract admits and return exactly what the contract describes? Which implementation-specific behavior are callers relying on today without saying so?
## Likely consequences
When implementations are genuinely interchangeable, adding one is a local act, and testing against a simple in-memory variant is honest rather than a hopeful approximation. When they are not, the interface stops being a boundary: knowledge of each variant leaks outward, type checks spread through callers, and the abstraction charges its indirection cost while buying no independence.
## Exceptions
Genuine capability differences exist — a store without transactions, a transport that cannot stream, a backend that cannot enumerate. Model those as separate contracts a caller explicitly asks for, rather than as optional parts of a common one. Performance may vary within a stated class; an implementation three orders of magnitude slower is a different contract in practice, however identical its signatures.
## Positive example
A document repository contract states that fetching a missing identifier returns an absent result rather than an error, and that a write is visible to reads that follow it in the same session. An in-memory implementation and a durable one both pass the same contract suite, and a new implementation is measured against that suite before anything depends on it.
## Counterexample
A cache interface has one implementation whose write is immediate and another whose write is asynchronous and eventually visible. Half the callers were written against the immediate one and read back straight after writing, so swapping implementations in one deployment produced intermittent missing data that took a week to attribute.
## Related policies
See `model-stable-concepts`, `keep-interfaces-simple`, and `avoid-surprising-behavior`.
