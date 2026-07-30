---
id: make-interfaces-somewhat-general
title: Shape interfaces around the capability, not the first caller
scope: general
strength: guidance
tags: [interfaces, generality, deep-modules]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Define a module's operations in terms of the capability it owns rather than the
  workflow of whoever called it first, while implementing only what is needed
  today. Somewhat general interfaces stay smaller and outlive the screens and
  jobs that prompted them.
---
## Intent
Keep a module's interface from encoding one caller's workflow as if it were the module's
purpose, so the interface survives changes to that caller.
## Guidance
Separate the two questions that get conflated: what the interface should express, and how
much the implementation should handle. Make the interface general — phrased in the
module's own nouns and verbs, covering the shape of the capability — and keep the
implementation specific to current needs. The target is somewhat general, not maximally
general: the simplest interface that serves every current use, without speculative
parameters for uses nobody has. A useful test is whether a second caller with the same
underlying need would find the existing operations natural, or would have to ask for a new
one. When a caller requests an operation named after its own step in a process, look for
the underlying capability behind that step and offer that instead.
## Signals
Method names and parameters mirror one caller's screens, wizard steps, or job stages. A
module accumulates near-identical operations that differ only by which context called
them. Parameters exist to tell the module which caller is calling, so it can behave
differently. Changing the order of steps in a user-facing flow requires renaming methods
on a storage or domain module. The interface has an operation nobody can describe without
naming the feature that prompted it.
## Diagnostic questions
What is the simplest interface that covers all current uses, and would it need to change
if a different caller arrived with the same underlying need? Is this operation named after
what the module does or after when it is called? Would this parameter still make sense if
the calling feature were redesigned tomorrow?
## Likely consequences
Interfaces stay smaller and more stable, and new callers compose existing operations
instead of requesting bespoke variants. Because the interface no longer tracks a
particular workflow, changes in the user experience stop propagating into modules that
have nothing to do with it. Caller-shaped interfaces grow one operation per feature, and
the module eventually has more surface than substance while still forcing a change for
every new caller.
## Exceptions
A deliberately caller-specific facade is appropriate when it exists to simplify exactly one
boundary, is named for that boundary, and sits above a general module rather than replacing
it. Generality also has a cost ceiling: an interface built for hypothetical future callers
is speculative design, and this policy asks for coverage of real current uses only.
## Positive example
A text buffer exposes insert and delete over ranges, plus a cursor position, rather than
backspace and delete-selection operations copied from the editor's keybindings. When the
editor later adds multi-cursor editing and a scripting API, both compose the existing range
operations, and the buffer is untouched.
## Counterexample
A storage module offers save-draft-from-wizard-step-two because that screen was the first
caller that needed saving, then gains three sibling operations for the other steps. When
the wizard is replaced by a single form, four operations must be deprecated, and the
module's interface still carries the vocabulary of a screen that no longer exists.
## Related policies
See `prefer-deep-modules`, `keep-interfaces-simple`, `delay-premature-abstraction`, and
`separate-general-from-special-purpose`.
