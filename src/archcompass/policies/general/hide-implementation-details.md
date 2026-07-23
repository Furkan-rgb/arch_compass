---
id: hide-implementation-details
title: Hide implementation details behind the owning boundary
scope: general
strength: guidance
tags: [information-hiding, dependencies, ownership]
source:
  author: ArchCompass
  inspiration: [software-design literature]
---
## Intent
Prevent callers from depending on decisions that belong to another module.
## Guidance
Expose the capability a caller needs while keeping formats, provider rules, and algorithms private.
## Signals
Several callers reproduce the same internal rule or inspect an implementation-specific type.
## Diagnostic questions
Which decisions can the module change without coordinating with callers?
## Likely consequences
Callers become simpler and implementation changes affect fewer locations.
## Exceptions
Transparent data types are appropriate when their representation is the stable shared concept.
## Positive example
A provider returns a voice catalog without exposing how its built-in voices are discovered.
## Counterexample
A wrapper forwards every provider option and therefore hides nothing.
## Related policies
See `assign-clear-ownership` and `contain-dependencies`.
