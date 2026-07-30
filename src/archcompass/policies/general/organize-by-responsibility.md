---
id: organize-by-responsibility
title: Organize by responsibility rather than temporal sequence
scope: general
strength: guidance
tags: [temporal-decomposition, cohesion, ownership]
source:
  author: ArchCompass
  inspiration:
    - "John Ousterhout, temporal decomposition"
    - "David Parnas, information hiding"
description: >-
  Group code by the knowledge it owns, not by when it runs. Modules named after
  phases of execution collect unrelated rules and force every feature to be
  spread across the timeline instead of held in one place.
---
## Intent
Avoid modules that are merely named after when code runs, so that each module is defined
by the knowledge it owns rather than by its position in a sequence.
## Guidance
Place each step with the owner of its knowledge, and let a workflow coordinate those
owners rather than reimplement their rules. Execution order is a fact about one run; it is
a poor basis for a boundary, because the things that happen at the same time usually have
nothing else in common. When a module's name answers "when", ask what it would be called
if it had to answer "what does this know". Sequencing itself is a legitimate
responsibility: a pipeline or workflow object may own the order in which steps run, so
long as it knows only enough about each step to invoke it and to react to its outcome.
## Signals
Modules named `before`, `during`, or `after` mix unrelated validation, provider, and
persistence rules. One feature's logic is scattered across every phase module, so
understanding it means reading the whole timeline. A phase module imports the internals of
several domains and its tests need most of the system stood up. Adding any feature means
editing every phase, whether or not the feature has anything to do at that phase.
## Diagnostic questions
What invariant or knowledge makes the code in this module belong together? If the order of
steps changed tomorrow, would this module still make sense, or would it have to be
redrawn? Could a maintainer describe this module without using the words first, then, or
finally?
## Likely consequences
Responsibilities remain cohesive even when workflow order changes, and a rule can be found
by asking who owns it rather than by tracing an execution path. Temporal decomposition
produces the opposite: knowledge about one subject is smeared across phases, duplicated
where phases need it twice, and drifts out of agreement between them.
## Exceptions
A workflow or pipeline object may explicitly own sequencing without owning every step's
details; that is a real responsibility, not a phase name. Startup and shutdown sequences
are also genuinely temporal, because ordering constraints are the substance of what they
manage.
## Positive example
Preflight coordinates provider validation rather than reimplementing provider capability
rules. Each provider adapter answers whether it can serve a request and why not, and
preflight only aggregates those answers, so a new capability rule changes one adapter and
nothing in the workflow.
## Counterexample
Every execution phase becomes a layer that all features must modify. A single new field
requires an edit to the request phase, the processing phase, and the reporting phase, and
no module can state the rules for that field on its own.
## Related policies
See `assign-clear-ownership`, `pull-complexity-downward`, and
`split-or-join-by-shared-knowledge`. A module that resists a crisp name is often
temporally decomposed; see `name-for-meaning`.
