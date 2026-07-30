---
id: model-stable-concepts
title: Define interfaces around stable concepts, not incidental mechanisms
scope: general
strength: guidance
tags: [interfaces, domain-model, stability]
source:
  author: ArchCompass
  inspiration: [domain-driven design literature]
description: >-
  Long-lived contracts should be named for the domain capabilities they provide,
  not for the provider, framework, or transport that currently implements them.
  A concept that would survive replacing the implementation is the right thing to
  build an interface from.
---
## Intent
Keep short-lived implementation choices from shaping long-lived application contracts, so
that contracts change when the domain changes rather than when a dependency does.
## Guidance
Name domain capabilities and results independently from the first provider, framework, or
protocol that happens to supply them. Sort candidate concepts by expected lifetime: the
business capability outlives the service that provides it, which outlives the client
library, which outlives the wire format. Build interfaces from the long-lived end and let
the short-lived end sit behind an adapter. Test a proposed concept by asking whether it
would still be meaningful under a different implementation; if the answer requires
explaining the current mechanism, the concept is the mechanism in disguise. Renaming is not
sufficient — a type is provider-shaped when its fields, states, and error cases follow the
provider's model, whatever it is called.
## Signals
Public interfaces contain vendor names, transport fields, framework lifecycle objects, or
status codes that only one implementation produces. Domain types carry optional fields that
exist because one provider returns them. Adding a second implementation requires widening
the interface rather than writing a new adapter. Error handling in the application branches
on codes that belong to a client library. A concept in the ubiquitous language of the team
has no corresponding type, while several types exist for mechanisms nobody outside the
adapter discusses.
## Diagnostic questions
Would this concept still exist if the current implementation were replaced tomorrow? Do
the names in this interface come from the domain or from a dependency's documentation? If a
second implementation appeared, would it fit this interface or force it to change?
## Likely consequences
Contracts change for domain reasons rather than adapter churn, so the cost of swapping or
adding an implementation stays inside one boundary. The application's vocabulary matches
the vocabulary people use when discussing requirements, which shortens every conversation
about a change. Where mechanisms shape contracts, each dependency upgrade becomes an
application-wide edit, and the accumulated provider vocabulary makes the domain harder to
see with every release.
## Exceptions
Provider-specific features may remain explicitly provider-specific when portability is not
a goal and the capability has no domain-neutral equivalent; the requirement is that the
specificity is visible in the name and confined to one module. Genuinely young domains are
another case: when nobody yet knows which concepts are stable, model close to the concrete
case and extract later rather than guessing at an abstraction.
## Positive example
A speech capability is expressed as a voice catalogue and a synthesis request returning
audio in the application's own type, defined in domain terms such as language, style, and
duration. One adapter maps a hosted provider onto it and another maps a local engine, and
neither the catalogue type nor its callers mention either.
## Counterexample
The application's interface returns the client library's response object, so callers read
its status field and handle its exception hierarchy directly. A later refactor renames the
types with a neutral prefix without changing a single field or state, so the contract still
tracks the provider's model and the second implementation must emulate it.
## Related policies
See `contain-dependencies`, `keep-interfaces-simple`, `plan-for-data-longevity`, and
`separate-model-context-from-provider-transport`.
