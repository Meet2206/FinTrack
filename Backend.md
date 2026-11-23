# FinTrack backend

This document describes the current local backend. For the product workflow
and automation justification, see [AUTOMATION.md](AUTOMATION.md).

## Runtime flow

`finance.pipeline.process_statement()` coordinates the backend:

1. `pdf_tools` opens the PDF, unlocks it when needed, and fingerprints it.
2. `extract` reads supported text-based layouts into validated transaction
   rows and statement metadata.
3. `reconcile` checks each balance transition and identifies the first bad row.
4. `ledger` stores the statement and deduplicated transactions in SQLite.
5. `categorize` applies saved merchant rules, configured keywords, and local
   heuristics.
6. `alerts` records unusual charges and merchant changes.
7. `suggestions` produces conservative, explainable savings opportunities.
8. `sync` rebuilds the configured FinTrack Google Sheet after review.

## Important modules

| Module | Purpose |
|---|---|
| `finance/config.py` | Typed settings and category definitions |
| `finance/pdf_tools.py` | PDF passwords, fingerprints, and archival |
| `finance/extract.py` | Local statement parsing and format detection |
| `finance/reconcile.py` | Balance arithmetic and mismatch reporting |
| `finance/ledger.py` | SQLite schema, queries, review and sync state |
| `finance/categorize.py` | Deterministic category assignment |
| `finance/suggestions.py` | Spending concentration, recurring charge, and set-aside suggestions |
| `finance/sync.py` | Google Sheets synchronization orchestration |
| `finance/sheets.py` | Workbook and monthly-tab writes |

## Database boundary

The SQLite ledger is the source of truth. Google Sheets is a rebuildable mirror.
This makes retries safe: a failed sync does not require reprocessing the PDF,
and a later sync can reconstruct the affected month tabs from the ledger.

## Configuration

Copy `config.example.yaml` to `config.yaml`. The important local-first values
are:

```yaml
offline_mode: true
currency: INR
fintrack_spreadsheet_id: "your-spreadsheet-id"
service_account_file: service_account.json
auto_sync: false
```

The service-account JSON must be kept private, and its `client_email` must be
shared on the target Google Sheet as an Editor. A client ID alone cannot write
to a Sheet.

## CLI and web entry points

```bash
streamlit run app.py --server.address 127.0.0.1
python cli.py process path/to/statement.pdf
python cli.py review
python cli.py sync
python cli.py check
```

## Error handling

- Unsupported or unreadable PDFs fail before rows are saved.
- Balance mismatches are held for review and show the affected row.
- Unknown or low-confidence categories remain visible for correction.
- Google authorization errors leave local data intact and can be retried.
- Suggestions are informational and never change bank or Sheet data.

## Verification

Run:

```bash
.venv/bin/ruff check app.py finance pages
.venv/bin/python -m pytest -q
```

The automated suite uses fake PDFs and an in-memory Sheets implementation, so
it does not spend money or write to a real account.
