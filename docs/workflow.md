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
       |  batch judge available       -> review_candidates     |
       |  otherwise, one Send each    -> review_candidate      |
       |                                                       |
       |   review_candidate (subgraph, once per candidate)      |
       |     START -> retrieve_policy_set -> judge_candidate -> END
       |                                                       |
       `- review_candidate / review_candidates ----------------'
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
            `- dispatch (the same closure) -> review_candidate / review_candidates
                 -> investigate_hinges -> rejudge_investigated -> generate_questions
```

Candidate work is exposed to LangGraph through `Send`; no node hides a thread pool or a
private orchestration loop. Retrieval and judgement are separate nodes in a visible
candidate subgraph, so a reader can see that a candidate is judged against policies chosen
for it rather than against the whole corpus.

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
answer for itself. So before anybody is interrupted, `investigate_hinges` gives each held
finding a bounded, recorded pass of read-only lookups over the atlas the review analysed and
the source at the revision that produced it.

**It establishes facts and decides nothing.** It returns a `RecordedInvestigation` — every
lookup, its arguments and the exact answer — and writes no findings at all. It is shown
which policies the judgement said the candidate bears on, by title and strength, so it knows
what the question is about; it is never shown the policy list, so there is no identifier it
could cite and nothing to validate.

`rejudge_investigated` then puts that record back to the **same judge**, with the same
candidate, the same case and the same retrieved policies. Nothing about the question changed,
so nothing is retrieved again. A candidate is re-judged only if it has a record, that record
has at least one lookup, and this round retrieved for it — so an investigation that was
withheld, or that could not ask anything, leaves the judge with exactly the inputs it had the
first time, and the finding it already reached stands.

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

**Reviews** are product history: immutable snapshots in the workspace database, sequenced per
branch and case, each naming the one before it. A checkpoint id is never a review id; the
execution store maps between them.

A run's *stage* is held in memory and is worth nothing after the process that ran it. The
durable status — running, awaiting answers, completed, failed, cancelled — is the execution
store's, and it survives a restart. A watcher asking about a run this process did not start
is told the honest status with no stage list, rather than a progress bar that claims to be
live and is not.
