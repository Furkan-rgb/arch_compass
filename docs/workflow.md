# Review workflow

The canonical description of how a review executes. `workflow/graph.py` is the source of
truth; this document is what it means. For the concepts behind it read
[architecture.md](architecture.md); for the knobs around it, [operations.md](operations.md).

```text
START
  -> load_context
  -> analyze_repository
  -> detect_candidates
  -> calculate_delta
  -> select_initial_candidates
  -> load_policy_corpus
  |
  `- dispatch ------------------------------------------------.
       |  nothing selected            -> generate_questions    |
       |  otherwise, one Send each    -> review_candidate      |
       |                                                       |
       |   review_candidate (subgraph, once per candidate)      |
       |     START -> retrieve_policy_set -> judge_candidate -> END
       |                                                       |
       `- review_candidate ------------------------------------'
                                |
  -> investigate_hinges         (look up what the repository says about anything held)
  -> rejudge_investigated       (put what was found back to the same judge)
  -> generate_questions
       |
       `- settled / CI / round >= 3 / stop requested
       |    -> seal_case
       |    -> write_final_synopsis -> compose_final_review -> record_review -> END
       |
       `- questions to ask
            -> write_waiting_synopsis
            -> compose_waiting_review
            -> record_waiting_review
            -> await_answers                       (interrupt)
            -> revise_case
            |    `- stop requested -> seal_case -> ... -> END
            -> select_candidates_for_rejudgement
            `- dispatch (the same closure) -> review_candidate
                 -> investigate_hinges -> rejudge_investigated -> generate_questions
```

After the first review, `select_initial_candidates` sends only the changed and the new to a
model; a finding for an unchanged candidate is carried out of the previous review untouched,
and a review of a branch where nothing moved raises `NothingToReviewError` instead of being
charged for.

Candidate work is exposed to LangGraph through `Send`; no node hides a thread pool or a
private orchestration loop. Retrieval and judgement are separate nodes in a visible
candidate subgraph, so a reader can see that a candidate is judged against policies chosen
for it rather than against the whole corpus.

Every selected candidate is dispatched at once, and how many of them reach a model at once is
a separate question with a separate answer. The graph is as wide as the review; the provider
is as wide as it says it is, through `ProviderDefaults.max_parallel_requests`, and the gate
that spends that number lives in `SelectedLangChainChatModel`. The two are apart on purpose.
A bound in the graph would be a bound on the fan-out — which is a description of the work,
and the same on every provider — and it would sit in the executor LangGraph also runs its
checkpoint writes through, where a width of one can deadlock. A bound at the transport is a
statement about who is listening, which is what actually varies: a hosted API answers in
parallel, and a local runner with one slot queues everything past the first request until
their deadlines run out. See "What bounds a review, and what does not" in
[operations.md](operations.md) for what that cost when nothing said it.

## Judging a candidate

`retrieve_policy_set` selects policies for one candidate — see
[policy-retrieval.md](policy-retrieval.md) — and `judge_candidate` puts the candidate, the
case and those policies to `ArchitectureJudge`.

The judge returns one verdict by name: **`material`**, **`cleared`** or **`held`**. It is
chosen, not inferred: the model emits the word, the application does not read it out of the
reasoning. `held` carries a *hinge* — the single fact the verdict turns on — and `material`
and `cleared` may not carry one, because they are answers rather than questions.

`ArchitectureJudge` is the only component in the system that produces a verdict.

## The hinge investigation

A hinge stops the review to ask a person, and many hinges are questions the repository can
answer for itself. So `investigate_hinges` gives each held finding a bounded, recorded pass
of read-only lookups over the atlas the review analysed and the source at the revision that
produced it.

The edge is unconditional, so the pass also runs where nobody will be asked anything — a CI
run, and the third round, which seals. There it is not saving an interruption; it is
improving the verdict a review ends on, which is the other half of what it is for.

