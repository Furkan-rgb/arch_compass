---
id: explicit-source-of-truth
title: Make the source of truth explicit
scope: general
strength: guidance
tags: [configuration, knowledge, discoverability]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Let maintainers determine where authoritative state or configuration originates.
## Guidance
Name the owner, define precedence at one boundary, and expose derived views as derived.
## Signals
Several files can define the same setting and precedence is implicit.
## Diagnostic questions
Which value wins, who may change it, and how is that visible?
## Likely consequences
Configuration behavior is more predictable and easier to validate.
## Exceptions
Layered configuration is valid when its precedence is intentional and documented.
## Positive example
Model identity and dimensions are loaded from one validated configuration file.
## Counterexample
Environment variables, constants, and CLI defaults silently disagree.
## Related policies
See `avoid-duplicated-knowledge` and `make-relationships-discoverable`.

