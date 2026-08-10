---
id: judge-concentration-by-who-pays
title: Judge a module that holds many concerns by who pays for them
scope: general
strength: guidance
tags: [modularity, decomposition, cohesion, change-amplification]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  A module holding many concerns is not wrong for holding them. It is wrong when
  each concern pulls its own dependants through it, so that every change lands on
  all of them and every reader loads the whole file to follow one thread.
---
## Intent
Decide what a crowded module costs by asking who pays for it, so that concentration is
read as evidence about the module's seam rather than as a fault in its size.
## Guidance
A module that holds a great deal is doing what a module is for. Complexity has to sit
somewhere, and a module complicated inside but reached through one narrow seam has taken
it off everyone else: its callers know one operation, and its internals can be rearranged
without any of them learning that they were. Judge that module by its seam, not by its
line count.

The judgement turns the other way when the concerns each have their own callers. If one
package reaches for the pricing rules, another for the audit trail, and a third for the
retry policy, then the module is not hiding three things behind one contract — it is
three contracts sharing a file. Every change now lands in code that three unrelated
dependants read, every reader loads all three subjects to follow one, and the module's
name has stopped predicting what is inside it.

Weigh four things before saying anything. What a change here amplifies into: how much of
the repository a reader would have to check after touching it. What it costs to hold in
mind: whether one thread through it can be followed without loading the rest. Whether its
concerns change for different reasons — two things that always change together are one
concern however unalike they look. And whether the team still navigates by its name: when
people say "it is in there somewhere", the name has stopped being an index.

This is not an argument for splitting. A split has its own price — a new interface to
maintain, a new indirection for readers to cross, and the risk of drawing the seam in the
wrong place and having to back out. Where the concerns are not yet distinct, or the right
seam is not yet visible, leaving them together and waiting is the better move. Say what
the module costs and to whom; recommend a seam only when you can name where it falls and
what it would hide.
## Signals
Different dependants reach into the same module for disjoint parts of it, and no two of
them use the same operation. A change to one subject in the file requires re-testing every
dependant, because the dependants cannot tell which subject they depend on. Its public
surface is broad and flat: many exported names, few of which are ever used together. The
module's name is a category rather than a subject — `utils`, `manager`, `core`, `service`
— or people describe it by listing what is in it. Merge conflicts in it come from teams
working on unrelated features. A newcomer asked where a rule lives names this module
because it is where everything lives.
## Diagnostic questions
Who pays for this concentration — the module's own maintainers, or every caller? Can one
thread through this module be followed without reading the others? Do its concerns change
for the same reasons and at the same times, or does each have its own trigger? If it were
split along the seam you have in mind, what would each half hide from the other, and how
much would they still have to know about each other? Would the split remove a cost
somebody is paying now, or only move it?
## Likely consequences
A module read by its seam rather than its size keeps a deep implementation that callers
never pay for, and a genuinely tangled one is described in terms of the amplification it
causes rather than the number of lines it contains. Reading concentration as automatic
fault produces the opposite: deep modules are broken up into shallow ones whose interfaces
carry the complexity that used to be hidden, and the system gains navigation cost without
losing any.
## Exceptions
Generated code, vendored code, and a module that is deliberately a facade over one
subsystem all concentrate by design and are not evidence of anything. A module in the
middle of a planned decomposition is expected to look like this until the move finishes.
Deployment, ownership, or performance constraints may require concentration that
knowledge alone would not, and that is worth recording next to the module rather than
rediscovering.
## Positive example
A scheduling module holds several thousand lines of calendar arithmetic, timezone
handling, and conflict resolution, and exposes two operations. Every dependant uses both
of them, none knows which internal rule it relies on, and a rewrite of the conflict
resolver changes no caller. The module is crowded, and the crowd is paid for by the
people who maintain it.
## Counterexample
A shared `core` module holds tax rules, PDF rendering, and the retry policy. Billing
imports the first, reporting the second, and the delivery worker the third; the three
have nothing to say to one another. A change to the tax table forces every dependant
through review because nothing in the import says which subject is being depended on, and
each of the three teams reads the whole module to find the part that is theirs.
## Related policies
See `prefer-deep-modules` for why a large implementation behind a small interface is the
goal rather than the problem, and `split-or-join-by-shared-knowledge` for where a seam
belongs once one is warranted. Before recommending a split, weigh
`delay-premature-abstraction` and `migrate-incrementally`. When the concerns turn out to
be phases of one run rather than separate subjects, see `organize-by-responsibility`; when
the module's name no longer predicts its contents, see `name-for-meaning`.
