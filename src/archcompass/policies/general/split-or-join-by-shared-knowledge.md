---
id: split-or-join-by-shared-knowledge
title: Merge code that shares knowledge; separate code that does not
scope: general
strength: guidance
tags: [modularity, cohesion, decomposition, boundaries]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Size modules by the knowledge they share rather than by line count or file symmetry.
## Guidance
Bring fragments together when they share information, are always used together, or cannot be understood apart; keep them separate when each can be understood and changed alone. Neither small classes nor one big file is a goal in itself.
## Signals
Two modules read each other's internals or duplicate the same rule in order to work at all, or one module hosts groups of members that never interact.
## Diagnostic questions
Could a maintainer fully understand one of these pieces without opening the other, and does the boundary between them hide any information?
## Likely consequences
Module boundaries land on real seams, interfaces shrink where artificial splits leaked shared state, and unrelated concerns stop sharing fate.
## Exceptions
Deployment, team, or security constraints may force a split or merge that knowledge alone would not justify, and that seam deserves an explicit note.
## Positive example
Request parsing and its length and encoding rules live in one module because neither is meaningful without the other.
## Counterexample
A class is split into manager, helper, and implementation thirds that share private state through setters to satisfy a size limit.
## Related policies
See `prefer-deep-modules`, `organize-by-responsibility`, and `optimize-locality-of-change`.
