---
id: hide-implementation-details
title: Hide implementation details behind the owning boundary
scope: general
strength: guidance
tags: [information-hiding, dependencies, ownership]
source:
  author: ArchCompass
  inspiration:
    - "David Parnas, information hiding"
    - "John Ousterhout, A Philosophy of Software Design"
description: >-
  A module's interface should expose the capability callers need and keep its
  formats, algorithms, and provider-specific rules private. Every internal
  decision that escapes into a caller becomes a coordination cost the module
  pays on every future change.
---
## Intent
Prevent callers from depending on decisions that belong to another module, so those
decisions stay changeable by the module that owns them.
## Guidance
Decompose around the decisions likely to change, and place each behind the interface of
the module that owns it. Expose the capability a caller genuinely needs while keeping
storage formats, wire encodings, provider quirks, retry policy, caching, and algorithm
choice private. Return types that belong to the module's own vocabulary rather than types
imported from its dependencies, since an exposed dependency type makes every caller a
client of that dependency too. Treat leakage as a design defect regardless of access
modifiers: a field can be private and still leak if callers must know its behaviour to
call correctly, and a value can be public and harmless if nothing downstream depends on
how it was produced. When a caller asks for a new option, first ask whether it is really
asking the module to make a decision the module should be making itself.
## Signals
Several callers reproduce the same internal rule — the same string format, the same
rounding, the same ordering assumption — because the module does not offer it. Caller code
imports a type from the module's dependency in order to talk to the module. A field or
option exists purely so one caller can influence how the module works internally. Changing
a storage format or a provider requires edits in modules that were never supposed to know
about either. Comments in caller code explain the callee's internals so that future
readers can call it correctly.
## Diagnostic questions
Which decisions can this module change without coordinating with any caller, and which
would break someone? Does any caller reason about how the result was produced rather than
what it means? If this module were reimplemented on a different mechanism tomorrow, how
much caller code would have to move with it?
## Likely consequences
Callers become simpler and implementation changes stay inside one boundary, so rework is
proportional to the change rather than to the number of clients. Modules that leak their
internals accumulate implicit contracts nobody wrote down, and each of those contracts
turns a local change into a negotiation. Over time the leaked details, not the published
interface, become the thing that cannot be changed.
## Exceptions
Transparent data types are appropriate when their representation is itself the stable
shared concept — a point, a money amount, an identifier — and hiding it would add cost
without protecting anything. A module deliberately published as a thin binding to an
external system may expose that system's vocabulary, since fidelity is its purpose; it
should be named so callers know they are taking that dependency.
## Positive example
A speech-provider module exposes a voice catalogue and a synthesis operation returning
audio in the application's own audio type. Internally it discovers built-in voices,
negotiates a codec, retries transient failures, and caches the catalogue; none of that
appears in the interface, so replacing the provider changes one module and no caller.
## Counterexample
A wrapper around the same provider accepts a dictionary of provider options and passes it
straight through, returning the provider's own response object. Callers now set codec
flags and read provider status codes directly, so the wrapper hides nothing, and switching
providers means editing every call site the wrapper was supposed to protect.
## Related policies
See `assign-clear-ownership`, `contain-dependencies`, `prefer-deep-modules`, and
`design-for-replaceability`.
