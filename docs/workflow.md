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
  -> [retrieve_policy_set -> judge_candidate] x candidate   (or review_candidates, batched)
  -> investigate_hinges
  -> generate_questions
       | settled / CI / limit / early stop
       |   -> seal_case
       |   -> write_final_synopsis -> compose_final_review -> record_review -> END
       |
       ` questions
           -> write_waiting_synopsis
           -> compose_waiting_review
           -> record_waiting_review
           -> await_answers (interrupt)
           -> revise_case
           |    ` stop requested -> seal_case -> write_final_synopsis -> ... -> END
           -> select_candidates_for_rejudgement
           -> [retrieve_policy_set -> judge_candidate] x candidate
           -> investigate_hinges
           -> generate_questions
```

Candidate work is exposed to LangGraph through `Send`; a node does not hide a thread pool
or private orchestration loop. Retrieval and judgement are separate nodes in a visible
candidate subgraph.

`investigate_hinges` is unconditional and guards itself. Both judgement paths reach it and
both leave it for `generate_questions`, so the edge carries no decision — and a conditional
edge out of a `Send`-fanned node would evaluate its predicate once per branch against that
branch's state, which is the wrong place to decide something about the whole set of
findings. Where no model can call tools, or nothing hinged, the node returns before it reads
a finding.

`write_synopsis` is the one node that asks the model about the review rather than about a
candidate: it writes the paragraph the report opens on, from verdicts that are already
final. It is a node rather than something the composer does because the composer is a pure
function of its draft, and because a graph whose nodes are its capabilities is how a model
call stays visible. Both compose paths have one — a waiting review is a document somebody
may hand over part-way through a clarification round. `ReviewSynopsisWriter` is the only
capability with a default (`NoReviewSynopsis`): a workspace with no model available still
composes its review, and the report opens on its counts.

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

After a round of answers, `RejudgeAllCandidates` initially selects every extant candidate.
It reads the answers rather than the revision number, which no longer moves between one
review's rounds. A dependency-aware selector can later replace it without changing the graph
or domain.
