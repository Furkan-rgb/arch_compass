---
id: apply-consistency-deliberately
title: Apply consistency where it reduces interpretation cost
scope: general
strength: guidance
tags: [consistency, conventions, clarity]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Make similar concepts behave similarly without forcing unlike responsibilities into one pattern.
## Guidance
Standardize naming, error handling, and lifecycle conventions at genuine shared boundaries.
## Signals
Equivalent operations use different terminology or error semantics without a domain reason.
## Diagnostic questions
Are the cases conceptually alike, and what does consistency let a maintainer infer?
## Likely consequences
Existing knowledge transfers and surprising special cases decline.
## Exceptions
Different domain semantics should remain visibly different.
## Positive example
All repositories use the same not-found and revision-conflict semantics.
## Counterexample
Every component is forced through one base class despite different ownership and lifecycle.
## Related policies
See `make-relationships-discoverable` and `keep-interfaces-simple`.

