CREATE TABLE IF NOT EXISTS report_follow_ups (
    follow_up_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    entry_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES consultation_runs(run_id)
);

CREATE INDEX IF NOT EXISTS report_follow_ups_run_created
    ON report_follow_ups(run_id, created_at, follow_up_id);

