---
id: program-strategically
title: Invest in design continuously instead of patching tactically
scope: general
strength: guidance
tags: [strategic-programming, complexity, incremental-change]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Working code is not the finish line. Spend a small, steady share of every
  change on the structure it touches, because complexity accumulates through
  sequences of individually reasonable shortcuts and is paid for with interest.
---
## Intent
Prevent complexity from accumulating through a sequence of individually reasonable
shortcuts, each too small to argue about and collectively decisive.
## Guidance
Treat each change as an opportunity to leave the affected design slightly better; when a
change fights the current structure, adjust the structure or record the debt explicitly
instead of adding another workaround. The investment is small and continuous — a share of
each task, not a scheduled cleanup phase — and it is spent where the current work already
required understanding: the module being edited, the interface being called, the name that
misled you. Working code is the minimum bar, not the goal; the goal is a structure the
next change can be made in. When the tactical option is genuinely right, say so out loud
and leave a marker, so that a deliberate shortcut is distinguishable from an accident.
## Signals
Fixes cluster in one module as flag additions, copy-adjusted branches, and callers routing
around a known-awkward interface rather than changing it. Estimates for similar tasks grow
over time with no change in scope. Reviews approve changes with the comment that the
structure is bad but this is not the place to fix it, repeatedly, for months. New team
members are warned which files not to touch.
## Diagnostic questions
If every future change were made in this same style, what would this module look like in a
year, and is the shortcut worth that trajectory? Is this workaround here because the
structure is wrong, or because changing it is out of scope right now? What would it cost
to fix the structure while the context is already loaded?
## Likely consequences
Development speed stays level over time, and cleanup happens in small continuous doses
rather than rare risky rewrites. The tactical path feels faster for the first several
changes and then stops: the system reaches a state where every change is expensive, no
single change is to blame, and the only remaining options are a rewrite or permanent
slowness.
## Exceptions
A time-boxed incident fix or a throwaway prototype may be deliberately tactical when the
follow-up correction is visible and scheduled. Code with a known, short expiry — a
migration shim due for removal, an experiment that will be deleted either way — does not
merit design investment it will never repay.
## Positive example
Adding a fourth report format prompts extracting format selection into the renderer that
owns it, so the fourth case becomes one registration. The extraction costs part of an
afternoon, and the fifth and sixth formats cost almost nothing.
## Counterexample
Each new provider adds another conditional to the same dispatch function because one more
branch is always cheaper than fixing the dispatch. Two years later the function is the
only place that knows how any provider works, nobody can change it safely, and every
provider change is scheduled as a risk.
## Related policies
See `design-it-twice`, `optimize-locality-of-change`, and `pull-complexity-downward`. When
the structural fix is too large for one change, stage it with `migrate-incrementally`.
