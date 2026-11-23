# Testing FinTrack

The test suite is designed to run locally without paid services, real bank
accounts, or writes to the user's Google Sheet.

## Run the checks

```bash
.venv/bin/ruff check app.py finance pages tests/test_suggestions.py
.venv/bin/python -m pytest -q
```

The suite covers PDF extraction, balance reconciliation, duplicate protection,
local categorization, review workflows, alerts, money suggestions, Google
Sheets sync decisions, CLI commands, and Streamlit pages.

## What is verified

- Supported statement formats produce transactions with correct dates and
  money-in/money-out values.
- Opening balance plus every row equals the printed closing balance.
- A corrupt or non-statement PDF fails clearly and safely.
- Re-uploading the same statement does not duplicate rows.
- Category rules are deterministic and user corrections are remembered.
- Suggestions are conservative, explainable, and never execute financial
  actions.
- Google Sheets writes are tested with an in-memory fake workbook.
- Every page renders with both populated and empty databases.

## Manual test with the supplied statements

1. Start the app: `streamlit run app.py --server.address 127.0.0.1`.
2. Upload a PDF from `Bank Statements/` or `statement_034.pdf`.
3. Click **Process** and confirm the balance check.
4. Check **Finances by category**, **Money suggestions**, and **All
   transactions**.
5. Review uncertain rows, then sync only after authorization is configured.

Scanned image-only PDFs may need OCR in a future enhancement. Until then, the
balance check and Review page are the safety gates for every sync.
