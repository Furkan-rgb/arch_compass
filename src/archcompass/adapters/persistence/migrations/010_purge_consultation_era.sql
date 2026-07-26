-- The consultation path was replaced by the boundary review (ADR 0006), and its tables
-- have had no reader or writer since. They are dropped here rather than left as schema a
-- future reader would have to work out the status of.
DROP TABLE IF EXISTS consultation_progress_events;
DROP TABLE IF EXISTS report_conversation_summaries;
DROP TABLE IF EXISTS report_conversation_errors;
DROP TABLE IF EXISTS report_conversation_messages;
DROP TABLE IF EXISTS report_conversations;
DROP TABLE IF EXISTS consultation_jobs;
DROP TABLE IF EXISTS consultation_runs;

-- A case revision could name the run that produced it, from when the advisor wrote its
-- conclusions back into the case. It never does now: the case holds user intent only, and
-- advisor output lives in the review that produced it (ADR 0007).
ALTER TABLE case_revisions DROP COLUMN origin_run_id;
