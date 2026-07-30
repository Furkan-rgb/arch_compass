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
description: >-
  Volatile code may depend on stable code, never the reverse; when a stable module
  needs a volatile capability, it declares the interface and the volatile side
  implements it. Dependency direction decides which changes stay local and which
  ripple into the core.
---
## Intent
Keep frequently changing code from being load-bearing for code that rarely changes, so that
churn at the edges never forces re-review of the center.
## Guidance
Let volatile modules such as presentation, adapters, and configuration depend on stable ones
such as the domain model, and when a stable module needs a volatile capability, define the
interface on the stable side and implement it on the volatile side. Stability here means
rate of change and number of dependents, not quality: a module that many things depend on
must change rarely, and a module that changes weekly must have few dependents. Judge each
import by asking which side is more likely to change and whether the arrow points the wrong
way; if it does, invert it by expressing what the stable side needs as a port it owns. The
interface belongs to the consumer, not the implementor — an interface defined by the
adapter and imported by the core is the same coupling with an extra file. Composition of
concrete implementations happens in one place at the edge, which is allowed to know
everything because nothing depends on it.
## Signals
Domain or core modules import presentation, transport, or vendor modules. Small edge edits
force re-review or re-release of central code, and the core's test suite fails when a
serialization format changes. An interface lives in the same package as its only
implementation and is imported across a layer boundary in the wrong direction. The core
knows about a transport concept — a request object, a status code, a template — in order to
read one value out of it. Release ordering is constrained because a stable component cannot
be built without a volatile one.
## Diagnostic questions
Which side of this edge changes more often, and how many things depend on each side? Would
inverting this dependency let the volatile side churn without touching the stable one? Who
owns this interface — the module that needs the capability, or the module that provides it?
## Likely consequences
Change frequency aligns with blast radius: churn stays at the edges while the core
accumulates reliability and its tests stay meaningful. New adapters can be added without
opening the core, which makes both extension and replacement routine. Where the arrows
point the wrong way, the core inherits the volatility of everything it touches, and its
stability becomes a matter of luck rather than structure.
## Exceptions
Any module, including the innermost core, may depend directly on a stable standard library
or platform type; inverting those adds ceremony without reducing risk. Where two components
change together for genuine domain reasons, a direct dependency is honest and inversion
only hides the coupling. A composition root depends on everything by design, and that is
the point of having one.
## Positive example
The scheduling core declares a notifier port describing what it needs to send — recipient,
event, and urgency — and an email adapter implements it. Switching to push notifications
adds one adapter and changes one line of composition, and the scheduling core is not
recompiled, retested, or reviewed.
## Counterexample
The pricing engine imports the web framework's request object so it can read a locale
header. Pricing now cannot be used from a batch job or a scheduled task without
constructing a fake request, a framework upgrade forces a pricing release, and the domain
rule that prices depend on locale is buried inside a transport detail.
## Related policies
See `keep-dependencies-acyclic`, `contain-dependencies`, `model-stable-concepts`, and
`keep-effects-at-the-edges`.
