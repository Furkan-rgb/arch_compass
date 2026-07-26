---
id: depend-toward-stability
title: Point dependencies toward the more stable concept
scope: general
strength: guidance
tags: [dependencies, stability, inversion, layering]
source:
  author: ArchCompass
  inspiration:
    - "Robert C. Martin, stable-dependencies principle"
    - "Alistair Cockburn, hexagonal architecture"
---
## Intent
Keep frequently changing code from being load-bearing for code that rarely changes.
## Guidance
Let volatile modules such as presentation, adapters, and configuration depend on stable ones such as the domain model, and when a stable module needs a volatile capability, define the interface on the stable side and implement it on the volatile side.
## Signals
Domain or core modules import presentation, transport, or vendor modules, and small edge edits force re-review or re-release of central code.
## Diagnostic questions
Which side of this edge changes more often, and would inverting it let the volatile side churn without touching the stable one?
## Likely consequences
Change frequency aligns with blast radius: churn stays at the edges while the core accumulates reliability.
## Exceptions
Any module, including the innermost core, may depend directly on a stable standard library or platform type.
## Positive example
The scheduling core declares a notifier port and the email adapter implements it, so switching to push notifications never touches scheduling.
## Counterexample
The pricing engine imports the web framework's request object to read a locale header.
## Related policies
See `keep-dependencies-acyclic`, `contain-dependencies`, and `model-stable-concepts`.
