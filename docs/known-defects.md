# Known defects

Faults that are understood but not yet fixed, written down so the next person does not have
to find them again. Each one names the evidence it rests on. A fault that has been fixed
leaves this file; a fault that turns out not to exist leaves it too, with a note saying so.

## An answer submitted twice destroys the case

**Confirmed against a real workspace on 2026-08-22.** Reported as "answering the questions
results in a conflicted version of the case", and blamed on a Gemini timeout. The shape of
the report is right. The timeout is not the cause.

### What it looks like on disk

For case `case_be455c98…` in the development workspace, `core_review_snapshots` holds three
rows at sequence 1:

| review | round | status | points at case revision |
| --- | --- | --- | --- |
| `review_aadbede0` | 1 | `awaiting_answers` | 1 |
| `review_d0464fe5` | 2 | `awaiting_answers` | 2 |
| `review_f260108c` | 2 | `failed` | 2 |

`core_case_snapshots` for that case holds **revision 1, with zero answers, and nothing else**.
Two reviews point at a revision that was never written. The five answers a person typed
survive only inside review blobs and the LangGraph checkpoint; the case, which is the durable
record and the thing every later review is judged against, has none of them. Opening revision
2 answers 404.

### How it happens

`api.answerRun` passes no timeout, so it inherits `READ_TIMEOUT_MS = 30_000` from
`frontend/src/api.ts`. That POST is not cheap — `_resume_command` decodes the whole review
and `_describe_run` decodes it a second time only to read `.sequence`, and the review blob in
this workspace is 2.37 MB. The request aborted, `resume.isPending` went false, the button
re-enabled with the answers still in component state, and a second identical POST went out
sixteen seconds later. By then the first attempt had succeeded, opened round 2, and written
its waiting snapshot.

Nothing refused the second one. `_resume_command` in `workflow/service.py` asks two questions,
and both of them answer yes for a superseded review:

* the execution row says `awaiting_answers` — true, but it is round 2 that is waiting;
* `self._reviews.get(review_id).status` says `awaiting_answers` — and always will, because a
  review snapshot is immutable. Round 1's snapshot says it for ever.

So round 1's answers resumed round 2's interrupt. `case.with_answers` found five equivalence
keys it already held and raised, and `_record_failure` recorded a failed review naming case
revision 2 — a revision `seal_case` never got to write.

Then it goes quiet. The execution row now reads `failed`, so `_resume_command` returns `None`,
`resume_background` hands back the old run state, and the route answers **202 with a failed
run**. The Answer button can be pressed for ever. Nothing happens and nothing says so.

### The repair

The one guard that closes it: compare the posted `review_id` against
`executions.current_review_id(thread_id)` and refuse with a 409 when they differ. A superseded
review id is a conflict, not a repeat, and it is the only thing that distinguishes the two.

Worth doing alongside, in this order:

1. `_record_failure` files a review naming an unwritten case revision. This happens on *every*
   failed round, not only this one. Seal the opened revision before recording the failure, or
   record `previous_case` on the failed snapshot.
2. A `failed` or `cancelled` execution must raise rather than return a stale run. "Not awaiting
   answers" is currently read as "already done", which is what makes the dead button silent.
3. Give `answerRun` `NO_TIMEOUT`, like the other calls that start work, and stop
   `_describe_run` decoding a multi-megabyte review to read one integer.

## The one-review-one-sequence rule has no schema behind it

Migration `003_one_revision_per_review.sql` rebuilt `core_review_snapshots` without the old
`UNIQUE(repository_id, branch_id, sequence)` and put nothing in its place. The table's only
constraint is `review_id PRIMARY KEY`, and `SQLiteCoreReviewRepository.record` defeats even
that with `ON CONFLICT(review_id) DO NOTHING` followed by a read of whatever row is there.

Review ids are `stable_id` over branch, atlas, case, revision, round and status, so two
reviews of an unchanged repository compose the *same* id — and the second silently receives
the first one's findings. `executions.bind` then sets `current_review_id` to an id another row
already holds, which raises an uncaught `IntegrityError` against
`UNIQUE(current_review_id)`.

Nothing anywhere checks that a review's `case.revision` exists in `core_case_snapshots`.

## `next_revision()` reserves nothing

Minutes pass between `reviser.open` and `seal_case`. Two reviews of one case inside that
window both take the same number, and the loser dies with a genuine `CaseRevisionConflictError`
after a full round of judging has already been paid for. Reserve the row at `open`, or make
`seal` retry with a fresh number.

## A question-generation timeout ends the round silently

`generate_questions_node` catches every exception and returns no questions. A model timeout
there does not fail the run — it ends the clarification loop and seals the case, and the
reader sees a review that simply stopped asking. Whatever the right behaviour is, it should be
distinguishable from "there was nothing to ask".

## The checkpoint database grows without bound

`.archcompass/review-checkpoints.db` reached **56 GB**, with a 260 MB WAL, on a development
machine. Individual checkpoint writes are 8–78 MB. This is its own problem and it feeds the
one above: those writes are what made a 30-second POST miss its deadline. Nothing prunes
checkpoints for reviews that have reached a terminal state.

## Indexing still happens inside the click

`POST /api/repositories/start` calls `repository_service.index(...)` before it answers, so the
longest wait in the product has no stage, no progress and no cancel. `start-page.tsx` labels
the two phases honestly as a stopgap.

It cannot simply move into the graph: `review_executions` has `repository_id`, `branch_id` and
`case_id` all `NOT NULL`, the row is written before the thread starts because the 202 response
describes it immediately, both ids come out of indexing, and the case is chosen from
`version.branch_id`. Moving it means nullable execution columns, a migration, case creation
ahead of `load_context` — whose whole job is to load a case by id — and a run page rendering
with no repository name or sequence for exactly the interval the change exists to make visible.

There is a better version of it next door. **The repository is parsed twice per review today**:
`/start` builds and persists an atlas, and then the graph's `analyze_repository` node parses
the same root under the same scope again and keeps the result only in graph state. Resolve the
lineage from git alone — `resolve_repository_lineage` needs only the root commit and the
canonical root, `resolve_branch_lineage` only the branch name, and `GitCommandLineClient`
already reads both — and move the *atlas build* into the graph as a new first node. All three
ids stay available at `_begin`, so the execution row, the run listing, the sequence and the run
page are untouched; no migration is needed; parsing becomes the run's first visible,
cancellable stage; and a whole parse is removed rather than relocated.

## `Label` still has twenty-two hand-rolled copies

The drift is fixed — the five different tracking values are gone — but roughly twenty-two
mono-variant copies of the recipe remain in `features/atlas/**`, `components/ui/select.tsx`
and `features/landing/specimen.tsx`. `ui/design-system.test.ts` carries this as an `it.todo`
so it stays visible.
