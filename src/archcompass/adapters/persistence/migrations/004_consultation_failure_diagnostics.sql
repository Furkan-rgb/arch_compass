ALTER TABLE consultation_jobs
    ADD COLUMN failure_diagnostics_json TEXT NOT NULL DEFAULT '[]';
