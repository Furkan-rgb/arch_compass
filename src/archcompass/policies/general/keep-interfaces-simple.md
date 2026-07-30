---
id: keep-interfaces-simple
title: Keep interfaces narrow and difficult to misuse
scope: general
strength: guidance
tags: [interfaces, usability, errors]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  An interface should be easy to use correctly and hard to use incorrectly:
  cohesive operations, validated inputs, meaningful results, and no required
  sequencing the caller must remember. Every flag, mode, and ordering rule is
  knowledge the interface has pushed onto everyone who calls it.
---
## Intent
Minimize the knowledge callers need for correct use, so that the obvious way to call an
interface is also the right way.
## Guidance
Expose cohesive operations whose meaning a caller can state without reference to the
implementation, take inputs that are validated or already proven, and return results that
say what happened. Absorb sequencing: if two calls must happen in a fixed order, offer one
operation that performs both, rather than documenting the order. Prefer several named
operations over one operation with a mode flag, since a boolean parameter at a call site
tells the reader nothing. Count the concepts a caller must hold — parameters, modes,
lifecycle rules, error cases, ordering constraints — and treat that count, not the method
count, as the size of the interface. Where a wrong call is possible, prefer making it
unrepresentable over documenting it.
## Signals
Callers must set flags in combinations, and only some combinations are meaningful. Methods
must be invoked in a fragile order, with the order recorded in a comment or discovered
through a runtime error. The same three calls appear together at every call site, which
means the interface is missing an operation. Parameters exist that only some callers may
pass, or that must be null unless another parameter is set. A caller has to inspect the
returned object to discover which of several outcomes occurred, with no type distinguishing
them.
## Diagnostic questions
Can invalid states or call sequences be made unrepresentable rather than documented? What
must a caller know beyond the signature to call this correctly, and where is that written?
If a new caller copies the nearest existing call site, will it be right?
## Likely consequences
Call sites become smaller and more uniform, and errors move from scattered misuse to one
clear boundary that can be tested. Reviewers can judge a call by reading it, without
reconstructing the callee's state machine. Interfaces that stay wide push their complexity
outward: each caller reimplements the same sequencing, the variants drift, and the
resulting bugs appear far from the interface that caused them.
## Exceptions
Low-level primitives may remain flexible when their audience genuinely needs explicit
control and would otherwise reimplement the mechanism themselves. A wide interface is also
acceptable when it faithfully models an inherently wide external protocol, provided a
narrow, opinionated interface is layered above it for ordinary use.
## Positive example
A resumable-job module exposes start, checkpoint, resume, and status. Checkpoint validates
the job's current state before advancing, so an out-of-order call is rejected with a clear
result rather than silently corrupting progress, and no caller needs to know how state is
persisted between calls.
## Counterexample
A facade offers thirty loosely related methods and is called simple because it is one
class. Half of them require an initialize call first, three take an options dictionary
whose valid keys are documented nowhere, and one takes a boolean that switches between two
unrelated behaviours, so every call site is a small experiment.
## Related policies
See `eliminate-errors-by-design`, `prefer-deep-modules`, `avoid-surprising-behavior`, and
`make-interfaces-somewhat-general`.
