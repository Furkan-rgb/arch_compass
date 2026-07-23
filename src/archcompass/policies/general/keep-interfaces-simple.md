---
id: keep-interfaces-simple
title: Keep interfaces narrow and difficult to misuse
scope: general
strength: guidance
tags: [interfaces, usability, errors]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Minimize the knowledge callers need for correct use.
## Guidance
Expose cohesive operations with validated inputs and meaningful results; hide sequencing where possible.
## Signals
Callers must set flags in combinations or invoke methods in a fragile order.
## Diagnostic questions
Can invalid states or call sequences be made unrepresentable?
## Likely consequences
Call sites become smaller and errors move to clear boundaries.
## Exceptions
Low-level primitives may remain flexible when their audience needs explicit control.
## Positive example
A single resumable-job operation validates state before advancing a checkpoint.
## Counterexample
A facade with dozens of unrelated methods is called simple because it is one class.
## Related policies
See `eliminate-errors-by-design` and `prefer-deep-modules`.