"The source at the revision" has one fallback. `read_code` asks git for the file at the
atlas's commit; where there is no revision to read — an unversioned directory, or a commit
git no longer holds — it reads the working tree instead, and only after a freshness check
confirms the tree still is what was judged.

**It establishes facts and decides nothing.** It returns a `RecordedInvestigation` — every
lookup, its arguments and the exact answer — and writes no findings at all. It is shown
which policies the judgement said the candidate bears on, by title and strength, so it knows
what the question is about; it is never shown the policy list, so there is no identifier it
could cite and nothing to validate.

`rejudge_investigated` then puts that record back to the **same judge**, with the same
candidate, the same case and the same retrieved policies. Nothing about the question changed,
so nothing is retrieved again. A candidate is re-judged only if it has a record, that record
has at least one lookup, and **this round** retrieved for it — so an investigation that was
withheld, or that could not ask anything, leaves the judge with exactly the inputs it had the
first time, and the finding it already reached stands.

The round condition is the load-bearing one. `investigations` is a merged mapping that
accumulates across rounds and is never cleared, so reading all of it re-judged candidates the
current round had already settled, against a record from before the answers arrived, and
stamped the result with that older record's identity. Scoping to `selected_candidates` and to
this round's retrievals is what stops that.

The judge sees three named blocks and they are three kinds of thing:

| block | whose choice | becomes |
|---|---|---|
| `CASE` | a person's | architectural intent |
| `CANDIDATE` | the detector's | `Finding.evidence` |
| `OBSERVATIONS` | the model's | `RecordedInvestigation`, never evidence |

The observations block is rendered by the application from `(tool, arguments, result)` — not
from the investigating model's prose, which would put an interpretation between the
repository and the verdict. It says out loud that a model chose these and that they are not
evidence, and it says when an investigation was cut short, because "the repository is silent"
and "we stopped asking" are opposite facts about a hinge.

A hinge nothing could settle reaches `generate_questions` unchanged and is put to a person.
That is a correct outcome, not a failure: the goal is to avoid *unnecessary* questions.

### The toolbox

Five lookups, over the pinned atlas and the reviewed revision:

| tool | takes |
|---|---|
| `search_code` | `name` — free text, for when the exact name is not known |
| `describe_code` | `qualified_name` |
| `related_code` | `qualified_name`, `relation` ∈ direct_dependencies · direct_dependants · known_callers · implementations · related_tests |
| `read_code` | `qualified_name` |
| `flagged_signals` | `codes` (optional) |

Names are resolved by the application against that atlas and no other: exact, unique, or
refused. Never a close match, never the first of several, never a node from a rebuilt atlas.
An ambiguous name is reported with its choices and settled by an optional `kind`. The model
never sees an atlas node id.

### Guards

Four bounds, each with one job, and the reason an investigation stopped is recorded on it:

| guard | value | bounds |
|---|---|---|
| `MAX_INVESTIGATION_LOOKUPS` | 12 | what may be explored — the primary budget |
| `MAX_INVESTIGATION_TURNS` | 12 | a loop that will not terminate |
| `MAX_INVESTIGATION_CHARACTERS` | 12,000 | an abnormal run, not a long one |
| wall clock | the transport's | the outer operational guard |

`MAX_INVESTIGATED_FINDINGS` (8) caps how many hinges one round investigates.

One answer is bounded too, before the budget ever sees it: 25 rows a result, 2,500 characters
a result, 80 lines from `read_code`, 10 signal codes a request. So the character budget above
is a guard against an abnormal run rather than the thing that trims a normal one.

`Termination` records which fired: `NATURAL_END`, `MODEL_CALL_LIMIT`, `LOOKUP_LIMIT`,
`INVESTIGATION_SIZE_LIMIT`, `PROVIDER_ERROR`. `NATURAL_END` says the model stopped asking —
it claims nothing about whether the search was sufficient. `None` means only that the reason
was not recorded, which is true of reviews stored before the field existed and of nothing
else; it is never read as a natural end.

