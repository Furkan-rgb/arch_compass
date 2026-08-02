-- The choice stops being a reference into a file, because there are no files any more.
--
-- `profile_id` named a `models.*.yaml` the workspace held, and that mechanism is gone: which
-- providers exist, where they are reached and what their budgets are is stated in code, one
-- descriptor per adapter module. What is left of a choice is the three things that actually
-- vary between two otherwise identical runs — which provider, which model, and whether the
-- model reasons before answering.
--
-- `thinking` is INTEGER NULL because the setting has three states and not two: 1 requires
-- reasoning, 0 forbids it, NULL leaves the model to its own default, and on both providers
-- those are three different behaviours rather than two. A NOT NULL column defaulting to 0
-- would quietly turn every existing choice into "forbid".
--
-- Nothing is carried over, and that is deliberate. A selection was only meaningful together
-- with the file it named, the files are deleted, and what is lost is one row a reader
-- replaces with two clicks. Translating it would mean inventing the thinking mode it never
-- recorded, and inventing it would silently change what a workspace runs against — the one
-- thing a review that carries its model as provenance cannot have happen quietly.
--
-- A new table under a new name rather than a rebuild of the old one, and the name is the
-- load-bearing part. The suite rewinds a workspace to a retired version and replays
-- everything after it, so 022 runs a second time — and 022 copies `profile_id` out of
-- `reasoning_model_selection`. Reusing that name would leave this shape standing where 021's
-- `CREATE TABLE IF NOT EXISTS` is a no-op, and 022 would then fail with `no such column:
-- profile_id`. Under a new name, 021 rebuilds its own table for 022 to read, 022 rebuilds it
-- again, and the drop below removes it a second time. Every pass ends in the same schema.

DROP TABLE IF EXISTS reasoning_model_selection;

CREATE TABLE IF NOT EXISTS reasoning_model_choice (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    thinking INTEGER,
    selected_at TEXT NOT NULL,
    failed_at TEXT,
    failure_detail TEXT NOT NULL DEFAULT '',
    input_token_limit INTEGER,
    output_token_limit INTEGER
);
