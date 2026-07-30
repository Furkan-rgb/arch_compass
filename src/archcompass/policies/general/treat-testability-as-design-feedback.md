---
id: treat-testability-as-design-feedback
title: Treat hard-to-test code as a design signal
scope: general
strength: guidance
tags: [testability, coupling, feedback]
source:
  author: ArchCompass
  inspiration: ["Steve Freeman & Nat Pryce, Growing Object-Oriented Software, Guided by Tests"]
description: >-
  Elaborate doubles, patched globals, and a required running environment are the
  test reporting coupling and undeclared dependencies. Change the design the
  test is complaining about instead of building heavier test machinery around it.
---
## Intent
Read difficulty in testing as a report about coupling and hidden dependencies, and correct
the design rather than the test.
## Guidance
When a unit cannot be exercised without elaborate setup, treat that setup as a
measurement. Each double a test must build corresponds to a dependency the unit reaches for
instead of receiving; each global or module-level value it must patch is a dependency the
design never declared; each running service it requires marks a boundary that was never
drawn. The correction usually belongs in the code under test — take the dependency as an
argument, separate the decision from the effect, narrow what the unit knows — not in a more
capable harness. Watch the shape of the tests as well as their difficulty: a test that
asserts on interactions rather than results is often describing an interface that returns
nothing worth checking, and a test that breaks whenever an unrelated detail changes is
reporting that the unit knows too much.
## Signals
A test's setup is longer than the code it exercises. Tests patch names inside the module
under test in order to control it. One behavior change breaks a dozen tests that were not
about that behavior. Tests assert that particular methods were called in a particular order
because the unit returns nothing else to assert on. The team maintains helper infrastructure
whose only purpose is to make one stubborn area reachable.
## Diagnostic questions
What is this setup telling us the unit depends on? Could this be tested with plain values
if the dependency were passed in instead of constructed inside? Are we writing a double
because the collaboration is genuinely complex, or because the seam is in the wrong place?
## Likely consequences
Designs corrected under testing pressure end up with explicit dependencies, smaller units,
and effects at the edges — the same properties that make them easy to change for reasons
that have nothing to do with testing. Teams that answer the pressure with heavier machinery
get a suite that is slow, brittle, and coupled to implementation, so it obstructs exactly
the refactoring that would have fixed the original problem.
## Exceptions
Some things are inherently hard to test and the difficulty is not the design's fault:
concurrency, real network behavior, and integration with an external system need real
infrastructure, and that is what integration tests exist for. Legacy code often needs
characterization tests with awkward scaffolding before it can be changed safely; the
scaffolding is a step, not a destination.
## Positive example
A settlement calculation could only be tested by standing up a data store, so the team
changed it to accept an account snapshot as an argument and return the resulting entries.
The tests became a table of inputs and expected entries, and the same change let the
calculation be re-run against historical data during an audit.
## Counterexample
A report generator constructs its own storage client, reads a module-level configuration
object, and stamps the current time internally. Its tests patch three module attributes and
freeze the clock, so when the storage client's constructor gains a parameter, forty tests
fail for reasons unrelated to reporting, and the team's response is a shared fixture that
patches all three by default.
## Related policies
See `keep-effects-at-the-edges`, `contain-dependencies`, `minimize-mutable-state`, and
`prefer-deep-modules`.