## Clarification and rejudgement

When a round has questions, an immutable `awaiting_answers` review is composed and recorded
**before** the graph interrupts, so the snapshot a reader is holding exists whether or not
anybody answers. `await_answers` then interrupts; the client resumes the same LangGraph
thread with the answers.

`revise_case` records them on the case and opens a revision if this review has not opened one
yet. One review keeps **one** case revision however many rounds it asks — the revision moves
when a review opens it, not when a round happens — and `seal_case` is the only thing that
writes it, at the end, so a review that asked and was never answered leaves no revision
behind.

`select_candidates_for_rejudgement` validates that the case genuinely continues the previous
one — same case, earlier answers unchanged, at least one new answer — and selects every
candidate. An answer is about intent, and intent bears on all of them rather than only on the
ones whose question mentioned it.

A snapshot's `status` says what was true when it was recorded, and a client deciding whether
to offer an answer form needs what is true now. Those are different questions on an immutable
record: the copy that asked says `awaiting_answers` for ever, so a page reading it kept the
form up after the round had been answered and was being judged, and submitting it did nothing
— `_resume_command` refuses a submission written against a superseded snapshot, and `cancel`
refuses to stop a round nobody is looking at. `ReviewResponse.answerable` is those same two
checks asked in advance: the round is open, and this snapshot is the one it is open on. The
rail follows the same rule from the other side — one entry per revision, so a run continuing
a revision is that revision's row saying what it is doing rather than a second row under its
number.

`ReviewResponse.superseded_by` is the other half of it, and `answerable` cannot carry it: a
finished review and a superseded snapshot both answer `false` to "can this be answered" while
needing opposite things said about them — one is the review, the other is history with a
successor to read. It is the execution's current snapshot wherever that is not this one,
which is the right answer for a run mid-flight and for one that has finished alike.
`superseded_by_status` travels with it and is a fact about the *review* rather than about the
round the record asked: it is the status of the record the execution now stands on, so for
round one of a review cancelled at round two it says `cancelled` about a round that was
answered. Anything talking about a round has to say where to look rather than infer from it.

Every answer records the case revision it was recorded on, stamped by `ArchitectureCase.with_answers`
rather than supplied — a caller building an `Answer` from a question and a submission cannot
know which revision is open. With `Question.round` it addresses a round exactly: a review
keeps one revision however many rounds it asks, so `round` is unique inside a review and
repeats across the life of a case, and grouping a case's history on it alone would fold two
different conversations into one.

At most **two** interrupts: `round >= 3` seals. `MAX_ASKED_HINGES` (8) caps how many held
findings a round asks about, which is a different number from the eight it investigates and
is there for a different reason: nine questions in a form is a form nobody finishes. Hinges
past the cap are not lost — they stay held and the next round asks them. A question already
asked is not asked again, on an equivalence key over its facet and candidates, and a hinge
the model could not phrase is counted and logged rather than silently dropped.

## Checkpoints and reviews

Two stores, and they are never the same record.

**LangGraph checkpoints** are execution durability: the thread, its state, and the interrupt
it is parked on, in `review-checkpoints.db`. They exist so a resume continues the same
attempt rather than starting a new one, and they are released when a review reaches an end.

**Reviews** are product history: immutable snapshots in the workspace database, sequenced
**per branch** — a review of a different case continues the branch's number line rather than
starting one — each naming the one before it. Every snapshot of a single review shares its
number, and `round` separates them. A checkpoint id is never a review id; the execution store
maps between them.

A run's *stage* is held in memory and is worth nothing after the process that ran it. The
durable status — running, awaiting answers, completed, failed, cancelled — is the execution
store's, and it survives a restart. A watcher asking about a run this process did not start
is told the honest status with no stage list, rather than a progress bar that claims to be
live and is not.
