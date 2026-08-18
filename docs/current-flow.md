# Current review flow

This is the implemented path through ArchCompass after the clean-break refactor. It is a
navigation aid for maintainers; [`workflow/graph.py`](../src/archcompass/workflow/graph.py)
remains the executable source of truth.

## Start and index

The web or CLI resolves a canonical repository path, records repository and branch lineage,
creates or selects an immutable `ArchitectureCase`, and indexes the repository. The
deterministic analyzer parses source without importing or executing it, writes the current
atlas records, and assigns a content identity.

Starting a review creates a new LangGraph thread. `load_context` resolves the requested
repository/branch/case revision and the preceding review lineage. `analyze_repository`
rebuilds a domain `RepositoryAtlas`; `detect_candidates` applies the characterized
detectors; `calculate_delta` partitions candidates against history; and
`select_initial_candidates` carries eligible findings while selecting changed/new work.

## Retrieve, judge, and clarify

`load_policy_corpus` obtains applicable authored policies. LangGraph fans out one visible
candidate subgraph per selected candidate:

```text
retrieve_policy_set -> judge_candidate
```

The configured `PolicyRetriever` returns ordered policies plus generic audit provenance.
The `ArchitectureJudge` receives only the candidate, current case, and that stable retrieval
result. Structured model positions are resolved back to application-owned policies before a
domain `Finding` is created.

`generate_questions` then either settles the review or returns application-identified
clarifications. When clarification is needed, ArchCompass composes and records an immutable
`awaiting_answers` review before `await_answers` interrupts. The client resumes the same
thread using the review ID; it does not submit a continuation pointer.

Every pending question is recorded as answered or explicitly skipped. `revise_case` creates
the next immutable `ArchitectureCase` revision. The initial selector then rejudges every
extant candidate, retrieves policies again, and returns to question generation. Early
conclusion and a three-round cap terminate with remaining uncertainty preserved.

## Completion, failure, and cancellation

Settled and CI paths compose and persist a completed `Review`. CI uses the same graph with
interactive interruption disabled. A failure after repository, atlas, and case context are
available records the richest possible immutable failed snapshot. A waiting review can be
cancelled explicitly, producing a new cancelled snapshot; cancellation does not mutate the
waiting record.

The web streaming endpoint emits graph-stage updates and the resulting snapshot. LangGraph
checkpoint state lives in `review-checkpoints.db`; review history, execution aliases, cases,
atlases, findings, decisions, and retrieval manifests live in `workspace.sqlite3`.

## Subsequent reviews and product surfaces

A later attempt gets a fresh thread but links to the preceding domain review. Delta
calculation preserves unchanged, changed, new, addressed, succession, and resurfacing
provenance. Cache reuse is keyed from the actual judgement inputs and records the source
review when a finding is reused.

Standing decisions are appended separately from findings. Waivers require reasoning, and
decision lineage can read through deterministic succession without influencing the judge.
Post-review conversation uses the persisted review, pinned evidence, case, and
application-assembled context; it does not restore an autonomous repository investigation
loop. Source/report/repository/case/revision endpoints project the same stored domain
records through boundary Pydantic DTOs.
