---
id: make-illegal-states-unrepresentable
title: Choose representations in which invalid states cannot be constructed
scope: general
strength: guidance
tags: [state, invariants, types, errors]
source:
  author: ArchCompass
  inspiration: ["Yaron Minsky", "Alexis King, Parse, Don't Validate"]
description: >-
  Encode invariants in the shape of the data rather than in comments and runtime
  checks. When a representation admits only valid values, whole classes of defect
  become unwritable instead of merely tested for.
---
## Intent
Move invariants out of documentation and scattered assertions into the structure of the data itself, so that entire classes of mistake cannot be expressed.
## Guidance
Choose representations in which every constructible value is a valid one. Replace a cluster of independent optional fields whose combinations are constrained by some flag with a set of alternatives — one variant per legitimate case, each carrying exactly the data that case needs and nothing else. Require required data at construction rather than assigning it afterwards, so there is no window in which an object is incomplete. Give distinct concepts distinct types instead of sharing a string or an integer between them, so that swapping two arguments stops being a plausible mistake. Prefer a type that cannot be empty over a collection plus a comment promising it never is. Parse untrusted input into these representations once, at the edge, and let everything inward hold values whose validity is a property of their type rather than a claim in a docstring.
## Signals
Two fields must be absent together or present together, and every method that touches them re-checks the pairing. A status value has combinations with other fields that are documented as impossible. Functions open with assertions about arguments they were just handed. Boolean parameters select between behaviors, so a call site reads as a run of true and false with no meaning visible at the call. One identifier type stands for three different kinds of entity, and mixing them up compiles and runs.
## Diagnostic questions
Which values of this type are invalid, and what prevents one from being constructed? If a caller set these fields inconsistently, would the failure surface at the mistake or somewhere far downstream? Could this check disappear entirely if the data had a different shape?
## Likely consequences
When the representation carries the invariant, the check happens once at construction and every reader downstream is relieved of it, so adding a case forces every handler to be revisited rather than silently skipped. When the representation admits invalid combinations, the check is duplicated at each use, drifts apart as rules change, and failures appear far from the code that created the bad value — often long after that code has been rewritten.
## Exceptions
Data crossing a serialization boundary must stay permissive on the wire; this discipline applies to the in-memory representation that parsed data becomes, not to the encoding. Some invariants span multiple entities or depend on the outside world — uniqueness across a store, a reference that must still exist, a quota measured at the time of use — and cannot be enforced by shape alone; those belong to a transaction or an owner.
## Positive example
A payment outcome is one of three variants: settled, carrying an amount and a timestamp; declined, carrying a reason code; or pending, carrying a retry deadline. No caller can read an amount from a declined outcome because a declined outcome has no amount, and introducing a fourth result forces every handler to acknowledge it.
## Counterexample
The same outcome is a single record with a settled flag and nullable amount, reason and deadline fields. Nothing stops a settled record with a reason and no amount from being written; a reconciliation job trips over one three months later, and the code that produced it has been rewritten twice since.
## Related policies
See `eliminate-errors-by-design`, `validate-at-trust-boundaries`, and `model-stable-concepts`.
