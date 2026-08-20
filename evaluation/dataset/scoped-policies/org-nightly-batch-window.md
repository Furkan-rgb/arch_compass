---
id: org-nightly-batch-window
title: Finish every nightly batch inside the maintenance window
scope: organisation
applies_to: globex-platform
strength: required
tags: [batch, operations, scheduling]
source:
  author: Globex Platform
  inspiration: [evaluation fixture]
description: >-
  Batch work runs between 01:00 and 04:00 and must be finished or safely abandoned by the
  end of that window. A job still running at 04:00 competes with the trading day.
---
## Intent
Keep overnight work off the critical path of the business day by making the window a
designed limit rather than an observed average.
## Guidance
Every batch declares a deadline and a behaviour at that deadline: finish, checkpoint and
resume tomorrow, or abandon and alert. Work that cannot state which of the three it does is
not scheduled. Runtime is measured per run and trended, so growth is seen before it
overruns rather than on the night it does.
## Signals
A job's runtime has no recorded trend. A batch has run past 04:00 more than once and the
response was to start it earlier. Two batches were moved into the same hour without anyone
comparing their durations.
## Diagnostic questions
What happens if this job is still running at 04:00? Who is told, and what state is the data
left in? How much has this job's runtime grown in a year?
## Likely consequences
Overnight work stays overnight, and growth surfaces as a trend rather than as an incident.
Without a declared deadline, the first sign is a slow trading morning.
## Exceptions
A recovery run after an incident may exceed the window with an incident commander's
approval, which is recorded on the incident.
## Positive example
The reconciliation job checkpoints every ten thousand rows, stops at 03:45, and resumes
from its checkpoint the following night, alerting when it has not caught up in three runs.
## Counterexample
The digest job has no deadline. It finished at 04:20 twice this quarter, and the response
both times was to move its start time earlier.
## Related policies
bound-queues-and-buffers, design-in-observability, migrate-incrementally
