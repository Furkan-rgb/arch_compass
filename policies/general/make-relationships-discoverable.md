---
id: make-relationships-discoverable
title: Make important relationships explicit and discoverable
scope: general
strength: guidance
tags: [discoverability, dependencies, configuration]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Help maintainers find dependencies, ownership, and configuration without relying on hidden convention.
## Guidance
Represent important relationships in types, composition, names, or queryable metadata.
## Signals
Behavior depends on import side effects, naming coincidences, or undocumented registration.
## Diagnostic questions
How would a new maintainer locate and verify this relationship?
## Likely consequences
Unknown unknowns decrease and structural evidence becomes more reliable.
## Exceptions
Well-established language conventions need not be restated everywhere.
## Positive example
Provider registration occurs in one visible composition root.
## Counterexample
Importing an unrelated module silently mutates a global registry.
## Related policies
See `explicit-source-of-truth` and `apply-consistency-deliberately`.

