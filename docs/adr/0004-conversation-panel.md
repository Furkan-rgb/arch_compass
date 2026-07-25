# ADR 0004 — A report-conversation panel in the web workspace

**Status:** Accepted
**Date:** 2026-07-25
**Amends:** master plan §18 (removes the conversation-UI non-goal)
**Related:** ADR 0003 (classifier-owned phrasing)

## Previous direction

Master plan §18 listed "a React report-conversation or generic chat frontend beyond the
existing local web workspace" as an explicit non-goal for V1.2, and `.agents/AGENTS.md`
stated "there is no conversation React UI in V1.2". Conversations were reachable only
through the CLI and the HTTP API.

The non-goal was written to stop the milestone sprawling into a general chat product
while the conversation contracts were still moving. Those contracts are now settled:
pinned identity, bounded retrieval, validated answers, and — since ADR 0003 — no turn
that fails because of how a question was phrased.

## New direction

The run detail page gains a conversation panel: start a conversation for the viewed
run, pick between existing ones, read history, and ask a question.

It is a **pure client of the existing routes** (`/api/conversations` create, list,
history, messages). No new backend path, no alternate domain flow, and no second way to
reach a conversation — the CLI and the panel call the same application service. That is
what keeps this a presentation change rather than a product expansion, and it is the
line the original non-goal was protecting.

The panel appears only for a finished, successful run, matching the service rule that a
conversation requires a validated report. Failed turns are surfaced as an alert rather
than swallowed, so a rejected question is visible rather than silently dropped.

## Why now rather than later

ADR 0003 removed the phrasing parser that turned ordinary wording into hard errors.
Before that, a panel would have exposed users to failures like "a comparison requires at
least two unambiguous finding references" for questions a person would consider
perfectly clear. A conversational surface is only reasonable once ordinary phrasing is
safe, which is why this follows that change rather than preceding it.

## Consequences

- Master plan §18 loses the conversation-UI non-goal; the V1.2 access bullet now names
  the web workspace alongside the CLI and API. `.agents/AGENTS.md` and
  `docs/report-conversations.md` are updated to match, so agent instructions no longer
  contradict the shipped UI.
- Still non-goals, and unchanged: a generic chat frontend, any conversational surface
  that is not pinned to one successful run, and any path by which a conversation could
  revise a case or recommendation.
- The panel renders the assistant's already-validated text rather than reformatting
  structured answers. Evidence citations are the service's output; presenting them
  differently would risk implying support the answer does not claim.
- The committed static bundle must be rebuilt with this change, and
  `make api-types-check` must stay green — conversation types now cross the API
  boundary into the frontend.
