-- A case revision records which review's questions it answered, and with what.
--
-- Everything either side of an answer was already immutable and already kept: the questions
-- live in the pass-1 review for ever, and the case is append-only with one full snapshot per
-- revision. What was missing was the arrow between them. A revision held the answer text and
-- nothing saying which question produced it, so four ordinary questions had no answer —
-- which ones did I skip, what did I say to Q-3, where did this line in my case come from,
-- and did answering Q-2 actually move that verdict.
--
-- The last one is the expensive one. The whole justification for judging twice is that
-- answers move verdicts — four of five on the bundled `warehouse-sync` example — and without
-- this that can only be seen in aggregate. No individual answer could be attributed to the
-- verdict it moved.
--
-- Master plan 6C.4 has said "a revision may record which review and question it answers"
-- since elicitation was specified. This is that, and the distinction it draws there is the
-- one that keeps invariant 25 intact: the `origin_run_id` ADR 0007 removed marked revisions
-- *authored by a run*, where this marks a revision the user authored and says what prompted
-- it. Nothing recorded here is model-written.
--
-- Deliberately not inside `snapshot_json`. That column holds the `ArchitectureCase`, and a
-- case has to stand alone — a `Q-2` inside it would make the document unreadable without the
-- review that produced it, and would put an advisor-assigned identifier into a user-authored
-- record.
--
-- Rebuilt rather than `ALTER TABLE ... ADD COLUMN`, for the reason 013, 014 and 018 rebuild:
-- a migration at or above a retired version number is replayed against a workspace that has
-- already applied it, and a bare ADD COLUMN fails there with `duplicate column name`. The
-- rebuild is idempotent, which is what the replay needs. Nothing is lost — every existing
-- revision is copied with `answered_json` NULL, which is truthful: as far as anything
-- recorded knows, it was authored by hand.

CREATE TABLE IF NOT EXISTS case_revisions_next (
    case_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    -- NULL for a revision authored by hand. Its absence is the only thing that tells a hand
    -- edit from a round of answering, so it is a nullable column rather than a defaulted one.
    answered_json TEXT,
    PRIMARY KEY (case_id, revision),
    FOREIGN KEY (case_id) REFERENCES cases(case_id)
);

INSERT OR IGNORE INTO case_revisions_next(
    case_id, revision, event_type, actor, created_at, snapshot_json, answered_json
)
SELECT case_id, revision, event_type, actor, created_at, snapshot_json, NULL
FROM case_revisions;

DROP TABLE case_revisions;
ALTER TABLE case_revisions_next RENAME TO case_revisions;

-- One review is asked once and its second pass cannot ask again, so a review maps to at most
-- one answering revision. A unique index says so rather than leaving it as a property of the
-- flow that a future caller could break silently. NULLs are distinct in SQLite, so every
-- hand-authored revision is exempt without needing a partial index.
CREATE UNIQUE INDEX IF NOT EXISTS case_revisions_answer_each_review_once
    ON case_revisions(json_extract(answered_json, '$.review_id'));
