# Review workflow

[`workflow/graph.py`](../src/archcompass/workflow/graph.py) is the canonical description of
review execution.

```text
START
  -> load_context
  -> analyze_repository
  -> detect_candidates
  -> calculate_delta
  -> select_initial_candidates
  -> load_policy_corpus
  -> [retrieve_policy_set -> judge_candidate] x candidate
  -> generate_questions
       | settled / CI / limit / early stop
       |   -> compose_final_review -> record_review -> END
       |
       ` questions
           -> compose_waiting_review
           -> record_waiting_review
           -> await_answers (interrupt)
           -> revise_case
           -> select_candidates_for_rejudgement
           -> [retrieve_policy_set -> judge_candidate] x candidate
           -> generate_questions
```

Candidate work is exposed to LangGraph through `Send`; a node does not hide a thread pool
or private orchestration loop. Retrieval and judgement are separate nodes in a visible
candidate subgraph.

## State and snapshots

`ReviewState` is a `TypedDict` used only while the graph runs. It holds domain snapshots,
candidate partitions, retrieval results, findings, questions, submitted answers, round
state, and control flags. It is neither persisted as the audit model nor exposed as the
public API.

Each review attempt gets a fresh LangGraph thread ID. Review lineage instead uses stable
repository and branch identity, review sequence, and `previous_review_id`.

The graph records immutable snapshots at awaiting, completed, failed, and cancelled
boundaries. The waiting snapshot is persisted before `await_answers`; the interrupt node is
write-free because LangGraph restarts interrupted nodes on resume.

## Clarification

The workflow permits at most three rounds. Partial submissions are completed with explicit
skips, early conclusion is supported, and answered/skipped equivalent questions are not
asked again. At the limit, remaining uncertainty is represented by held findings instead of
an unbounded loop.

CI runs the same graph with interruption disabled. Unresolved questions produce held,
non-blocking findings.

## Delta and rejudgement

Unchanged findings can carry forward when every judgement input is unchanged. Changed and
new candidates are judged; disappeared candidates become addressed after conservative
succession matching. Historical candidates can be marked resurfaced. Standing decisions
read through branch and succession lineage without entering judgement.

After a case revision, `RejudgeAllCandidates` initially selects every extant candidate. A
dependency-aware selector can later replace it without changing the graph or domain.
