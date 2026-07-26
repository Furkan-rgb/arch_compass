---
id: make-interfaces-somewhat-general
title: Shape interfaces around the capability, not the first caller
scope: general
strength: guidance
tags: [interfaces, generality, deep-modules]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Keep a module's interface from encoding one caller's workflow as if it were the module's purpose.
## Guidance
Define operations in terms of the capability the module owns while letting the implementation serve only current needs; a second caller with the same underlying need should find the existing interface natural.
## Signals
Method names and parameters mirror one caller's screens or job steps, or a module accumulates near-identical operations that differ only by calling context.
## Diagnostic questions
What is the simplest interface that covers all current uses, and would it need to change if a different caller arrived with the same underlying need?
## Likely consequences
Interfaces stay smaller and more stable, and new callers compose existing operations instead of requesting bespoke variants.
## Exceptions
A deliberately caller-specific facade is appropriate when it exists to simplify exactly one boundary and is named accordingly.
## Positive example
A text buffer exposes insert and delete over ranges rather than backspace and delete-selection operations copied from the user interface.
## Counterexample
A storage module offers a save-draft-from-wizard-step-two operation because that screen was the first caller that needed saving.
## Related policies
See `prefer-deep-modules`, `keep-interfaces-simple`, and `delay-premature-abstraction`.
