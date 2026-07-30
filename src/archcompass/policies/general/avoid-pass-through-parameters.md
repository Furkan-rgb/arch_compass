---
id: avoid-pass-through-parameters
title: Do not thread values through layers that ignore them
scope: general
strength: guidance
tags: [information-leakage, parameters, coupling]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  A value that travels through several layers only to be forwarded makes every layer
  on the path depend on knowledge it never uses. Give the value one owned home where
  its producer and its consumer can meet, instead of widening every signature between
  them.
---
## Intent
Keep intermediate modules from depending on knowledge they neither use nor understand, so
that adding an input does not widen the interfaces of modules it has nothing to do with.
## Guidance
When a value must travel from a high layer to a low one, give it one owned home — the
module that reads it, an object constructed with it, or an explicitly scoped context —
instead of adding it to every signature along the path. Prefer supplying the consumer at
composition time, so the value never traverses the call chain at all: if the low-level
component is built by a factory that already knows the setting, no caller in between needs
to. Where a value genuinely varies per operation, a single named request-scoped object
carrying the operation's inputs is better than a growing parameter list, and far better
than ambient global state, because its lifetime and contents are visible. Judge each
parameter by whether the receiving module interprets it; a parameter that is only forwarded
is a leak of the caller's concerns into a module that should not have them.
## Signals
The same parameter appears in many signatures where it is only forwarded, and adding one
setting rewrites a chain of constructors across modules that never read it. A function's
parameter list is longer than its body is interesting, and most parameters appear exactly
once, in the recursive or delegating call. A diff that adds a feature touches ten files,
nine of which only widen a signature. Intermediate modules import a type solely to name a
parameter they pass on. Someone introduces a global or a thread-local specifically to stop
the threading, which trades a visible problem for an invisible one.
## Diagnostic questions
Which modules actually read this value? What is the narrowest home that lets its producer
and consumers meet without informing everyone in between? Could the consumer be constructed
with this value once, rather than told it on every call?
## Likely consequences
Signatures come to reflect real inputs, so a reader can infer what a function depends on
from how it is declared. Introducing a cross-cutting setting stops causing chain edits
through unrelated layers, which lowers both the cost and the review burden of such changes.
Left unchecked, pass-through parameters couple layers that share nothing conceptually, and
each new one makes the next one easier to justify.
## Exceptions
Explicit threading is right when every level genuinely interprets the value — a deadline
that each layer must check, a cancellation signal each stage honors. A named request-scoped
context object is a legitimate home for values that are genuinely per-operation and read in
several places, and it beats both long parameter lists and ambient global state. Very short
chains of two calls rarely justify introducing an abstraction to avoid the threading.
## Positive example
Certificate configuration is handed to the connection factory at composition time. The
router, dispatcher, and handler know nothing about certificates, and enabling mutual
authentication changes the factory and the composition root only, leaving every signature
on the request path untouched.
## Counterexample
A verbosity flag is added to eleven function signatures so the innermost formatter can read
it. Ten of those functions forward the flag without inspecting it, every one of their tests
gains an argument, and the next diagnostic setting will follow exactly the same path
because the precedent is now established.
## Related policies
See `keep-interfaces-simple`, `hide-implementation-details`, `optimize-locality-of-change`,
and `different-layer-different-abstraction`.
