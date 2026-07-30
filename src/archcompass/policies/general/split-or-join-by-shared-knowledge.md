---
id: split-or-join-by-shared-knowledge
title: Merge code that shares knowledge; separate code that does not
scope: general
strength: guidance
tags: [modularity, cohesion, decomposition, boundaries]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Decide module size by shared knowledge, not by line counts or structural
  symmetry. Code that cannot be understood or changed apart belongs together;
  code that can stand alone should not be forced to share a boundary.
---
## Intent
Size modules by the knowledge they share rather than by line count or file symmetry, so
that every boundary hides something rather than merely dividing something.
## Guidance
Bring fragments together when they share information, are always used together, or cannot
be understood apart; keep them separate when each can be understood and changed alone.
Neither small classes nor one big file is a goal in itself. A boundary is worth having
when it hides a decision — when a maintainer can work on one side without loading the
other side into memory. If a proposed split would require both halves to know the same
rule, encode the same format, or reach into each other's state, the seam is in the wrong
place and the two halves are one module. Test the split by asking what each side would
need to be told if the other were rewritten.
## Signals
Two modules read each other's internals or duplicate the same rule in order to work at
all, or one module hosts groups of members that never interact. A change to one file is
almost always accompanied by a change to its sibling. An interface between two components
exists only to move private state across the boundary. A file's members fall into clusters
that touch different data and share no vocabulary.
## Diagnostic questions
Could a maintainer fully understand one of these pieces without opening the other, and
does the boundary between them hide any information? If one side were replaced wholesale,
how much of the other would have to change? Are these pieces separate because they are
different, or because a convention said a file should be smaller than this?
## Likely consequences
Module boundaries land on real seams, interfaces shrink where artificial splits leaked
shared state, and unrelated concerns stop sharing fate. Splits made for symmetry create
interfaces that carry knowledge instead of hiding it, and merges made for convenience
produce modules whose parts change for unrelated reasons and drag each other along.
## Exceptions
Deployment, team, or security constraints may force a split or merge that knowledge alone
would not justify, and that seam deserves an explicit note. A boundary may also be drawn
early around something expected to grow independently, as long as the expectation is
stated and revisited rather than treated as settled.
## Positive example
Request parsing and its length and encoding rules live in one module because neither is
meaningful without the other. Callers see one operation that turns bytes into a validated
request, and the encoding rules can change without any caller learning that they did.
## Counterexample
A class is split into manager, helper, and implementation thirds that share private state
through setters to satisfy a size limit. Three files now exist, no decision is hidden by
any of the boundaries between them, and a reader must hold all three open to follow a
single operation.
## Related policies
See `prefer-deep-modules`, `organize-by-responsibility`, and
`optimize-locality-of-change`. When a merge has produced a shared abstraction that no
longer fits either caller, see `back-out-of-wrong-abstractions`.
