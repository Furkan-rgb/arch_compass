-- What the provider said about the chosen model, kept so resolving a choice costs no probe.
--
-- A profile's budgets are written for the model its own file names. Choose a smaller model
-- through that same profile and those numbers become generous rather than wrong-looking,
-- which is the direction that lets an oversize request through to be silently truncated
-- instead of refused. Resolving a selection therefore clamps the profile down to these, and
-- only ever downwards: the authored number stays the ceiling, because it was already
-- deliberately below what the vendor advertises.
--
-- Null where the provider reports no limit, which is every Ollama model.
--
-- Its own migration rather than two more columns in 021, and that is the whole lesson here.
-- 021 had already run in a live workspace when these columns were wanted; adding them to it
-- changed a file the runner had recorded as applied, so it was never re-read and the table
-- stayed as it was. The failure surfaced as `no column named input_token_limit` at the first
-- click, in a place that said nothing about migrations. An applied migration is history and
-- history is append-only.
--
-- Written as a rebuild rather than as two `ALTER TABLE ADD COLUMN`, because migrations here
-- must survive being replayed — the suite rewinds a workspace to a retired version and runs
-- everything after it again — and SQLite has no `ADD COLUMN IF NOT EXISTS`, so an ALTER
-- fails the second time with `duplicate column name`. This form is replayable: the new shape
-- is a superset of the old, so the SELECT below names columns that exist under either, and
-- `IF NOT EXISTS` makes the create a no-op on a second pass. Same idiom as migration 019.
--
-- No foreign keys point at this table, so the rebuild has none of 019's hazards; it is
-- rebuilt only because that is the replay-safe way to widen a table in SQLite.

CREATE TABLE IF NOT EXISTS reasoning_model_selection_next (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    profile_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    failed_at TEXT,
    failure_detail TEXT NOT NULL DEFAULT '',
    input_token_limit INTEGER,
    output_token_limit INTEGER
);

INSERT OR IGNORE INTO reasoning_model_selection_next(
    id, profile_id, provider, model, selected_at, failed_at, failure_detail
)
SELECT id, profile_id, provider, model, selected_at, failed_at, failure_detail
FROM reasoning_model_selection;

DROP TABLE reasoning_model_selection;
ALTER TABLE reasoning_model_selection_next RENAME TO reasoning_model_selection;
