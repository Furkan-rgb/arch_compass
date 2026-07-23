---
id: model-stable-concepts
title: Define interfaces around stable concepts, not incidental mechanisms
scope: general
strength: guidance
tags: [interfaces, domain-model, stability]
source:
  author: ArchCompass
  inspiration: [domain-driven design literature]
---
## Intent
Keep short-lived implementation choices from shaping long-lived application contracts.
## Guidance
Name domain capabilities and results independently from the first provider or framework.
## Signals
Public interfaces contain vendor names, transport fields, or framework lifecycle objects.
## Diagnostic questions
Would this concept still exist if the current implementation were replaced?
## Likely consequences
Contracts change for domain reasons rather than adapter churn.
## Exceptions
Provider-specific features may remain explicitly provider-specific when portability is not a goal.
## Positive example
`VoiceCatalog` represents an application capability while Qwen owns its construction.
## Counterexample
Renaming every concrete object to `Generic*` without changing its semantics.
## Related policies
See `contain-dependencies` and `keep-interfaces-simple`.
