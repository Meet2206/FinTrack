-- finance/migrations/002_synced_month.sql
-- Version 2: also remember WHICH MONTH TAB a row was last written to.
-- Why: if you fix a misread date, the row moves to another month. The next sync must
-- rebuild the old month's tab too, or a stale copy of the row would stay there.
ALTER TABLE transactions ADD COLUMN synced_month TEXT;
UPDATE transactions SET synced_month = month WHERE synced_category IS NOT NULL;
