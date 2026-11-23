# FinTrack architecture

FinTrack is a local-first statement-processing and budgeting workflow. The
current production path does not require a paid AI service or an external AI
API.

## Data flow

```text
PDF upload / data inbox
        │
        ▼
PDF tools ── unlock, fingerprint, extract text
        │
        ▼
Local parser ── dates, descriptions, money in/out, balances
        │
        ▼
Reconciliation ── opening balance + rows = closing balance
        │
        ├── mismatch ──► hold statement and show the problem row
        │
        ▼
Local categorizer ── saved rules → keywords → heuristics
        │
        ▼
SQLite ledger ── deduplicated transactions, review state, alerts
        │
        ├── Dashboard / money suggestions
        ├── Review page
        └── approved sync ──► FinTrack Google Sheet
```

## Components

| Component | Responsibility | Main files |
|---|---|---|
| Streamlit app | Upload, process, review, dashboard | `app.py`, `pages/` |
| CLI | Process, review, sync, checks from a terminal | `cli.py` |
| PDF tools | Unlock, fingerprint, copy and archive PDFs | `finance/pdf_tools.py` |
| Local extractor | Parse supported text-based bank layouts | `finance/extract.py` |
| Reconciler | Verify every balance transition to the cent | `finance/reconcile.py` |
| Categorizer | Apply saved merchant rules and local rules | `finance/categorize.py` |
| Suggestions | Explain spending opportunities from ledger rows | `finance/suggestions.py` |
| Ledger | Persist statements, transactions, rules and sync state | `finance/ledger.py` |
| Sheets mirror | Rebuild monthly tabs and Summary | `finance/sheets.py`, `finance/sync.py` |

## Processing guarantees

- A repeated statement fingerprint is not imported twice.
- A balance mismatch prevents the statement from being treated as ready.
- Uncertain rows remain in Review instead of being silently accepted.
- Google Sheets sync is idempotent: it rebuilds affected month tabs from the
  local ledger.
- Suggestions never execute an action. They only explain a possible saving.

## Google Sheets layout

With `fintrack_spreadsheet_id` configured, sync creates or updates:

```text
FinTrack
├── Summary
├── 2026-09
├── 2026-10
└── 2026-11
```

Each month tab contains Category, Date, Merchant, Description, Money out,
Money in, Net, and the source transaction fields. Summary contains Month,
Category, Total, and Transactions.

## Privacy boundary

PDF parsing, reconciliation, categorization, alerts, suggestions, and the
SQLite ledger run locally. The only configured external write is the explicit
Google Sheets sync. The app never moves money or changes a bank account.

See [AUTOMATION.md](AUTOMATION.md) for the use case, monthly routine, safety
justification, and folder automation workflow.
