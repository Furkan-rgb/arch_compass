---
id: different-layer-different-abstraction
title: Give each layer a distinct abstraction
scope: general
strength: guidance
tags: [layers, abstraction, pass-through, complexity]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Ensure that an additional layer hides, translates, or consolidates complexity instead of merely adding another name and call hop.
## Guidance
Make each layer express concepts appropriate to its responsibility. A layer should aggregate operations, enforce invariants, translate representations, or otherwise provide a simpler view than the layer below it; collapse layers that only repeat another interface.
## Signals
Methods mostly forward the same arguments to similarly named methods and return the same result, or adjacent interfaces expose nearly identical concepts and sequencing.
## Diagnostic questions
What knowledge or decision does this layer hide, and could its caller use the lower-level interface with essentially the same understanding?
## Likely consequences
Call paths become shorter, interfaces earn their maintenance cost, and each remaining layer provides a meaningful place for change.
## Exceptions
A deliberately transparent adapter, decorator, security boundary, or compatibility seam may mirror an interface when isolation itself has concrete value and the extra hop remains obvious.
## Positive example
A repository exposes a domain aggregate assembled from storage rows, while the application service exposes a complete use-case result rather than forwarding row-oriented operations.
## Counterexample
A controller calls a service that calls a client with the same method name, parameters, and result, with no validation, translation, policy, or aggregation at either boundary.
## Related policies
See `prefer-deep-modules`, `keep-interfaces-simple`, and `contain-dependencies`.
