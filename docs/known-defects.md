# Known defects

Faults that are understood but not yet fixed, written down so the next person does not have
to find them again. Each one names the evidence it rests on and carries a status:

- **OPEN** — reproduced, still present in the code on this branch.
- **PARTLY FIXED** — the sharp edge is gone, something named below is not.

A fault that is fully fixed leaves this file, and so does one that turns out not to exist.
Everything here was re-verified against the code on 2026-08-22.

## OPEN — the one-review-one-sequence rule has no schema behind it

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

## OPEN — `next_revision()` reserves nothing

Minutes pass between `reviser.open` and `seal_case`. Two reviews of one case inside that
window both take the same number, and the loser dies with a genuine `CaseRevisionConflictError`
after a full round of judging has already been paid for. Reserve the row at `open`, or make
`seal` retry with a fresh number.

`ArchitectureCaseService.rescope` (`workflow/cases.py`) takes `latest + 1` through
`ArchitectureCase.revise()` — the same unreserved number `open` took — so re-scoping during a
live review makes `seal_case` die the same way, with a wider window.

## PARTLY FIXED — a round that could not be put into words is not distinguishable on screen

`generate_questions_node` catches every exception and returns no questions; so does the
per-finding loop inside `LangChainQuestionGenerator.generate`. Degrading is right — every
candidate has already been judged by then, and letting it propagate throws that away — but
"the review settled everything" and "the review has uncertainty it could not phrase" both
leave with no questions and both seal the case.

Half fixed: the two are now distinguishable **in the log**, at ERROR, naming how many held
findings went unasked. Nothing says so on a surface a reader sees, and a review that quietly
stopped short still reads as a review that finished.

## OPEN — a failed or cancelled execution reads as "already done"

`_resume_command` returns `None` for any execution that is not `awaiting_answers`, and
`resume_background` turns that into `202` with the existing run state. For a `failed` or
`cancelled` execution that is a 202 describing a run that will never do anything: the Answer
button can be pressed for ever, and only a client that reads `status` off the run body can
tell. A submission against a superseded *round* is now refused properly
(`ReviewSupersededError`, 409); a submission against a dead *run* is not.

## OPEN — indexing still happens inside the click, and the repository is parsed twice

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

## OPEN — nothing bounds a review's peak checkpoint size

Checkpoints are released the moment a review reaches an end and the space is handed back, so
the file no longer grows without bound. What is not bounded is the *peak*: LangGraph writes the
whole `ReviewState` at every superstep, and that state carries the atlas, the policy corpus and
every retrieved policy set. One review of a six-file example repository reaches about 86 MB
mid-flight before it is released. A repository of real size scales that by its atlas.

The peak is lower than when this was written and the entry's number predates the change: a
`Send` payload now carries three keys instead of the whole state, which took one round of six
candidates from 21 MB of `__pregel_tasks` to 1.3 MB (`workflow/graph.py:199`). That bounds the
fan-out, not the state each superstep writes, which is what this entry is about.

## PARTLY FIXED — `Label` still has two dozen hand-rolled copies

The drift is fixed — the five different tracking values are gone — but twenty-four
mono-variant copies of the recipe remain in `features/atlas/**`, `components/ui/select.tsx`,
`features/landing/specimen.tsx`, `ui/brand.tsx`, `features/landing/exhibit.tsx` and
`features/review/atlas-surface.tsx`. `ui/design-system.test.ts` carries this as an `it.todo`
so it stays visible.

## OPEN — dead surface that has not been removed yet

Route-plus-generated-types with no live caller, verified by grep over `frontend/src`,
`tests/`, `docs/` and the CLI. The last streaming endpoint has been removed; these remain,
because unlike that one they are plausible REST surface somebody may have meant to keep:

- `POST /api/cases/import-yaml`, `POST /api/cases`, `GET /api/cases/{case_id}`
- `GET /api/branches`, `GET /api/policies/{policy_id}`
- `GET /api/review-conversations/{id}` (and `reasoning/conversation.py:show` behind it)

`safe_workspace_output_path` (`repositories/safety.py`) is called from nowhere. It is a
symlink and path-traversal defence, so **confirm it was deliberately unwired rather than
accidentally orphaned** before removing it; everything else the audit found dead has gone.

`safe_workspace_output_path` is the last of the dead code; the duplicated helpers, the
duplicated ignored-directory list and the two protocols sharing the name `RepositoryAnalyzer`
have all been reduced to one definition each.

## OPEN — the concurrency setting reaches one path, and two providers' copies of it reach none

`ARCHCOMPASS_MODEL_CONCURRENT_REQUESTS` and `ProviderDefaults.concurrent_requests` read as
"how parallel this provider's judging is". They are not that.

`concurrent_requests` has exactly one reader — `SelectedLangChainJudge._judge_each`
(`reasoning/adapters/selected.py:255`) — reachable only from `judge_all` (`:206`), whose only
caller is the `review_candidates` node (`workflow/nodes.py:229`), which the graph enters only
when `judge.supports_batch()` (`workflow/graph.py:173`). `supports_batch` is false for every
provider but Google (`selected.py:185`). So for Ollama, Groq and Cerebras the graph takes the
per-candidate `Send` fan-out instead and this number is never consulted.

`OpenAICompatibleProvider.concurrent_requests = 4` (`reasoning/adapters/openai_compatible.py:79`)
is therefore dead for both vendors that use it. The variable itself is live, but only in the
Google-batch-refused fallback, where the descriptor's value is 1
(`reasoning/adapters/providers.py:244`) — so raising it is the only thing it can do.

Nothing is broken by this; a reader is. Either the name should say what it bounds, or the
concurrent path should be the one those providers actually take.

## OPEN — the documented retrieval gate cannot be run from a checkout

`archcompass retrieval evaluate --from <file>` (`presentation/cli/app.py:100`) declares
`exists=True` on its argument, and no reference-results file is committed anywhere in the
repository. The command is a maintainer's step over results they hold privately, which is a
legitimate design, but there is no fixture, no example and no schema doc — so the only way to
learn the file's shape is to read `RetrievalEvaluationFile` (`app.py:84`).

Unrelated to `make evaluation`, which is the notebook harness and does run.
