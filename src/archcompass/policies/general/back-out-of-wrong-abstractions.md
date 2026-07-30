---
id: back-out-of-wrong-abstractions
title: Dismantle an abstraction that no longer fits instead of parameterizing it further
scope: general
strength: guidance
tags: [abstraction, duplication, refactoring]
source:
  author: ArchCompass
  inspiration: ["Sandi Metz, The Wrong Abstraction"]
description: >-
  When a shared abstraction grows a flag or a branch for each new caller, the
  cheapest path is backward — inline it, let the duplication reappear, and
  re-extract along the seam that is genuinely shared. Duplication costs less
  than the wrong abstraction.
---
## Intent
Stop a shared abstraction from turning into a switchboard of caller-specific special cases
by unwinding it once its callers no longer share a reason to be together.
## Guidance
When a shared component grows a flag, a mode, or a conditional for each new caller, read
that as evidence that the callers do not share the behavior it was extracted from. The
cheapest move is backward: inline the component into each caller, let the duplication
reappear in full, then study the copies to find the seam that is actually common — which is
often narrower, somewhere else entirely, or absent. Do this while the special cases can
still be told apart, because a heavily parameterized component eventually reaches a state
where no caller exercises the general path and nobody can say which combinations are still
live. Duplication is a local cost a reader can see; the wrong abstraction is a distributed
cost a reader has to infer.
## Signals
A function's parameters are booleans named after its callers, and its body opens by
branching on which caller it is. Changing behavior for one caller requires reading every
other caller to confirm the branch is not shared. Several parameters are never varied while
one switches between two nearly disjoint bodies. Callers pass placeholder values for
parameters that do not apply to them, and nobody knows what those values mean.
## Diagnostic questions
If we inlined this into every caller, would any of them read worse? What do these callers
have in common now, as opposed to when the extraction was made? Is this code shared because
it expresses one idea, or because two things once looked alike?
## Likely consequences
Backing out restores the ability to change one caller without reasoning about the others,
and the re-extraction that follows sits on a real seam rather than a historical accident.
Continuing to parameterize turns a module into a decision table only its history explains:
each new caller is cheap to add and every existing caller becomes more expensive to change,
until the component can be edited only by adding branches.
## Exceptions
An abstraction whose parameters express genuine variation within one concept — a sort
order, a page size, a currency — is not a wrong abstraction however many of them it has.
When the callers are numerous and the special cases few, lifting the exceptions out of the
shared path is usually cheaper than dismantling it.
## Positive example
A document exporter had accumulated four flags separating an archival path from an
interactive one. The team copied the function into both call sites and deleted the branches
each side did not use, discovering that the only genuinely shared part was pagination,
which became a small helper both copies call and nothing else.
## Counterexample
One notification builder serves five channels through a mode parameter, plus flags for
whether to include a footer, whether to truncate, and whether to resolve recipients. A
truncation change for one channel breaks another, because the shared branch was never
shared on purpose, and the fix is a sixth flag.
## Related policies
See `delay-premature-abstraction`, `separate-general-from-special-purpose`, and
`split-or-join-by-shared-knowledge`.
