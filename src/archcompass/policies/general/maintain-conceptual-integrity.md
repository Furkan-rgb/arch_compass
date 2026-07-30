---
id: maintain-conceptual-integrity
title: Keep one coherent design idea across the system
scope: general
strength: guidance
tags: [conceptual-integrity, consistency, design]
source:
  author: ArchCompass
  inspiration: ["Fred Brooks, The Mythical Man-Month"]
description: >-
  A system built on a few concepts applied uniformly is easier to learn than a
  more capable one built on several. Every addition either strengthens the
  governing ideas or dilutes them, and a feature that resists the existing
  vocabulary calls for a design conversation rather than an exception.
---
## Intent
Preserve a small set of governing concepts that the whole system expresses, so that
learning one part of it predicts the others.
## Guidance
Decide what the system's core concepts are — its unit of work, its identity model, its
error model, the shape of its extension points — and require every addition to be
expressible in them. A feature that cannot be stated in the existing vocabulary is
information: either the vocabulary needs a considered extension, or the feature belongs
somewhere else. Prefer the coherent design over the more capable one when the two conflict,
because a maintainer pays for every extra concept at every future encounter while a missing
capability is paid for once. Give someone the standing to refuse a change on grounds of
coherence alone; conceptual integrity does not emerge from a series of individually
reasonable local decisions.
## Signals
Three subsystems solve the same problem three ways — one with callbacks, one with events,
one by polling — and no reason for the difference is recorded anywhere. New code picks
between competing idioms based on which file it sits next to. The same domain noun means
different things in different modules, with translation code between them. Onboarding takes
longer than the system's size suggests, because knowing one area predicts nothing about the
next.
## Diagnostic questions
Can this feature be described using concepts the system already has? If a maintainer
learned this subsystem thoroughly, what would they correctly guess about the others? Are we
introducing a second way to do something we already do, and if so, what happens to the
first?
## Likely consequences
A system with few concepts applied consistently is learnable in one pass and lets a
maintainer transfer understanding between areas, which is where most of a long-lived
system's cost sits. As governing concepts multiply, every change begins with a local
investigation, review quality falls because reviewers no longer share a model of what
correct looks like, and the system becomes a collection of neighborhoods rather than a
design.
## Exceptions
A genuinely different problem may need a different idea, and forcing it into the reigning
concept produces a worse distortion than the inconsistency; the test is whether the
difference lies in the problem or only in the author. A subsystem inherited from elsewhere
may keep its own internal coherence behind a translating boundary instead of being half
converted.
## Positive example
A workflow system settles on one notion of a step — a named unit with declared inputs, a
single outcome, and a retry policy — and every capability added over two years is expressed
as steps. Someone who understands one workflow can read any other, and the scheduler, the
audit log, and the interface all use the same word for the same thing.
## Counterexample
An extension mechanism is added three times: plugins in one subsystem, configuration-driven
hooks in another, subclassing in a third, each introduced by whoever needed extensibility
that quarter. None is wrong on its own, but extending the system now starts with an
investigation into which mechanism the area uses, and shared tooling can serve none of them.
## Related policies
See `apply-consistency-deliberately`, `design-it-twice`, `record-design-rationale`, and
`align-architecture-with-teams`.
