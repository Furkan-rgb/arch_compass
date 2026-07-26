-- A listing of reviews identified only by `rev_9f2c…` is a listing nobody can read: what
-- distinguishes two reviews is the case each judged. The title is denormalised here for the
-- same reason the boundary counts already are — the listing must stay cheap as reviews
-- accumulate, and parsing every stored report to render a page of rows is what the columns
-- exist to avoid.
--
-- Nullable, because a failed review has no report to take a title from. A row that cannot
-- say which case it judged is rendered by its identifier, which is honest; a placeholder
-- written into the column would be indistinguishable from a case actually called that.
ALTER TABLE boundary_reviews ADD COLUMN case_title TEXT;

UPDATE boundary_reviews
SET case_title = json_extract(review_json, '$.report.case_title')
WHERE case_title IS NULL;
