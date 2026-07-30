---
id: avoid-duplicated-knowledge
title: Keep each architectural fact in one authoritative place
scope: general
strength: guidance
tags: [knowledge, duplication, change-amplification]
source:
  author: ArchCompass
  inspiration: [software-design literature]
description: >-
  A rule, mapping, or constant that the system depends on should have exactly one
  authoritative home, so a conceptual change is one edit rather than a synchronized
  set of them. The target is duplicated knowledge, not duplicated text.
---
## Intent
Prevent one conceptual change from requiring synchronized edits in places that have no way
of knowing about each other.
## Guidance
Consolidate duplicated rules, mappings, and capability knowledge under their natural owner,
and let everyone else derive or request rather than restate. The unit of concern is
knowledge, not characters: two code fragments that look identical but would change for
different reasons are not duplication, while two that look nothing alike but encode the
same threshold are. When a fact must exist in more than one place — a cached projection, a
value duplicated across a process boundary — make one copy authoritative, name it, and make
the direction of synchronization explicit and one-way. Prefer deriving a second
representation at build or startup time over maintaining it by hand. Where duplication
persists for a reason, the reason belongs in the design record, not in a comment asking
future readers to remember.
## Signals
The same list, constant, validation rule, or conditional appears in unrelated modules, and
one of the copies is already stale. A code review comment says "also update X" and the
reviewer had to know that from memory. Adding one enum value requires touching a parser, a
formatter, a user-facing label table, and a database check constraint. Two components
disagree about a boundary condition — one treats a limit as inclusive, the other as
exclusive — because each encoded it separately. A test asserts a value that is also
hard-coded in the implementation, so the pair can drift together without failing.
## Diagnostic questions
Are these copies accidental, cached, or intentionally independent? If this fact changes,
what is the complete set of places that must change with it, and how would a maintainer
discover that set? Which copy is authoritative, and can the others be derived from it
instead of maintained?
## Likely consequences
Changes become atomic, contradictory definitions become unlikely, and the cost of a
conceptual change stops scaling with the size of the codebase. Where knowledge is
duplicated, the copies diverge on a schedule nobody chose: the divergence is discovered as a
defect, usually in the copy that is exercised least. Consolidating also makes the fact
findable, which matters more than the edit count.
## Exceptions
Deliberate denormalization is valid when synchronization and ownership are explicit — a
read model kept in sync from a named source, a value copied across a service boundary with
a stated staleness bound. Independent systems that happen to agree on a value today should
keep their own copies rather than acquire a shared dependency for a coincidence. Test data
may restate expected values on purpose, since a test that computes its expectation the same
way as the implementation asserts nothing.
## Positive example
The set of supported output formats is declared once by the component that renders them.
Request validation, the option list shown to users, and the documentation generator all
read that declaration, so adding a format is one edit and no part of the system can offer
an option the renderer does not implement.
## Counterexample
Unrelated code is merged because two fragments happen to look alike: an invoice line
formatter and an audit log formatter both produced a currency string, so they were
consolidated into one shared helper. When invoices need locale-specific grouping and audit
logs must stay machine-parseable, the helper grows a mode flag, and every future change to
either format must now reason about the other.
## Related policies
See `explicit-source-of-truth`, `assign-clear-ownership`, `give-state-one-writer`, and
`back-out-of-wrong-abstractions`.
