---
id: separate-general-from-special-purpose
title: Keep caller-specific logic out of general-purpose mechanisms
scope: general
strength: guidance
tags: [special-cases, generality, layering, coupling]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Prevent a shared mechanism from absorbing knowledge about the specific features built on top of it.
## Guidance
Push specializations upward into the callers that own them and keep the lower-level mechanism uniform; a mechanism that must branch on who is calling has a misplaced boundary.
## Signals
A general module contains flags, mode enums, or conditionals that exist for exactly one caller, and its tests enumerate feature scenarios instead of mechanism behavior.
## Diagnostic questions
Would this branch disappear if that one feature were deleted, and could the caller express the specialization through the mechanism's ordinary operations?
## Likely consequences
The mechanism stays reusable and testable in isolation, and feature changes stop rippling into shared code.
## Exceptions
A mechanism may offer a small extension point such as a hook or strategy when several callers genuinely vary at the same seam.
## Positive example
An undo system stores generic actions, and the editor registers its own selection-restoring actions instead of the undo core knowing about selections.
## Counterexample
A retry helper gains an is-billing-job flag because one workflow wants different backoff.
## Related policies
See `pull-complexity-downward`, `different-layer-different-abstraction`, and `assign-clear-ownership`.
