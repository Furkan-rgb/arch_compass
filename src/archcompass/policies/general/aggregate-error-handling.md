---
id: aggregate-error-handling
title: Handle failures at the boundary that can actually recover
scope: general
strength: guidance
tags: [errors, exceptions, recovery, boundaries]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
---
## Intent
Stop error handling from being smeared across every intermediate layer.
## Guidance
Let failures propagate to the nearest boundary that can retry, substitute, report, or abort a unit of work, and handle many failure kinds once there; translate an error only where crossing an ownership boundary changes its meaning.
## Signals
Intermediate layers catch, log, and rethrow the same failure; callers receive sentinel values each must re-interpret; or one failure appears several times in the logs before anything acts on it.
## Diagnostic questions
What can this layer do about the failure that its caller could not do better, and how many places currently react to the same error?
## Likely consequences
Handlers become fewer and more capable, each failure is reported once with its cause intact, and intermediate code shrinks.
## Exceptions
A layer holding resources may catch to release or annotate and rethrow, and masking a failure locally through a retry is valid when it makes the failure invisible to everyone above.
## Positive example
A job runner catches all task failures in its scheduling loop, marks the run failed, and logs once with the task identity, while tasks themselves do not catch.
## Counterexample
Every service method wraps its body in a catch block that logs and returns none, so the cause is reported four times and lost before reaching the API layer.
## Related policies
See `eliminate-errors-by-design`, `pull-complexity-downward`, and `keep-interfaces-simple`.
