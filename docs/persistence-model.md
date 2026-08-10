# Persistence model

One SQLite database per workspace, at `<workspace>/.archcompass/archcompass.db`, private to the
persistence adapters. Nothing above `adapters/persistence` knows it is SQLite: the application
layer sees the repository protocols in `ports/repositories.py` and nothing else.

Connections are per call. Each one enables foreign keys, WAL, and a 5-second busy timeout, so a
run holding the database for the length of a review does not lock a page out of reading. The
analysed repository is never a persistence destination; a workspace living inside a repository
being reviewed is allowed and is excluded from that repository's snapshot, so state written here
cannot enter the atlas or move its fingerprint. Database paths are revalidated against the
workspace on every connect and refuse traversal and symlink escapes.

## The one storage pattern

Every aggregate is stored as **a JSON document beside queryable projection columns**. The
document is the record; the columns exist so a listing or a join does not have to parse it.
`boundary_reviews` is the clearest case: the whole review — verdicts, questions, investigation,
delta — is one `review_json`, and `status`, `case_id`, `branch_id` and the four boundary counts
are columns because the reviews list must stay cheap as reviews accumulate.

Documents are decoded strictly (`stored_records.decode_stored_json`). A row written by a
superseded schema fails validation and raises `UnreadableStoredRecordError` naming the record and
what to do about it, rather than being reinterpreted by a compatibility shim — ADR 0002. The
remedy differs by record and is supplied by the caller: a review can be run again, a case cannot,
because a case is what someone typed.

## Tables and ownership

**Cases** — `cases` holds the current-revision pointer and timestamps; `case_revisions` holds the
immutable snapshots, one row per revision, plus `answered_json`, the provenance of what a
revision answered. A unique index enforces one answering revision per review, so the elicitation
loop cannot answer the same review twice. Appends match the expected revision inside the same
transaction as the new snapshot.

**Atlas** — `atlas_versions` is the immutable evidence identity (content fingerprint, parser
version, analysis config hash, and the commit, branch and repo/branch ids where they exist).
`atlas_nodes`, `atlas_edges`, `atlas_metrics`, `atlas_signals` and `atlas_module_facts` are owned
by exactly one version. Rebuilds always insert a new version; old reviews go on referencing the
exact evidence they used.

**Reviews** — `boundary_reviews` (the aggregate as JSON, with listing columns and the
`elicited_from` back-reference that ties a second pass to the first) and `review_conversations`
(the whole conversation as JSON, with a message count for listings). Both are written from the
moment a run starts, not at the end: a review nobody can find while it is being produced looks
the same as one that was never started.

**Memory across revisions** — `verdict_cache` is write-once per key: a verdict already reached
for an unchanged question is returned rather than recomputed, and rows outlive the review that
reached them (025). `boundary_lines` is the append-only record of what happened to a boundary
across revisions — successions, closures, resurrections (029).

**Standing state** — `standing_decisions` and `decision_comments` are append-only: a team's
disposition toward a boundary, with an author and a reason, and the discussion attached to it
(026). `repository_lineages` and `branch_lineages` give a repository and its branches durable
identity independent of where they are checked out (024, 030).

**Workspace settings** — `reasoning_model_choice` is a single row: provider, model, thinking
variant and the budgets that came with it (021–023). It is workspace-global, which is a known
limitation for shared use rather than a design intent. `scope_selections` records the folders a
repository is reviewed without (032); `source_origins` records where a fetched repository came
from (031); `policy_source_registrations` records the paths policies are read from.

Policies themselves are deliberately not stored. Sources are registered by path and the documents
are re-read per request, so editing a policy file changes the next review with nothing to rebuild.

**The ledger** — `schema_migrations` holds `version`, `applied_at` and `checksum`.

## Migrations

Numbered SQL files embedded in the package, applied explicitly at initialization in filename
order. Each file runs as a sequence of complete statements inside one `BEGIN IMMEDIATE`, together
with its own row in `schema_migrations`, so a failing later statement cannot leave an earlier
schema or data change applied.

Three guarantees are worth stating because each was bought with a failure:

- **An applied migration is history, and history is append-only.** Every run records the
  `sha256` of the text it ran, and a file that has changed since it was applied refuses to open
  the database, naming the file. Editing an applied migration otherwise changes nothing and
  announces nothing until an unrelated query fails: two columns added to 021 after it had run
  surfaced much later as `no column named input_token_limit`. Rows written before the checksum
  column existed hold `NULL` and are grandfathered.
- **A migration number is an identifier, not a position, and there is no 015.** The numbering
  skips it: 015 was withdrawn before release and its number was retired with it. Nothing is
  missing and there is no file to hunt for. Closing such a gap by renumbering a later migration
  down into it is what caused the failure that made this a rule — every workspace that had
  already recorded that number then skipped the renumbered file, so a table was missing in
  exactly the workspaces that had data in them.
- **Foreign keys are off for the length of a migration, and paid for.** That is SQLite's own
  recipe for rebuilding a table anything points at, and it would also let a careless migration
  strand rows. So `PRAGMA foreign_key_check` runs inside the transaction and anything it finds
  rolls the migration back — a stronger guarantee than the per-statement enforcement it replaces,
  which never looked at rows the migration did not itself touch.

Migrations that move stored documents forward exist and are ordinary: 011 stripped advisor output
from case snapshots, 033 strips `failure_diagnostics` from reviews. Both are guarded so a replay
is a no-op, and both are tested against a workspace with rows in it, because a migration that
passes against an empty database has not been tested at all (019 died on the first real one).

## What used to be here

The consultation era's storage is gone rather than deprecated, in line with ADR 0002. Migration
010 dropped `consultation_runs`, `consultation_jobs`, `consultation_progress_events` and the
`report_conversation*` tables when the boundary review replaced that path (ADR 0006); 007 had
already dropped `report_follow_ups`. Migration 017 dropped the withdrawn knowledge index and 020
the policy index, both after retrieval lost to presenting the corpus whole; their per-version
`vec0` tables cannot be enumerated in static SQL and are left inert, which 020 explains. Migration 033 dropped `branch_baselines`: the baseline was retired in favour of the
delta rule (architecture.md decision 4) and its service was never constructed, so the table never
held a row.
