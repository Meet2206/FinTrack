# FinTrack plan

## Current outcome

FinTrack is a local-first financial automation tool. It reads supported bank
statement PDFs, validates balances, categorizes transactions, suggests
conservative savings opportunities, and syncs approved data to one FinTrack
Google Sheet.

## Product goals

- Replace repetitive statement-to-spreadsheet data entry.
- Make every imported total auditable against the bank's printed balances.
- Keep the local ledger as the source of truth.
- Make suggestions explainable instead of pretending to make decisions for the
  user.
- Make Google Sheets sync repeatable and safe to retry.

## Completed

- Local PDF extraction for the supplied bank statement formats.
- Balance reconciliation and mismatch reporting.
- Duplicate statement and transaction protection.
- Saved merchant rules, keyword categorization, and Review workflow.
- Dashboard, alerts, category summaries, and all-transaction view.
- Money suggestions for category concentration, recurring charges, repeated
  merchants, and missing set-asides.
- Single-workbook Google Sheets layout with Summary and month tabs.
- Folder/inbox processing and monthly summaries.

## Next useful enhancements

1. OCR for scanned image-only PDFs.
2. Per-category budgets and threshold alerts.
3. Optional receipt matching.
4. Gmail attachment ingestion with explicit user authorization.
5. A dry-run preview of Sheet changes before sync.

## Non-goals

FinTrack will not move money, cancel subscriptions, place investments, or
replace a bank's own records. It is a tracking and review assistant, not a
financial adviser.
