---
id: prefer-composition-over-inheritance
title: Compose behavior from parts instead of inheriting it from parents
scope: general
strength: guidance
tags: [composition, inheritance, coupling]
source:
  author: ArchCompass
  inspiration: ["Gamma, Helm, Johnson & Vlissides, Design Patterns"]
description: >-
  Implementation inheritance couples a child to its parent's internals and fixes
  variation at class-definition time, while composition keeps each part
  replaceable and lets behavior vary per instance. Inherit only for genuine
  subtype contracts; compose for reuse.
---
## Intent
Keep behavior assembled from replaceable parts rather than fixed by a class hierarchy, so
that variation stays cheap and coupling stays visible.
## Guidance
Reuse implementation by holding a collaborator, not by extending a class. Implementation
inheritance binds a child to details its parent never promised — field layout, the order in
which methods call each other, which step is expected to be overridden — so the parent
cannot be refactored without auditing its descendants, and the child's behavior is fixed
when the class is written rather than when the object is built. Reserve inheritance for the
case where the subtype is genuinely usable everywhere the supertype is expected, and prefer
implementing an interface over inheriting an implementation even then. When a hierarchy
starts growing a level to accommodate a combination of traits, that is the moment to turn
those traits into constructor-supplied parts. The test is whether a new variation can be
introduced by passing something different instead of defining something new.
## Signals
A hierarchy is three or more levels deep and the behavior of one call has to be assembled
by reading all of them. Subclasses override a method and call the parent version at a
particular point the parent never documented. A base class holds protected fields only some
descendants use, or methods that exist purely as hooks. New requirements produce a
combinatorial hierarchy, with a class for each pairing of two independent traits.
## Diagnostic questions
Does this subclass depend on how the parent is implemented, or only on what it promises?
Could this variation be supplied as a collaborator at construction time instead of fixed by
a class? If the parent's internals were rewritten, which descendants would break silently?
## Likely consequences
Composed designs let each part be tested, replaced, and reasoned about alone, and behavior
can vary per instance and per configuration without introducing new types. Deep
implementation hierarchies spread one behavior across several files with no explicit
contract holding them together, so the base class becomes unchangeable in practice and
every new combination of traits costs another class.
## Exceptions
Inheritance is the right tool for a real subtype relationship with a stable, documented
contract, and for narrow extension points a framework defines deliberately. Where a
language offers no other way to share a small amount of structure, one shallow layer of
inheritance is an acceptable cost provided the base exposes no mutable internals.
## Positive example
A message handler takes a validator, a rate limiter, and a transport as constructor
arguments. Handling messages from a trusted internal source means passing a permissive
validator, adding a new limiting strategy means writing one small class, and the handler
itself has not changed since it was written.
## Counterexample
An import job base class defines fetch, parse, and store as overridable steps, and six
subclasses extend it. Two of them need to parse before fetching everything, so they
override fetch to do nothing and smuggle the work into parse; changing the base class's
step order is now impossible, because two descendants depend on it being violated.
## Related policies
See `honor-substitution-contracts`, `hide-implementation-details`, and
`contain-dependencies`.
