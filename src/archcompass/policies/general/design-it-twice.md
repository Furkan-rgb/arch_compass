---
id: design-it-twice
title: Compare two materially different designs before committing
scope: general
strength: guidance
tags: [design, alternatives, strategic-programming, decisions]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Avoid mistaking the first workable decomposition for the best design when a decision is consequential or difficult to reverse.
## Guidance
Sketch at least two materially different allocations of responsibility or interfaces, then compare information hiding, interface complexity, change locality, failure modes, and fit with credible future changes before choosing.
## Signals
The first plausible design is accepted without alternatives, ownership remains debatable, or discussion focuses on implementation detail before module boundaries are tested.
## Diagnostic questions
What fundamentally different design could satisfy the same needs, and which comparison criteria would reveal a meaningful advantage?
## Likely consequences
Hidden assumptions surface earlier, trade-offs become explicit, and the selected design has a reason stronger than familiarity or momentum.
## Exceptions
Do not manufacture alternatives for a small, reversible change with an established local precedent, or when an urgent incident requires a temporary containment fix.
## Positive example
Before adding model-based report questions, compare provider-owned prompt assembly, application-owned context assembly, and a dedicated conversation domain service against the same evidence and evolution scenarios.
## Counterexample
Two alternatives differ only in class names while keeping the same responsibilities, dependencies, and public interface.
## Related policies
See `assign-clear-ownership`, `optimize-locality-of-change`, and `delay-premature-abstraction`.
