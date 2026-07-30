---
id: design-it-twice
title: Compare two materially different designs before committing
scope: general
strength: guidance
tags: [design, alternatives, strategic-programming, decisions]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  For a consequential or hard-to-reverse decision, sketch at least two genuinely
  different designs and compare them against stated criteria before choosing. The
  first workable decomposition is rarely the best one, and comparing is the cheapest
  way to find out.
---
## Intent
Avoid mistaking the first workable decomposition for the best design when a decision is
consequential or difficult to reverse.
## Guidance
Sketch at least two materially different allocations of responsibility or interfaces, then
compare information hiding, interface complexity, change locality, failure modes, and fit
with credible future changes before choosing. Materially different means the alternatives
put the same knowledge in different places or draw the boundary through a different seam —
not the same design with other names. State the comparison criteria before evaluating, so
the exercise tests the designs rather than confirming the preferred one. Spending an hour
on the second sketch is cheap next to the cost of discovering the boundary was wrong after
callers depend on it, and the value often comes from what the second design teaches about
the first rather than from adopting it. Scale the effort to the reversibility of the
decision: cheap-to-unmake choices deserve a moment, load-bearing boundaries deserve a
written comparison and a recorded rationale.
## Signals
The first plausible design is accepted without alternatives, and the discussion moves
straight to implementation detail before module boundaries have been tested. Ownership of a
key responsibility remains debatable after the design is agreed. The justification offered
for a boundary is that it matches an existing file layout or a familiar pattern. A design
document describes one option and lists its benefits with no comparison. A reviewer's
question about a different decomposition is answered with effort already spent rather than
with a property of the design.
## Diagnostic questions
What fundamentally different design could satisfy the same needs? Which comparison criteria
would reveal a meaningful advantage, and were they stated before or after the choice? If
this decision turns out wrong in six months, what does unwinding it cost — and does that
cost justify more comparison now?
## Likely consequences
Hidden assumptions surface earlier, trade-offs become explicit, and the selected design has
a reason stronger than familiarity or momentum. The rejected alternative is itself useful:
it documents what was considered and gives a starting point if the chosen design fails.
Designs adopted without comparison tend to encode the first author's mental model, and the
cost appears later as boundaries that everyone works around but nobody can justify.
## Exceptions
Do not manufacture alternatives for a small, reversible change with an established local
precedent; following the existing pattern is the right answer and inventing a rival wastes
attention. An urgent incident requires a temporary containment fix, with the design
comparison deferred to the follow-up rather than performed under pressure. Where an
external constraint genuinely admits one structure, record that constraint instead of
staging a comparison whose outcome is fixed.
## Positive example
Before adding a long-running analysis feature, a team compares three placements of the same
responsibility: the request handler assembles and owns the analysis input, a dedicated
domain service owns it, or the storage layer materializes it on write. Each is evaluated
against the same evolution scenarios — a second input source, a change to the ranking rule,
a switch to asynchronous execution — and the domain service wins because it is the only one
where the ranking rule has a single home.
## Counterexample
Two alternatives are presented that differ only in class names while keeping the same
responsibilities, dependencies, and public interface. The comparison concludes in five
minutes, the design review is recorded as complete, and the boundary that was never
questioned is the one that has to be moved a year later.
## Related policies
See `assign-clear-ownership`, `optimize-locality-of-change`, `delay-premature-abstraction`,
`record-design-rationale`, and `preserve-reversibility`.
