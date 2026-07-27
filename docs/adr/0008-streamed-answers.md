# ADR 0008 — A streamed answer is a second transport, not a second flow

**Status:** Accepted
**Date:** 2026-07-27
**Amends:** ADR 0004 (the conversation panel — the "no new backend path" clause)
**Related:** ADR 0001 (composed synthesis), ADR 0006 (review-centred workspace), master plan
§12.0 (nothing the model writes is a key), §16 (the review-centred workspace), §18 (no job
queue)

## Previous direction

ADR 0004 gave the workspace a conversation panel and drew a hard line around it: the panel is
"a pure client of the existing routes. No new backend path, no alternate domain flow, and no
second way to reach a conversation." That line was protecting a specific thing — the V1.2
non-goal it amended existed to stop the milestone sprawling into a general chat product, and a
panel with its own backend path is how that sprawl starts.

The consequence was that a question took as long as a full answer to show anything. The
answering stage reads the whole review, the whole method primer and the whole policy corpus,
and produces considered prose; against a local model that is tens of seconds during which the
page says "Thinking…" and a reader cannot tell a slow answer from a hung one.

The same problem was already solved once, elsewhere. Workspace design step 4 gave the review
run `POST /api/reviews/stream` beside `POST /api/reviews`, because per-boundary progress
"replacing the notice line and reload" needed the run to be watchable while it happened.

## New direction

The conversation gains `POST /api/review-conversations/{id}/messages/stream`, in the same
NDJSON form: any number of `prose` lines carrying fragments to append, then exactly one
`answered` line carrying the appended message, or one `failed` line if the turn could not be
attempted at all.

This is a second **transport** for one turn, and ADR 0004's clause is read as forbidding a
second **flow**:

- The same application call appends the same message. `ReviewConversationService.ask` gained an
  optional `on_prose` callback, not a sibling method — one code path, one validation, one
  append, whether or not anyone is watching.
- Nothing streamed is a record. Fragments are prose on its way to being checked. The answer
  that gets stored is the one this stage validates whole, after generation, and grounding is
  still derived from positional flags that do not exist until the last token has arrived — so a
  fragment can never carry a citation (§12.0).
- No second way to reach a conversation. Both routes reach the same service; the CLI and the
  non-streaming route are unchanged and still correct.

Streaming is a **capability of the provider**, asked rather than configured. A transport that
can stream implements `StreamingChatTransport.stream`; one that cannot omits it, and
`isinstance` decides. The same pattern repeats one level up as `StreamingAnswerReasoner`. A
workspace pointed at a provider that cannot stream answers the question anyway, after the last
token instead of during, and nothing above the port has to know which happened. That is why
there is no capability endpoint to query first: there is nothing a client would do differently.

**Ollama only, for now.** The `ollama` client already streams: `chat(stream=True)` returns an
iterator of chat responses, so the transport's `stream` is a pass-through that hands their text
on in order and adds nothing. Gemini can stream too and is deliberately left out of this
change; adding it is one method on `GoogleChatTransport` whenever it is wanted, and until then
a Google workspace answers questions exactly as it does today. That the capability is asked
rather than configured is what makes leaving it out cost nothing.

A streamed request is not retried. `complete` keeps the transport's transient-failure retry
because nothing has been shown when it fires; a stream that failed part-way has already put
text on the page, and a second attempt would repeat it.

Reading a growing structured reply needs one new deterministic piece — `prose_prefix`, which
finds a named string field in an incomplete JSON document and decodes what has arrived. It
hands escapes back to the JSON decoder rather than reimplementing them, and it returns nothing
rather than a guess. It depends on the answer field being declared before its grounding flags,
which `ProposedReviewAnswer` already did for an unrelated reason (§12.0, field order): the
prose has to be written before the model picks what it rests on.

## Why the repair round is not streamed

One constrained repair round is the only second attempt at content. It rewrites a reply that
failed validation, which means it is a *replacement* rather than a continuation, and there is
no honest way to narrate a replacement as a stream of fragments — a reader part-way through one
answer would watch it change underneath them with no way to tell which they had read. So the
first attempt streams, the repair lands whole, and the returned answer is authoritative over
anything a reader saw.

This is also why the callback contract says fragments are provisional. A caller must render the
returned message, not the accumulated text.

## Consequences

- `SUMMARISE_REVIEW` moves to v4, for a related defect found at the same time: at v3 both the
  contract and the run-specific arity note said "every statement carries one supported_by
  flag", of four fields, two of which are prose. A live run answered `situation` with
  `{"statement": ..., "supported_by": [...]}` serialised into the string, and a JSON document
  is a valid string, so it validated, persisted, and printed verbatim as the conclusion.
  Prose fields are now named as prose, and `_prose_defects` refuses a prose field that parses
  as a JSON document — routed through the one sanctioned repair round, and failing the review
  rather than storing a document in a record that is immutable once written.
- `AnswerProgress` is a declared contract in the OpenAPI document, discriminated by `event`,
  as `ReviewProgress` is. `make api-types` follows.
- Still non-goals, and unchanged: a generic chat frontend, any conversational surface not
  pinned to one successful review, any path by which a conversation could revise a case or a
  review, and any job queue — the stream lives exactly as long as its request, in a thread,
  like the review stream.
- A turn that emits fragments and then fails is still appended as a failed message. What a
  reader saw does not promote itself into the history.
