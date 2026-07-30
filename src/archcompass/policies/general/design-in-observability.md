---
id: design-in-observability
title: Design systems to explain themselves in production
scope: general
strength: guidance
tags: [observability, operations, debugging]
source:
  author: ArchCompass
  inspiration: ["Michael Nygard, Release It!", "operational practice"]
description: >-
  Being able to answer what a system is doing and why is a designed property:
  correlation across boundaries, meaningful state exposed, events at decision points. A
  component that cannot be inspected while it runs is not finished.
---
## Intent
Make the questions asked during an incident answerable from outside the process, without
attaching a debugger or shipping new code to find out what happened.
## Guidance
Decide how a component will explain itself at the same time you decide its interfaces,
not during the first outage. Give every unit of work an identifier that travels with it
across each boundary it crosses, so one request's path can be reconstructed end to end.
Emit events at decision points — which branch was taken, on which input, with which
answer from which dependency — rather than at function entry and exit, where the volume
is high and the information is low. Expose the state an operator will ask about: queue
depths, the configuration actually in effect, component versions, and the position of
long-running work. Make a health check name the dependency that is failing instead of
returning a boolean. Prefer a small number of structured facts with stable field names
over free text; the test is whether a question can be answered by a query rather than by
reading.
## Signals
Diagnosing an incident requires adding log lines and redeploying. Logs record that a
function ran but not the value its decision turned on. A request cannot be followed across
a service boundary because no identifier survives the hop. The effective configuration
cannot be read from a running instance, only inferred from files and deployment history.
A health endpoint reports healthy while the component is unable to do any work. The only
way to see what a background job is doing is to query the table it eventually writes.
## Diagnostic questions
If this behaved wrongly for one user yesterday, what would you query today to find out
why? Can you tell from outside the process which branch of this decision was taken, and
on what input? Which piece of internal state, had it been exposed, would have shortened
the last incident?
## Likely consequences
Systems that explain themselves are debugged from evidence, so incidents end with a cause
rather than a restart, and the second occurrence of the same failure is recognized in
minutes. Systems that do not are debugged by hypothesis and redeployment, which is slow
when it works and misleading when it does not, and the information that turns out to be
missing is usually exactly what would have revealed a rare failure. Designing this in also
improves the code: a decision point that is hard to describe in one event is usually a
decision point doing several things.
## Exceptions
Confidential data should not be exposed merely because it would help debugging; record a
stable reference or a redacted form and keep the correlation without the content. On a
genuinely hot path, full instrumentation can cost more than it returns, in which case
sample deliberately and record the sampling rate rather than removing the instrumentation
altogether.
## Positive example
A document-processing pipeline attaches a job identifier at intake and carries it through
extraction, review, and storage, emitting one structured event per stage with the outcome
and the rule that produced it. When a document is rejected, an operator queries the
identifier and sees which stage refused it and why, without shell access to any machine.
## Counterexample
A pricing component logs one line, calculation complete, at the end of each request. A
customer reports a wrong price, nobody can determine which rules matched, and the team
reproduces the request in a test environment with guessed inputs before finally shipping a
temporary build with extra logging to production in the hope of catching it again.
## Related policies
See `make-relationships-discoverable`, `design-for-partial-failure`, and
`record-design-rationale`.
