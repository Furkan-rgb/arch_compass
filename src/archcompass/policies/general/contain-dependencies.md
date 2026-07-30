---
id: contain-dependencies
title: Contain volatile dependencies behind a narrow boundary
scope: general
strength: guidance
tags: [dependencies, boundaries, providers]
source:
  author: ArchCompass
  inspiration: [software-architecture literature]
description: >-
  A dependency whose API, semantics, or availability may change should be reachable
  from one place only, with its concepts translated into the application's own model
  at that boundary. Containment is what makes a dependency replaceable rather than
  structural.
---
## Intent
Limit the reach of dependencies whose API or behavior may change, so that the cost of an
upgrade or a replacement is proportional to the dependency's real role rather than to how
widely it was used.
## Guidance
Translate external concepts at one adapter boundary and keep the application model
provider-neutral: the adapter speaks the outside world's vocabulary on one side and the
application's on the other, and nothing past it knows which provider is in use. Design the
inward-facing interface from what the application needs, not from what the provider offers,
otherwise the provider's model leaks through a layer of renaming. External error types,
enums, identifiers, and configuration shapes all count as dependency concepts and all stop
at the boundary. Judge the containment by asking what a replacement would touch: if
swapping the dependency requires changes anywhere but the adapter and the composition root,
it is not contained. Volatility, not popularity, sets the standard — a widely used library
with a churning API deserves an adapter, and a frozen one may not.
## Signals
Vendor types, constants, or error classes appear in presentation, workflow, and persistence
modules. A supposedly neutral interface carries the union of every provider's option
fields, so callers must know which fields their provider honors. Application code catches
an exception type defined by the dependency. The dependency's identifiers or status strings
are stored in the domain model and its enums are persisted verbatim. An upgrade note about
a renamed parameter produces a diff across a dozen unrelated files.
## Diagnostic questions
How many modules must change when the dependency changes its API? If this dependency were
replaced with a different one offering the same capability, what would the diff touch
beyond the adapter? Does the inward-facing interface describe what the application needs,
or what this particular provider happens to offer?
## Likely consequences
Provider upgrades and replacements have a smaller, more visible blast radius, and the
decision to change providers becomes an engineering estimate rather than a rewrite.
Testing improves as a side effect, because a narrow owned interface is straightforward to
substitute. Uncontained dependencies gradually become architecture: their model becomes the
application's model, and the choice made in the first week cannot be revisited in the third
year.
## Exceptions
A stable standard type — a date, a UUID, a byte buffer — may be used directly, since
translating it adds a layer without hiding anything. Where a dependency is the whole point
of a component and no substitution is contemplated, an adapter may be honest overhead;
record that judgment rather than leaving it implicit. A prototype may skip containment
deliberately, provided the boundary is added before the prototype acquires dependents.
## Positive example
Only the speech-synthesis adapter imports that provider's request and response types; the
rest of the system passes a small owned request object and receives an owned result with an
owned error type. When the provider renames a field and changes its retry semantics, the
change is a single file and one round of adapter tests.
## Counterexample
A provider-neutral interface is defined as the union of every vendor's option fields, so
callers set six optional parameters and learn from documentation which three their current
provider ignores. The interface now changes whenever any vendor adds an option, and adding
a fourth provider means every existing caller must be re-examined.
## Related policies
See `model-stable-concepts`, `optimize-locality-of-change`, `depend-toward-stability`, and
`design-for-replaceability`.
