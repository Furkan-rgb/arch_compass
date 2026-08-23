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

`load_policy_corpus` obtains applicable authored policies. What happens next is one of two
paths, chosen at dispatch rather than when the graph was built, because which model is
selected can change while the workspace is running.

Where the provider can be asked for every verdict in one submission — today that is Google,
with `ARCHCOMPASS_GOOGLE_BATCH` on by default, which is what a hosted deployment runs —
`review_candidates` retrieves for every selected candidate and submits them together. A
fan-out cannot batch: every branch would have to wait for every other, which is a deadlock
wearing a barrier's clothes.

Otherwise LangGraph fans out one visible candidate subgraph per selected candidate:

```text
retrieve_policy_set -> judge_candidate
```

The configured `PolicyRetriever` returns ordered policies plus generic audit provenance.
The `ArchitectureJudge` receives only the candidate, current case, and that stable retrieval
result. Structured model positions are resolved back to application-owned policies before a
domain `Finding` is created.

The candidate reaches the model through `candidate_text()` in
[`reasoning/adapters/langchain.py`](../src/archcompass/reasoning/adapters/langchain.py),
which lays it out as addressable sections — pattern, summary, participants, relationships,
measurements, evidence, detection limits. It is not a dataclass repr: a repr escapes every
newline, so code would arrive as one long line punctuated by literal `\n`, and a
measurement's `structural_proxy` tag would be present and unreadable at the same time.

Source excerpts are bounded at `MAX_EXCERPT_LINES = 60` per participant and widened upward
over at most `MAX_LEADING_COMMENT_LINES = 12` contiguous comment lines. Both numbers are
deliberate. A detector picks declaration spans — one line for a duplicated constant, a
handful for a class — so the ceiling guards against a pathological span rather than
budgeting a view; raising it to 200 bought no more understanding, because the longest span
in this repository is 1,676 lines and the excerpt is a fragment at either ceiling. What
changed was only whether it *looked* like one, which is why a truncated excerpt now carries
a note saying so. The upward widening exists because a constant's recorded span is the line
that assigns it while the sentence explaining it sits directly above, and a judge shown the
assignment alone was deciding with that sentence out of frame.

Findings that came back with a hinge then reach `investigate_hinges`, which gives each one
a bounded pass of read-only atlas lookups — at most six turns, ten thousand characters of
findings and eight findings per round — and either settles the verdict, narrows the question,
or leaves it exactly as it was. Every lookup is recorded on `Review.investigation_manifest`
and named on the finding by content hash. A hinge nothing settled reaches question generation
unchanged, which is why that path needed no new code.

`generate_questions` then either settles the review or returns application-identified
clarifications. When clarification is needed, ArchCompass composes and records an immutable
`awaiting_answers` review before `await_answers` interrupts. The client resumes the same
thread using the review ID; it does not submit a continuation pointer.

Every pending question is recorded as answered or explicitly skipped. `revise_case` opens
one `ArchitectureCase` revision the first time a review has an answer to record, and every
later round of that review adds to the same revision. The initial selector then rejudges
every extant candidate, retrieves policies again, and returns to question generation. Early
conclusion and a three-round cap terminate with remaining uncertainty preserved.

Every exit from that loop passes through `seal_case`, which writes the revision the review
opened — once, and only if the review opened one. A review that asked nothing, or that
nobody answered, leaves no case revision behind. The number it takes comes from the store
rather than from the case in hand, so a review started against an older revision writes
beside the newer ones instead of over them.

A review keeps one `sequence` for its whole life. Each waiting snapshot and the record it
finishes as are snapshots of one revision, told apart by `Review.round`, and the newest of
them is the one every listing shows. Superseded snapshots stay readable by id.

## Completion, failure, and cancellation

Settled and CI paths compose and persist a completed `Review`. CI uses the same graph with
interactive interruption disabled. A failure after repository, atlas, and case context are
available records the richest possible immutable failed snapshot. A waiting review can be
cancelled explicitly, producing a new cancelled snapshot; cancellation does not mutate the
waiting record.

A run reports its graph stage and its judged count as it goes, read back through
`GET /api/reviews/runs/{run_id}`. LangGraph
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
application-assembled context, and may put the same bounded, recorded lookups to the
repository that a hinge investigation does. Its first turn is never forced, unlike a hinge's:
a reader is usually asking about text already in front of them, and a forced lookup there
spends a round trip asking the repository about the review's own words.

Every fact in an answer comes from that context or from a recorded lookup, and the answer
says which. It is not held to extraction: what to do about a finding follows from the
finding, the policies it bears on and any recommended response already recorded, and the
answer distinguishes what the review records from what it reasons. A proposed fix is still
structure and placement with a citation rather than a patch — the lookups answer what
depends on what, and `read_code` serves a bounded span at a named node, neither of which is
a diff.

The atlas a conversation asks is the one its review judged, carried on the review itself,
so structural questions keep answering however far the repository has moved on. Reading
source is the one lookup that leaves the atlas, and it leaves it for the same revision: a
review records the commit it judged, and `read_code` asks git for the file as it stood at
that commit. The line spans in the atlas belong to that revision and to no other, which is
what makes this the correct reading rather than merely the current one.

Only where there is no revision to ask for — an unversioned directory, or a commit git no
longer holds — does the working tree become the only source there is, and then it may be
read only while it still is what was judged. That is the freshness check, and it refuses in
a sentence naming the way back.

Source/report/repository/case/revision endpoints project the same stored domain records
through boundary Pydantic DTOs.
