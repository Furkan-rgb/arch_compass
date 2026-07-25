-- The report_follow_ups table was the storage for a pre-V1.2 feature whose API and
-- UI were removed when report conversations replaced it. Its rows were never read
-- again and were retained only by a migration-era mandate. ArchCompass has not been
-- released, so there is no external data to preserve.
DROP INDEX IF EXISTS report_follow_ups_run_created;
DROP TABLE IF EXISTS report_follow_ups;
