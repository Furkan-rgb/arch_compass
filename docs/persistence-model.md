# Persistence model

ArchCompass separates resumable execution storage from architectural history.

```text
review-checkpoints.db
  LangGraph thread/checkpoint state

workspace.sqlite3
  repository and atlas records
  case revisions
  immutable review snapshots
  execution-to-review aliases
  standing-decision history
  finding cache
  review conversations
  model selection
  retrieval provenance
```

Checkpoint IDs are never review IDs. Domain lineage uses repository/branch identity,
sequence, and `previous_review_id`.

## Immutable records

Review snapshots are inserted at awaiting, completed, failed, and cancelled boundaries.
Case answers are recorded on the revision the review that asked them opened — one per
review, written when that review finishes, and never written over: a second, different
revision under a number already stored is an error rather than a silent no-op. Standing
decisions and conversations are append-only. A review is stored once per snapshot and
several snapshots share one `sequence`, so listings read the newest snapshot per revision.
Pydantic `TypeAdapter` codecs validate stored JSON before domain dataclasses are rebuilt.

The finding cache is keyed from the candidate, case, generic retrieval identity, reasoning
model, and prompt. It is an optimization, not a source of domain identity. Retrieval
manifests persisted on reviews explain exactly which policies were selected.

## Schema epochs

ArchCompass does not reinterpret records an earlier schema wrote. When a persisted domain
record changes shape, the codec refuses the stored row rather than guessing, and a numbered
migration under [`persistence/sqlite/migrations/`](../src/archcompass/persistence/sqlite/migrations)
retires what can no longer be read. There are no compatibility shims.

What the migration drops and what it keeps follows one rule: **derived output is produced
again, authored input is not.**

- Dropped: review snapshots, the finding cache, executions and their aliases, and review
  conversations. All of these embed a `Candidate` or point at one that does.
- Kept: case revisions, which hold intent a person wrote, and standing decisions, which hold
  a team's disposition toward a boundary. Standing decisions survive a candidate-shape change
  because candidate identity is derived from pattern and participant names, so a disposition
  still lands on the boundary it was made about — but a migration that changed that
  derivation would have to retire them too.

Clearing executions is also what retires the LangGraph checkpoints in a separate
`review-checkpoints.db`: a checkpoint is reachable only through the thread ID an execution
row holds, so with the executions gone there is no path back to in-flight state carrying the
old shape. The file itself is not truncated by the migration and can be deleted.

`002_candidate_evidence_epoch.sql` is the worked example — measurements moved from
name/value pairs to records that state their own nature and limits.

Not every schema change is an epoch. `003_one_revision_per_review.sql` rebuilds
`core_review_snapshots` in place instead of dropping it: what changed is which numbers a
*new* review takes, and a review already recorded is still a true record of what was judged
under the numbers it was read under. It drops the uniqueness of `(repository, branch,
sequence)`, because one review now files a snapshot per clarification round under one
sequence, and adds the `round` that tells them apart.

### The checkpoint allowlist

[`bootstrap.py`](../src/archcompass/bootstrap.py) passes `allowed_msgpack_modules` to the
LangGraph serializer. Every nested record a checkpointed `Candidate` holds must be named
there. An unlisted type is **not refused — it is revived as a raw dict**, so the failure
surfaces much later as an attribute error on a resumed run. Adding a record to the domain
means adding it here.

## Startup

The runtime opens `.archcompass/workspace.sqlite3` and initializes it when missing. This is
the sole application database name; other files in `.archcompass/` are neither interpreted
nor allowed to block startup.

Explicit review deletion remains available to the user. Startup and normal execution never
silently erase architectural history.
