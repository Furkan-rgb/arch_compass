---
id: assign-clear-ownership
title: Give each responsibility one clear owner
scope: general
strength: guidance
tags: [responsibility, ownership, boundaries]
source:
  author: ArchCompass
  inspiration: [responsibility-driven design literature]
description: >-
  Every decision, invariant, and piece of domain knowledge belongs to exactly one
  module that holds the information needed to maintain it. Responsibility that is
  shared by default is enforced by nobody, and changes to it have no obvious home.
---
## Intent
Make it clear where behavior and decisions belong, so that a change has one destination and
an invariant has one guardian.
## Guidance
Assign ownership according to knowledge and invariants, not convenience or call order: the
owner of a rule is the module that holds the data the rule constrains and can refuse
operations that would break it. Name the owner explicitly in the design, and give it the
authority to say no — an owner that cannot reject invalid requests is a formatter, not an
owner. When two modules both seem to qualify, that is usually evidence that the
responsibility is really two responsibilities, or that the data is in the wrong place.
Everyone who is not the owner interacts through the owner's interface rather than
reproducing its decisions, and the owner's interface should be narrow enough that
reproducing them is harder than asking. A module that owns nothing and only sequences calls
between owners is a coordinator, and should be named as one.
## Signals
Several modules can answer the same domain question, and they disagree at the edges. No
single module can answer it completely, so callers assemble the answer from fragments. A
class named manager, helper, or service owns behavior because it is globally reachable
rather than because it holds the relevant state. The same validation rule is enforced in
the request handler, the domain object, and the storage layer, each slightly differently. A
bug fix requires edits in three modules because the decision it corrects was made in all
three.
## Diagnostic questions
Which module has the information and the authority to maintain this invariant? If this rule
changes next quarter, where does the change land, and how many other modules learn about
it? Can the nominal owner actually refuse an operation that would violate the rule, or can
callers reach around it?
## Likely consequences
Changes have an obvious destination, duplicated decisions decline, and invariants hold
because one component is in a position to enforce them. Reviewers can evaluate a change
against a single component's contract rather than reasoning about a distributed
consensus. Where ownership is diffuse, invariants degrade quietly: each module assumes
another is checking, and the system's real rules become whatever the union of the code
happens to permit.
## Exceptions
Shared protocols intentionally distribute responsibility across participants, but each
participant's role should still be named and each obligation assigned. Read-only derived
views may be maintained by consumers when the derivation is explicit and the authoritative
copy is unambiguous. Genuinely cross-cutting concerns such as tracing may be applied
uniformly, provided no domain decision travels with them.
## Positive example
A capability registry owns which operations a connected backend supports, and every part of
the system that needs to know — request admission, the user-facing option list, the
scheduler — asks it. When a backend gains a capability, the registry changes and nothing
else does, because no other module encodes its own opinion about what is supported.
## Counterexample
A miscellaneous coordinator owns quota enforcement because it happens to sit on the path
every request takes, while the account module holds the balances. The coordinator reads
balances, applies its own rounding, and writes back, so the account module cannot guarantee
that a balance is ever non-negative — and a second caller that skips the coordinator
silently bypasses the quota entirely.
## Related policies
See `organize-by-responsibility`, `hide-implementation-details`, `give-state-one-writer`,
and `align-architecture-with-teams`.
