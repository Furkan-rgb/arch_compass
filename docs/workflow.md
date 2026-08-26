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
            `- dispatch (the same closure) -> review_candidate -> generate_questions
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

## What a judgement may look at

A judgement is not shown a candidate and asked to decide from it alone. It may read the
repository the candidate was found in while it decides — read-only, at the exact revision the
analysis was made from — and it does that inside the same conversation that produces the
verdict. There is no separate investigation phase and no second judgement.

Eight tools, and each answers one thing. `ls`, `read_file`, `glob` and `grep` read the
reviewed source. `describe_code`, `related_code` and `search_code` ask the atlas the
questions no search over text can answer: what implements this, what reaches it, what it
reaches for. `search_policies` finds a principle the deterministic retrieval did not send —
and whatever it returns joins the set the verdict's citations are checked against, so a
judgement can never cite a policy nobody put in front of it.

"At the revision" has one fallback. The source is asked of git at the atlas's commit; where
there is no revision to read — an unversioned directory, or a commit git no longer holds —
the working tree is read instead, and only after a freshness check confirms the tree still is
what was judged. That check runs immediately before every such read rather than once, because
a tree can change while a judgement is still using it.

Using no tools at all is an ordinary outcome. Where the dossier and the policies settle the
question, the judgement says so and finishes; measured on a hosted model, that is about one
judgement in five.

Four circuit breakers bound it — model calls, tool calls, recorded characters and wall clock
— and a fifth ends a run that asks the same question of the same tool a third time, which
cannot answer differently because the reviewed repository does not change while it is being
judged. None of them is a quota, and none is a lost finding: when one fires the tools are
taken away and the same conversation is asked to state the verdict it was working towards.

What it looked at is kept. Every tool call, its arguments and the exact answer become the
`RecordedInvestigation` on the review, and the finding names it by content hash. It is not
evidence: `Finding.evidence` is what the detector pinned, and nothing a judgement read is
promoted into it.

The same toolbox answers a reader. `ReviewToolbox` is built once and used by both callers —
a judgement deciding a candidate, and a conversation held against a review — because it is
one set of bounds and a second construction is how two of them start to differ. The
conversation's lookups are recorded the same way: the atlas tools write themselves into the
transcript as they answer, and everything else the agent is given, filesystem included, is
written there by the loop that wrapped the call. A lookup nobody recorded did not happen.

## Asking about a question

A reader who cannot make sense of a question the review is waiting on opens a thread about
that question, from the round itself. It is a `ReviewConversation` with a `question_id` on
it, and the scope is what makes it a different prompt: the findings that question is holding
up, in full with their hinges and evidence, rather than every finding in the review in
outline. The thread is filed against the snapshot that asked, so it stays with the round on
the Rounds surface and does not follow the case forward.

What it may do is bounded by one rule the contract states four ways: **explain the question,
never decide it**. The question exists because the code could not settle it; an agent reading
the same code cannot settle it either, and an answer becomes the team's intent the moment it
is recorded. So it says what is being asked, which finding is waiting, and what each answer
would change — and it never says which answer is likelier. "The repository already settles
this" is a first-class outcome, and the honest next move there is an explicit skip.

It may offer wording in `suggested_answer`, which reaches the reader's own answer box as
editable text. Nothing submits on their behalf. Where they submit it byte for byte unchanged,
`Answer.drafted_by` records which model wrote it and `case_text` puts that in front of every
later judgement — because otherwise a model reads its own draft back as the team's position
with nothing saying so. Edit a word and the stamp is not set: the sentence is then theirs.
The fact is stated and never weighed; no prompt tells a judgement what to make of it.

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
