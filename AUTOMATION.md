# FinTrack automation

FinTrack is a local-first financial workflow: a statement enters as a PDF, the
app validates and categorizes it on the computer, and the approved result can
be copied to Google Sheets. The workflow is useful as automation because it
removes repetitive data entry while keeping the review and spending decisions
under your control.

## What is automated

1. **Ingest** — accept one or more bank or card statement PDFs, including locked
   PDFs when a password is supplied.
2. **Extract** — read text-based statement layouts locally and turn rows into
   dates, descriptions, money in, money out, and balances.
3. **Validate** — replay every transaction against the opening and closing
   balances. A mismatch stops the statement from being treated as trustworthy.
4. **Deduplicate** — fingerprint statements and transactions so re-uploading a
   file does not create a second copy.
5. **Categorize** — apply saved merchant rules first, then local keyword and
   heuristic rules. Uncertain rows remain visible in Review.
6. **Advise** — show explainable suggestions based on the current statement,
   such as recurring subscriptions, repeated merchants, category concentration,
   and the absence of Savings or Investments transfers.
7. **Sync** — after review, write approved rows into the configured FinTrack
   Google Sheet, partitioned into a Summary tab and monthly tabs with a
   Category column.

## Why automate it

The highest-value work is repetitive and rules-based: copying hundreds of
rows, checking arithmetic, finding duplicate uploads, and grouping merchants.
Automating those steps gives you a consistent monthly process and leaves the
important judgment calls—whether a charge is correct, whether a suggestion is
realistic, and what to change—to you.

This is deliberately not an auto-money-moving system. It does not transfer
funds, cancel subscriptions, or make investment decisions. Suggestions are
conservative estimates, not financial advice, and Google Sheets sync occurs
only after the statement passes validation and any required review.

## Recommended monthly routine

1. Drop the new PDF into the app or into `data/inbox/` when folder processing
   is enabled.
2. Process it and confirm the balance check.
3. Review any uncertain rows and correct categories when needed.
4. Read the suggestions; choose only actions that fit your actual budget.
5. Sync to Google Sheets and use the Dashboard to compare months.

## Google Sheets layout

Single-workbook mode uses the spreadsheet ID in `fintrack_spreadsheet_id`:

```text
FinTrack
├── Summary       Month | Category | Total | Transactions
├── 2026-09      Category | Date | Merchant | Description | Money out | Money in | Net | ...
├── 2026-10
└── 2026-11
```

The service account must be shared on the target spreadsheet as an Editor.
The client ID by itself is not permission to write; the service-account JSON
and sharing step are what authorize the sync.

## Safety and limits

- Processing and suggestions work without a paid AI service or external AI API.
- Google Sheets is the only external destination used for sync.
- The app never moves money or changes a bank account.
- Keep the local database and service-account JSON private.
- Scanned image-only PDFs may need a future OCR step; always rely on the
  balance check and Review before syncing.
