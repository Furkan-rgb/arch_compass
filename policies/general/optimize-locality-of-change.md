---
id: optimize-locality-of-change
title: Keep one conceptual change local
scope: general
strength: guidance
tags: [locality, change-amplification, dependencies]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Reduce coordinated edits caused by a single decision.
## Guidance
Group knowledge that changes together while separating responsibilities that change independently.
## Signals
Adding one provider requires changes in presentation, validation, workflow, and root composition.
## Diagnostic questions
Which files change together, and is there one responsibility behind those edits?
## Likely consequences
Feature changes touch fewer locations and partial updates become less likely.
## Exceptions
Cross-cutting security or compliance changes may intentionally affect many boundaries.
## Positive example
Adding a provider requires one adapter and one composition registration.
## Counterexample
A large central module is justified only because all changes are now in one file.
## Related policies
See `avoid-duplicated-knowledge` and `contain-dependencies`.

