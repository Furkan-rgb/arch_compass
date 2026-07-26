---
id: avoid-pass-through-parameters
title: Do not thread values through layers that ignore them
scope: general
strength: guidance
tags: [information-leakage, parameters, coupling]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Keep intermediate modules from depending on knowledge they neither use nor understand.
## Guidance
When a value must travel from a high layer to a low one, give it one owned home, such as the module that reads it or an explicitly scoped context object, instead of adding it to every signature along the path.
## Signals
The same parameter appears in many signatures where it is only forwarded, and adding one setting rewrites a chain of constructors across modules that never read it.
## Diagnostic questions
Which modules actually read this value, and what is the narrowest home that lets its producer and consumers meet without informing everyone in between?
## Likely consequences
Signatures reflect real inputs, and introducing a cross-cutting setting stops causing chain edits through unrelated layers.
## Exceptions
Explicit threading is right when each level genuinely interprets the value, and a named request-scoped context object beats ambient global state.
## Positive example
Certificate configuration is handed to the connection factory at composition time instead of passing through router, dispatcher, and handler signatures.
## Counterexample
A verbosity flag is added to eleven function signatures so the innermost formatter can read it.
## Related policies
See `keep-interfaces-simple`, `hide-implementation-details`, and `optimize-locality-of-change`.
