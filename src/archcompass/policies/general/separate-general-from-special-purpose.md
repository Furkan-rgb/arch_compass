---
id: separate-general-from-special-purpose
title: Keep caller-specific logic out of general-purpose mechanisms
scope: general
strength: guidance
tags: [special-cases, generality, layering, coupling]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  A shared mechanism should know nothing about the particular features built on
  it. Specializations belong in the callers that own them, because a mechanism
  that branches on who is calling has a boundary in the wrong place.
---
## Intent
Prevent a shared mechanism from absorbing knowledge about the specific features built on
top of it, so the mechanism can be understood, tested, and reused on its own terms.
## Guidance
Push specializations upward into the callers that own them and keep the lower-level
mechanism uniform; a mechanism that must branch on who is calling has a misplaced
boundary. Give the mechanism operations general enough that each caller can express its
special case by composing them, rather than by asking the mechanism to recognize it. Where
several callers vary at the same point, close the gap with one deliberate extension point
— a strategy, a hook, a supplied policy object — instead of a growing set of caller-named
flags. The line is knowledge, not code volume: a mechanism may be large and intricate, but
if it can name one of its callers, it has crossed over.
## Signals
A general module contains flags, mode enums, or conditionals that exist for exactly one
caller, and its tests enumerate feature scenarios instead of mechanism behavior. Parameter
names carry domain vocabulary from a layer above. Adding a feature reliably requires a
small edit inside the shared component. The shared module imports types that only one
consumer defines, so it cannot be reused without dragging that consumer along.
## Diagnostic questions
Would this branch disappear if that one feature were deleted, and could the caller express
the specialization through the mechanism's ordinary operations? If a second, unrelated
consumer adopted this mechanism tomorrow, which parts would be meaningless to it? Does the
mechanism's vocabulary belong to its own layer, or borrow from the layer above?
## Likely consequences
The mechanism stays reusable and testable in isolation, and feature changes stop rippling
into shared code. The alternative accumulates: each special case is individually small,
they interact combinatorially, and eventually the shared component is the most dangerous
file in the system because every feature has a claim on it.
## Exceptions
A mechanism may offer a small extension point such as a hook or strategy when several
callers genuinely vary at the same seam. Performance sometimes justifies a specialized
fast path inside a general mechanism, when the specialization is expressed in the
mechanism's own terms and the general path remains correct on its own.
## Positive example
An undo system stores generic actions, and the editor registers its own selection-restoring
actions instead of the undo core knowing about selections. The core's contract is a stack
of reversible operations, so a second tool with entirely different actions can use it
untouched.
## Counterexample
A retry helper gains an is-billing-job flag because one workflow wants different backoff.
Two releases later it carries three such flags, its behavior can only be predicted by
knowing the caller, and the retry logic can no longer be reasoned about as a single
mechanism.
## Related policies
See `pull-complexity-downward`, `different-layer-different-abstraction`, and
`assign-clear-ownership`. When a mechanism has already accumulated caller-specific
branches, `back-out-of-wrong-abstractions` describes the way back.
