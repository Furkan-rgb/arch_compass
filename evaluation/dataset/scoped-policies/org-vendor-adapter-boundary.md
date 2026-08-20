---
id: org-vendor-adapter-boundary
title: Reach a third-party vendor through exactly one adapter package
scope: organisation
applies_to: acme-engineering
strength: required
tags: [vendors, boundaries, dependencies, procurement]
source:
  author: Acme Engineering
  inspiration: [evaluation fixture]
description: >-
  Every third-party vendor this organisation buys from is reached through one adapter
  package, and no other package names the vendor. Contracts are renegotiated yearly and
  a vendor we cannot price a migration away from is a vendor we cannot negotiate with.
---
## Intent
Keep the cost of replacing a paid vendor a number somebody can put in a slide, by keeping
the code that knows about the vendor in one place.
## Guidance
One package per vendor, holding the client, the credentials, the vendor's own vocabulary
and the translation into ours. Everything else depends on the translated concepts. The
vendor's name may appear in that package, in dependency manifests, and in deployment
configuration, and nowhere else — not in a type name a caller writes, not in a test outside
the package, not in a feature flag.
## Signals
The vendor's name appears in a module that is not the adapter. A type imported from the
vendor SDK is a parameter or return type of one of our own functions. Two packages both
hold credentials for the same vendor. A migration estimate cannot be produced without
grepping.
## Diagnostic questions
If this contract were not renewed, which packages would change? Can that list be produced
from the dependency graph rather than from a search? Does anything outside the adapter need
to know which vendor is behind the capability?
## Likely consequences
A vendor change becomes one package rewritten against tests that never mentioned the
vendor. Where the boundary has leaked, the same change becomes an unbounded search, and the
renewal is signed because nobody could price the alternative in time.
## Exceptions
A vendor whose product is the runtime itself — the cloud provider, the language runtime —
is not containable this way and is not in scope. A spike may name a vendor anywhere,
provided it is deleted or contained before it merges.
## Counterexample
The speech vendor is behind a provider port, and the vendor's name is also in the
frontend's catalogue module, in preflight validation, and in the entry point.
## Positive example
The payment gateway package holds the SDK, the webhook signatures and the currency
translation. The billing package takes a Money and a PaymentMethod, neither of which the
vendor defines, and its tests run with no vendor library installed.
## Related policies
contain-dependencies, hide-implementation-details, model-stable-concepts
