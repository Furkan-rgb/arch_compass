---
id: delay-premature-abstraction
title: Delay abstractions until variation is credible
scope: general
strength: guidance
tags: [abstraction, simplicity, change]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  An abstraction introduced before its variation exists is a guess about a boundary,
  paid for in interfaces, indirection, and configuration. Wait until a second real
  implementation or a committed change shows where the seam actually is.
---
## Intent
Avoid paying interface, factory, and configuration costs for imagined variation, and let
the shape of a boundary be determined by evidence rather than anticipation.
## Guidance
Keep one behavior local until a second implementation or a committed change reveals the
stable boundary, then extract along the seam the two cases actually share. An abstraction
must earn its place by removing or containing present complexity — if it only defers the
same decision behind another name, it has added a concept and hidden nothing. Prefer
writing the concrete case twice and studying the difference over designing the interface
from the first case alone; the first implementation rarely reveals which of its assumptions
are essential. Distinguish anticipated variation from committed variation: a second
provider on next quarter's roadmap with a signed contract is evidence, and a second
provider someone can imagine is not. When you do abstract, abstract at the point of
greatest agreement between the real cases, not at the widest point that could accommodate
hypothetical ones.
## Signals
An interface has one implementation, one caller, and no credible second variant. A factory
selects between exactly one option, or a registry contains a single registration made at
startup by the only module that reads it. Configuration keys exist that have never been set
to anything but their default. A plugin mechanism was built before any plugin. The names in
an abstraction are generic — handler, processor, strategy — because no one could say what
distinguishes the members of a set that has one element.
## Diagnostic questions
What present complexity does this abstraction remove or contain? Which second
implementation exists or is committed, and does it actually fit this interface? If the
anticipated variation never arrives, what does this cost a reader for the next three years?
## Likely consequences
The design carries fewer concepts, and future boundaries can reflect real evidence about
what varies. Concrete code is also cheaper to change than abstract code, so waiting keeps
options open rather than closing them. Premature abstraction has the opposite effect: the
guessed boundary is usually in the wrong place, and once callers depend on it, correcting
it costs more than the abstraction ever saved.
## Exceptions
A safety, testing, or platform boundary can justify one implementation — an interface that
exists so effects can be substituted in tests, or so a platform-specific detail stays
isolated, is earning its keep from day one. A published contract that external consumers
already depend on must be designed ahead of its implementations. A genuinely committed
second case may be designed for before it is built, provided its requirements are known
rather than assumed.
## Positive example
A report formatter stays a plain function inside the module that renders reports. When a
second output target with materially different layout rules arrives, the two concrete
implementations are compared, and only the three operations they truly share are lifted
into an interface — which turns out not to include the layout parameters the original
design would have exposed.
## Counterexample
Interfaces, a registry, and a factory are added for a notification sender because a second
channel might exist someday. Two years later there is still one channel, but every new
developer reads three files to find the code that sends a message, and the interface's
signature — shaped around a single synchronous channel — is the reason the eventual second
channel needs a special case rather than an implementation.
## Related policies
See `model-stable-concepts`, `prefer-deep-modules`, `back-out-of-wrong-abstractions`, and
`preserve-reversibility`.
