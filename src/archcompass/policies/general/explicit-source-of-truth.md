---
id: explicit-source-of-truth
title: Make the source of truth explicit
scope: general
strength: guidance
tags: [configuration, knowledge, discoverability]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  For every piece of authoritative state or configuration, one place defines it
  and everything else is visibly derived from that place. When several sources
  can supply the same value and precedence is implicit, the system's real
  behaviour is discovered by experiment rather than by reading.
---
## Intent
Let maintainers determine where authoritative state or configuration originates, and
distinguish at a glance between a value that is defined and a value that is derived.
## Guidance
For each significant setting or piece of state, name exactly one owner that defines it.
Where several inputs legitimately contribute — a file, an environment, a command-line
override — resolve them at one boundary into a single validated object, and let everything
downstream read only that object. Make derived values visibly derived: compute them from
the authority rather than storing a second copy that can drift, and if a copy is required
for performance, mark it as a cache with a defined refresh. Never let a default live in two
places; a default is part of the definition and belongs with it. Precedence must be
written down as code in one resolution step, not implied by import order, by which module
happened to run first, or by a fallback chain scattered across call sites.
## Signals
Several files can define the same setting and the winner depends on load order. Reading a
value requires knowing whether the environment, a constants module, or a command-line
default takes precedence, and no single function encodes that answer. The same fact is
stored in two tables or two objects and a reconciliation job exists to keep them agreed.
A bug report is answered by asking someone to print the effective configuration at
runtime, because it cannot be determined by reading. Changing a documented default has no
effect because a second default shadows it.
## Diagnostic questions
Which value wins, who may change it, and how is that visible to someone reading the code?
If this value is wrong in production, what is the single place to look? Is this field
authoritative or derived, and does the code make the difference obvious?
## Likely consequences
Configuration behaviour becomes predictable and testable, because one resolution step can
be validated in isolation and its output asserted. Ownership questions get answered by
reading rather than by experiment. Where the source of truth is implicit, values drift,
divergence is discovered in production, and each incident adds another defensive
override that makes the next divergence harder to trace.
## Exceptions
Layered configuration is valid and often necessary when its precedence is intentional,
resolved in one place, and inspectable. Caches and read models are legitimate derived
copies as long as their authority and staleness policy are stated. The policy forbids
ambiguity about which copy is authoritative, not the existence of more than one copy.
## Positive example
A service resolves settings once at startup by merging a packaged default file, a
deployment file, and explicit overrides in a fixed order, validating the result into a
single immutable settings object. Every component receives that object; an operator can
dump it and see both the effective value and which layer supplied it, so a wrong value has
exactly one place to look.
## Counterexample
An embedding model's identity is read from an environment variable in one module, from a
module-level constant in another, and from a command-line default in a third. Two of them
disagree after a deployment, index writes and index reads use different models, and the
mismatch shows up as quietly degraded search results rather than as a failure.
## Related policies
See `give-state-one-writer`, `avoid-duplicated-knowledge`, `make-relationships-discoverable`,
and `fail-fast-on-bad-configuration`.
