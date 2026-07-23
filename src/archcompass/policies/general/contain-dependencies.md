---
id: contain-dependencies
title: Contain volatile dependencies behind a narrow boundary
scope: general
strength: guidance
tags: [dependencies, boundaries, providers]
source:
  author: ArchCompass
  inspiration: [software-architecture literature]
---
## Intent
Limit the reach of dependencies whose API or behavior may change.
## Guidance
Translate external concepts at one adapter boundary and keep the application model provider-neutral.
## Signals
Vendor types, constants, or errors appear across presentation, workflow, and persistence modules.
## Diagnostic questions
How many modules must change when the dependency changes?
## Likely consequences
Provider upgrades and replacements have a smaller, more visible blast radius.
## Exceptions
A stable standard type may be used directly when translation would add no information hiding.
## Positive example
Only the Qwen adapter imports Qwen request and response types.
## Counterexample
A provider-neutral interface contains a union of every vendor's option fields.
## Related policies
See `model-stable-concepts` and `optimize-locality-of-change`.
