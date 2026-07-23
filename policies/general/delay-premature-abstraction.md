---
id: delay-premature-abstraction
title: Delay abstractions until variation is credible
scope: general
strength: guidance
tags: [abstraction, simplicity, change]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Avoid paying interface, factory, and configuration costs for imagined variation.
## Guidance
Keep one behavior local until a second implementation or committed change reveals the stable boundary.
## Signals
An interface has one implementation and no independent caller or credible future variant.
## Diagnostic questions
What present complexity does the abstraction remove or contain?
## Likely consequences
The design carries fewer concepts and future boundaries can reflect real evidence.
## Exceptions
A safety, testing, or platform boundary can justify one implementation.
## Positive example
A local formatter stays a function until different formatting policies actually appear.
## Counterexample
Interfaces, registries, and factories are added solely because another provider might exist someday.
## Related policies
See `model-stable-concepts` and `prefer-deep-modules`.

