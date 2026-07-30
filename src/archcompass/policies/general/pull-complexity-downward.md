---
id: pull-complexity-downward
title: Pull unavoidable complexity into the module that can contain it
scope: general
strength: guidance
tags: [complexity, ownership, usability]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  When complexity cannot be removed, put it where it is solved once rather than
  where every caller must solve it again. A module that is harder inside so its
  callers are simpler outside has made the right trade.
---
## Intent
Avoid making every caller solve the same difficult problem, by placing unavoidable
complexity with the one component that has the knowledge to handle it.
## Guidance
Let a lower-level owner validate, normalize, default, or coordinate the details it
understands best, and let its interface promise the simple thing callers actually want.
The trade is deliberate: accept a more sophisticated implementation in one place in
exchange for removing an obligation from every call site. Apply it where the module has
strictly more information than its callers — the shape of the data it stores, the quirks
of the system it wraps, the ordering its own state requires. Do not apply it to decisions
that legitimately differ per caller; pushing a policy choice downward does not simplify
anything, it just hides who decided. The question is never whether the code looks tidier
below, but whether the module knows enough to be right for everyone.
## Signals
Callers repeat setup order, error translation, or provider-specific normalization. A
module's documentation explains what the caller must do before and after each call. The
same defensive check appears at every call site because the callee will not do it. Utility
helpers exist whose only purpose is to remember the sequence a lower-level interface
demands, and each caller has written its own slightly different copy.
## Diagnostic questions
Which module has enough knowledge to make this decision once? Is this a detail the callee
understands better than any caller, or a policy that genuinely varies by caller? If this
work moved down, would any caller need to override it, and how many would be relieved of
it entirely?
## Likely consequences
The owning module may become locally sophisticated while system-wide complexity falls, and
the sophistication stays reviewable because it is concentrated where the expertise is.
Leaving the complexity up means every caller reimplements it, each slightly differently,
and the resulting inconsistencies show up as bugs that no single module is responsible
for.
## Exceptions
Policy decisions that differ by caller should remain explicit at the application boundary;
a module that guesses at intent forces callers to work against it. Complexity should also
stay up when pushing it down would require the lower module to depend on concepts from a
higher layer, since that trades local simplicity for an inverted dependency.
## Positive example
A provider adapter normalizes its own voice identifiers before returning them, so callers
compare stable values instead of each learning that one provider lowercases its
identifiers and another pads them. The adapter grows one normalization step; four call
sites lose a special case each.
## Counterexample
A shared helper guesses business policy because moving code downward looked tidy. It picks
a default retry budget suitable for one workflow, and the other three now pass flags to
undo the guess, so the helper has absorbed a decision it cannot make correctly.
## Related policies
See `hide-implementation-details`, `eliminate-errors-by-design`, and `prefer-deep-modules`.
The limit on how far complexity may travel downward is set by
`separate-general-from-special-purpose`.
