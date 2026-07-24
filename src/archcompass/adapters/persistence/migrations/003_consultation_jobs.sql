CREATE INDEX IF NOT EXISTS consultation_runs_case_completed
    ON consultation_runs(case_id, completed_at DESC);

CREATE INDEX IF NOT EXISTS cases_updated
    ON cases(updated_at DESC);

CREATE INDEX IF NOT EXISTS atlas_versions_created
    ON atlas_versions(created_at DESC);

CREATE TABLE IF NOT EXISTS consultation_jobs (
    run_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    input_case_revision INTEGER NOT NULL,
    repository_root TEXT,
    status TEXT NOT NULL,
    current_stage TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    warning TEXT,
    error TEXT,
    FOREIGN KEY (case_id, input_case_revision)
        REFERENCES case_revisions(case_id, revision)
);

CREATE INDEX IF NOT EXISTS consultation_jobs_updated
    ON consultation_jobs(updated_at DESC);

CREATE TABLE IF NOT EXISTS consultation_progress_events (
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    PRIMARY KEY (run_id, sequence),
    FOREIGN KEY (run_id) REFERENCES consultation_jobs(run_id)
);
