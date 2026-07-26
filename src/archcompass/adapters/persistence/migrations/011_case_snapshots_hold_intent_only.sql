-- ADR-0007 settled that a case holds user intent only: the advisor's conclusions live in
-- the review that produced them, never written back into the case. Migration 010 dropped
-- the era's tables and the `origin_run_id` column, but the snapshots themselves still
-- carried the three fields the advisor used to write into them.
--
-- A case cannot be regenerated the way a review can — it is what the user typed — so the
-- stored document is moved forward here rather than reported as unreadable. Only advisor
-- output is removed; every user-authored field is untouched.
UPDATE case_revisions
SET snapshot_json = json_remove(
        snapshot_json,
        '$.advisor_design_forces',
        '$.current_recommendation',
        '$.confidence'
    )
WHERE json_type(snapshot_json, '$.advisor_design_forces') IS NOT NULL
   OR json_type(snapshot_json, '$.current_recommendation') IS NOT NULL
   OR json_type(snapshot_json, '$.confidence') IS NOT NULL;

-- A revision the advisor wrote was recorded as a `consultation` event. There is no such
-- event now, and the two kinds that remain say who wrote a revision, not which subsystem
-- did: `actor` already holds that, and these rows keep `archcompass` there. Rewritten
-- rather than dropped, because a review pins the revision number it judged.
UPDATE case_revisions SET event_type = 'user_update' WHERE event_type = 'consultation';
