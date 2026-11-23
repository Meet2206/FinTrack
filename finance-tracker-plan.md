# FinTrack project plan

This file is the implementation plan and roadmap. The public project
introduction is [README.md](README.md); the exact automation workflow is in
[AUTOMATION.md](AUTOMATION.md).

## Current product

FinTrack turns bank statement PDFs into a validated local ledger and an
organized Google Sheet. The local path is intentionally deterministic:

```text
PDF → extract locally → reconcile balances → categorize locally
    → review uncertain rows → suggestions → sync approved rows
```

The goal is simple: stop copying transactions into spreadsheets by hand every
month while keeping financial decisions with the human who owns the account.

> **MEME:** “I will track every expense manually this month.”
>
> **Narrator:** They did not.

## Completed

- Local extraction for the supplied text-based Indian-style statements
- Password handling, statement fingerprints, and duplicate transaction IDs
- Opening/closing balance reconciliation to the cent
- Merchant rules, keyword categorization, and Review workflow
- Category totals and full transaction table after processing
- Alerts for unusual charges and merchant behavior
- Explainable savings suggestions
- Single-workbook Google Sheets sync with Summary and monthly tabs
- Inbox/folder processing and monthly summary support
- Automated test coverage for pipeline, UI, suggestions, and sync behavior

## Why this is useful automation

The repetitive parts are mechanical: reading rows, checking arithmetic,
grouping merchants, spotting recurring charges, and rebuilding monthly tabs.
Automating those steps creates a consistent two-minute monthly routine.

> **MEME:** The spreadsheet has entered the chat. It brought charts, receipts,
> and questions about the 19 food-delivery charges.

The app deliberately does not automate money movement, subscription
cancellation, investment selection, or approval of questionable transactions.
That boundary is important: “automated bookkeeping” is useful; “robot decides
what to do with my salary” is how a documentary starts.

## Google Sheets target

The current recommended layout is one workbook:

```text
FinTrack
├── Summary       Month | Category | Total | Transactions
├── 2026-09      categorized transaction rows
├── 2026-10      categorized transaction rows
└── 2026-11      categorized transaction rows
```

The service account must be shared as an Editor. A client ID alone cannot
authorize writes. SQLite remains the source of truth and the Sheet is a
rebuildable mirror.

## Current suggestions engine

Suggestions are local heuristics, not advice. They can identify:

1. A category using a large share of spending and estimate a modest 10% trim.
2. Multiple or expensive subscription charges to review.
3. Repeated high-value merchants where a spending cap may help.
4. Income with no Savings or Investments transfer detected.

Every suggestion includes the observed amount and explains the estimate. The
user chooses whether it makes sense.

> **MEME:** “It is not a spending problem; it is a temporary liquidity event.”
> FinTrack files it under **Other** and quietly shows the total.

## Roadmap

1. OCR support for scanned image-only PDFs.
2. Per-category budgets and threshold alerts.
3. Receipt matching.
4. Explicitly authorized email attachment ingestion.
5. Dry-run preview of Google Sheets changes before sync.
6. More bank-layout fixtures and currency edge cases.

## Product principles

- Local-first and free to run for supported text PDFs.
- Reconciliation before sync.
- Review before uncertain data leaves the ledger.
- User corrections become deterministic rules.
- No destructive financial actions.
- A failed sync is retryable.
- The bank statement wins arguments with the app.

## Sarcastic test cases

- **MEME:** “The subscription is basically free.” Check the monthly total.
- **MEME:** “That ₹300 purchase was a one-off.” Check whether the merchant
  appears twelve times.
- **MEME:** “I will remember what this charge was.” That is why Review exists.
- **MEME:** “The balance looks right-ish.” Reconciliation requires exact cents.
