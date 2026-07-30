---
id: name-for-meaning
title: Choose names that carry the abstraction
scope: general
strength: guidance
tags: [naming, clarity, abstraction]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  A name is the smallest interface a design has: a precise one transmits the
  abstraction, an imprecise one sends the reader into the implementation.
  Difficulty naming something crisply is evidence that the design underneath is
  blurred.
---
## Intent
Make a name carry the abstraction it stands for, so that reading a call site is usually enough and reading the implementation is rare.
## Guidance
Choose names that say what a thing is or does in the caller's terms, precisely enough that a reader can predict behavior without opening the definition and generally enough that the name survives a change of implementation. Prefer a specific noun or verb over a category: manager, handler, data, info, helper and process describe nothing and invite unrelated behavior to accumulate beneath them. Include the unit or frame wherever a wrong assumption would be invisible in review — a duration, a deadline, a currency, a coordinate space. Use one word for one concept across the whole system, and never two words for the same concept. Treat naming difficulty as evidence about the design rather than a vocabulary problem: when a module can only be named by listing what it contains, or the honest name is a conjunction, the boundary is in the wrong place, and the fix is to move the boundary.
## Signals
A type's name is a category, and its methods have nothing in common with each other. A name needs a comment beside it to be understood. Two names in the same system mean the same thing, or one name means different things in different modules. A variable holding a deadline is called time, or one holding a count is called size. Names describe the current mechanism rather than the purpose, so replacing the storage engine would falsify half the identifiers in a file.
## Diagnostic questions
Could a reader predict what this returns from the name alone? Does the name describe what the thing is for, or how it happens to work today? If you cannot name this module in a short phrase, what are the two things inside it?
## Likely consequences
Precise names make code legible at a glance and keep unrelated behavior out, because adding something the name does not cover is visibly wrong to a reviewer. Vague names conceal the design: nobody can tell whether a change belongs where it was put, modules accrete responsibilities under a permissive label, and every reader pays to descend into implementations for information that should have been on the surface.
## Exceptions
Short conventional names are correct in small scopes where the referent is obvious and close by — a loop index, a lambda parameter, a local alias used two lines later. Established domain vocabulary should be used exactly as the domain uses it, even when a more descriptive invented term exists, because matching the language of the people who own the problem is the point.
## Positive example
A scheduling component names its operations reserve_slot, release_slot and next_available_after, and its values slot_duration and earliest_start. A reviewer who sees reserve_slot called from a read path objects immediately, without knowing anything about how reservations are stored.
## Counterexample
The same component instead exposes a data manager with process, update and handle. Within a year process has absorbed the retry loop, the audit write and the notification, because nothing in the name said any of them did not belong; the file is now the riskiest one in the system to change, and nobody can describe it in a sentence.
## Related policies
See `avoid-surprising-behavior`, `prefer-deep-modules`, and `organize-by-responsibility`.
