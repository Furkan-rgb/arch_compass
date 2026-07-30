---
id: aggregate-error-handling
title: Handle failures at the boundary that can actually recover
scope: general
strength: guidance
tags: [errors, exceptions, recovery, boundaries]
source:
  author: ArchCompass
  inspiration: ["John Ousterhout, A Philosophy of Software Design (2nd ed.)"]
description: >-
  Let failures travel to the nearest layer that can retry, substitute, report, or
  abandon a unit of work, and handle many failure kinds there in one place. Error
  handling scattered across every intermediate layer multiplies code without
  multiplying the number of recoveries the system can actually perform.
---
## Intent
Stop error handling from being smeared across every intermediate layer, and concentrate it
where a layer holds enough context to choose a genuine response.
## Guidance
Let failures propagate to the nearest boundary that can retry, substitute, report, or abort
a unit of work, and handle many failure kinds once there; translate an error only where
crossing an ownership boundary changes its meaning. The test for a handler is authority,
not proximity: a layer should catch a failure only if it can decide something the layer
above could not decide better. Prefer one handler that copes with a family of failures over
a handler per failure type, since the recovery for a timeout, a refused connection, and a
malformed response is usually the same abandonment or retry. When a boundary does translate
an error, it should preserve the original cause rather than flatten it into a message, so
the layer that finally reports has the full chain. Code between the failure and its handler
should carry no error vocabulary at all beyond releasing what it owns.
## Signals
Intermediate layers catch, log, and rethrow the same failure, so one incident appears in
the log several times before anything acts on it. Callers receive sentinel values — null,
empty list, a boolean — that each caller must re-interpret against undocumented rules.
Functions have more lines devoted to failure paths than to the work they exist to do.
Exception types multiply until the handler at the top catches the base class anyway,
because no caller could keep the taxonomy straight. A stack trace arrives at the operator
already stripped of the frame where the failure originated.
## Diagnostic questions
What can this layer do about the failure that its caller could not do better? How many
places currently react to the same error, and does each one change the outcome? If this
catch block were deleted, would anything except the log output differ?
## Likely consequences
Handlers become fewer and more capable, each failure is reported once with its cause
intact, and intermediate code shrinks to the work it is named for. Recovery policy becomes
reviewable, because it lives in a small number of readable places rather than being an
emergent property of dozens of catch blocks. Systems that spread handling instead accrue
failure paths nobody tests, and the paths that are exercised most often are the ones that
swallow information.
## Exceptions
A layer holding resources may catch to release or annotate and rethrow, since the cleanup
obligation is genuinely local. Masking a failure through a bounded retry is valid when it
makes the failure invisible to everyone above, meaning the caller cannot observe that it
happened. A trust boundary that must not leak internal detail outward translates
deliberately, and that translation is handling, not smearing.
## Positive example
A job runner catches all task failures in its scheduling loop, marks the run failed with
the task identity and the original cause, and decides whether the task is eligible for
another attempt. The tasks themselves contain no error handling: they open resources with
scoped cleanup and let anything unexpected escape, so each task body reads as the work it
performs.
## Counterexample
Every service method wraps its body in a catch block that logs the exception and returns
nothing. A failing storage call is therefore reported four times on the way up, each time
with less context, and the request handler receives an empty result it cannot distinguish
from a legitimate absence — so it returns a success response for a request that failed.
## Related policies
See `eliminate-errors-by-design`, `pull-complexity-downward`, `keep-interfaces-simple`, and
`validate-at-trust-boundaries`.
