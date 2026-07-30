---
id: apply-consistency-deliberately
title: Apply consistency where it reduces interpretation cost
scope: general
strength: guidance
tags: [consistency, conventions, clarity]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  Make conceptually similar things behave and read the same way, so a maintainer who
  has learned one case can predict the rest. Consistency is a means of reducing what
  must be learned, not a mandate to force unlike responsibilities through one shape.
---
## Intent
Make similar concepts behave similarly without forcing unlike responsibilities into one
pattern, so that knowledge gained from one part of the system predicts another.
## Guidance
Standardize naming, error semantics, lifecycle, and argument order at genuine shared
boundaries — the places where a maintainer will meet several instances of the same idea and
expect them to agree. Consistency earns its keep by allowing inference: if every repository
signals absence the same way, a reader who has seen one has read them all. Apply it to
things that are alike in responsibility, not merely alike in shape; two classes with the
same method names and different obligations are a trap, not a convention. When you must
deviate, deviate visibly, so the difference reads as a decision rather than an oversight.
Where a convention exists, follow it even when your local preference differs, and change it
globally rather than starting a second one.
## Signals
Equivalent operations use different terminology or error semantics without a domain reason
— one lookup returns null for absence, another raises, a third returns an empty result
object. Argument order or naming flips between sibling functions, so call sites must be
read rather than skimmed. A single concept has three names across layers and no glossary
says they are the same thing. Conversely, an inheritance hierarchy or shared base class
groups components that have nothing in common except that they were written at the same
time. New code copies whichever nearby file the author happened to open.
## Diagnostic questions
Are these cases conceptually alike, or only structurally similar? What can a maintainer
infer about the unfamiliar case from the familiar one once they agree? If the two diverge
later, does the shared convention become a lie that must be maintained?
## Likely consequences
Existing knowledge transfers, surprising special cases decline, and review can focus on
what is genuinely new in a change rather than on rediscovering local dialects. Uniformity
imposed on dissimilar responsibilities has the opposite effect: it hides the differences
that matter behind a shared vocabulary, and every real distinction has to be re-learned as
an exception.
## Exceptions
Different domain semantics should remain visibly different; a queue that drops on overflow
and one that blocks must not share a name or signature. A boundary with an external system
inherits that system's conventions where translating them would obscure the mapping. An
established convention that is genuinely wrong should be replaced wholesale rather than
preserved for consistency's sake.
## Positive example
Every repository in a system reports a missing record and a stale-revision conflict the
same way, with the same two error types and the same fields on them. A maintainer writing
against a repository they have never opened knows what to catch and what the fields mean,
and a reviewer can check the call site without reading the implementation.
## Counterexample
Every component in a system is forced through one base class that owns construction,
configuration, and shutdown, even though some components are singletons created at startup
and others are per-request objects. The base class grows optional hooks and lifecycle flags
for cases it does not fit, and reading any subclass now requires understanding which of the
inherited stages actually apply to it.
## Related policies
See `make-relationships-discoverable`, `keep-interfaces-simple`, `avoid-surprising-behavior`,
and `maintain-conceptual-integrity`.
