---
id: different-layer-different-abstraction
title: Give each layer a distinct abstraction
scope: general
strength: guidance
tags: [layers, abstraction, pass-through, complexity]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Every layer must express a different abstraction than the one beneath it —
  aggregating, translating, or enforcing something its caller would otherwise
  have to know. A layer that restates the interface below it adds a call hop and
  a maintenance obligation without hiding a decision.
---
## Intent
Ensure that an additional layer hides, translates, or consolidates complexity instead of
merely adding another name and call hop. A layer earns its place by changing what its
caller has to understand.
## Guidance
Make each layer express concepts appropriate to its responsibility. A layer should
aggregate several lower operations into one meaningful unit, enforce an invariant the
lower level cannot see, translate between representations, or narrow a general mechanism
to a specific policy; if it does none of these, collapse it into the interface it
duplicates. Judge a layer by the difference between the vocabulary on each side of it: a
layer whose parameters, names, and error types are the same as the level below is not an
abstraction, it is an alias. When adding a layer, state in one sentence what the caller no
longer needs to know, and reject the layer if the sentence cannot be written. Resist the
instinct that layering is inherently good structure — depth is only valuable when each
level is genuinely simpler than the one it covers.
## Signals
Methods mostly forward the same arguments to similarly named methods and return the same
result unchanged. Adjacent interfaces expose nearly identical concepts, parameter sets,
and required call sequencing, so a reader must trace three files to find the one place a
decision is made. Adding a field to a lower-level record requires threading it through
every intermediate signature. Error types from the bottom layer surface unmodified at the
top, proving no layer interpreted them. A change to any layer is nearly always accompanied
by a mechanical change to its neighbours in the same commit.
## Diagnostic questions
What knowledge or decision does this layer hide, and could its caller use the lower-level
interface with essentially the same understanding? If this layer were deleted and its
callers rebound to the level below, what would break other than imports? Do the two
interfaces speak in the same nouns, or has the vocabulary genuinely changed at this
boundary?
## Likely consequences
Call paths become shorter, interfaces earn their maintenance cost, and each remaining
layer provides a meaningful place for change. When layers are distinct, a new requirement
lands at one level and stops there. When they are not, every change ripples through the
full stack of pass-throughs, and the cost of navigation is paid on every read while the
benefit of abstraction is never collected.
## Exceptions
A deliberately transparent adapter, decorator, security boundary, or compatibility seam
may mirror an interface when isolation itself has concrete value and the extra hop remains
obvious. A stable published interface may forward to an internal one that is free to
change, since the forwarding is the point. In both cases the layer's purpose is isolation
rather than abstraction, and it should be named so a reader expects no translation.
## Positive example
A repository exposes a domain aggregate assembled from several storage rows, resolving
identity and ordering as it goes, while the application service above it exposes a
complete use-case result with its own success and rejection outcomes. Neither level
mentions the other's vocabulary: the service never sees rows, the repository never sees
use cases, and a change to the storage layout stops at the repository.
## Counterexample
A controller calls a service that calls a client, all three with the same method name,
parameters, and result type, and none performing validation, translation, policy, or
aggregation. When a new option is added to the client, all three signatures change
together, so the two upper layers cost three files of navigation and deliver nothing but
a longer stack trace.
## Related policies
See `prefer-deep-modules`, `keep-interfaces-simple`, `avoid-pass-through-parameters`, and
`apply-the-end-to-end-principle`.
