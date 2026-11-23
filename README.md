# 💸 FinTrack

### Upload a bank statement. Find out where the money went. Pretend this was the plan all along.

FinTrack is a local-first personal-finance tracker for bank and card statement
PDFs. It extracts transactions, checks the statement arithmetic, categorizes
spending, suggests realistic savings opportunities, and syncs approved data to
your Google Sheet.

> **MEME:** “I barely spent anything.”
>
> **Plot twist:** the Dashboard has receipts.

<p align="center">
  <img src="https://api.memegen.link/images/fine/Bank_balance_after_one_weekend/This_is_fine.gif" width="460" alt="MEME: bank balance after one weekend — this is fine">
</p>

## What it does

- Reads supported text-based bank and card statement PDFs locally
- Handles password-protected PDFs through the local Keychain workflow
- Reconciles opening balance + money in − money out against the closing balance
- Prevents duplicate statements and duplicate transactions
- Categorizes Grocery, Travel, Subscriptions, Investments, Savings, Other,
  and Not an expense
- Learns merchant categories from your corrections
- Shows category totals and all finances after **Process**
- Suggests conservative savings opportunities with supporting evidence
- Syncs approved transactions to a FinTrack Google Sheet
- Runs without a paid AI service or external AI API

> **MEME:** Upload one PDF instead of typing 200 transactions into a
> spreadsheet. Your future self sends a thank-you note. It is probably still
> waiting for you to cancel that gym subscription.

## How it works

```text
PDF upload / data inbox
        ↓
Local extraction → balance reconciliation → local categorization
        ↓                         ↓
Review uncertain rows       stop mismatches safely
        ↓
Money suggestions → approved Google Sheets sync
```

The app automates repetitive bookkeeping, not financial decisions. It does not
move money, cancel subscriptions, place investments, or silently “fix” a
questionable transaction.

> **MEME:** The app says “review this charge.” You say “I know exactly what
> this is.” The app says “then why is it in Other?”

## Money suggestions

FinTrack can identify a category consuming a large share of spending,
recurring subscriptions worth reviewing, repeated merchants that may need a
cap, and income with no visible Savings or Investments transfer. Suggestions
show the evidence and a modest estimate; they are not financial advice.

> **MEME:** “It was only ₹300.” — said twelve times in one month.

<p align="center">
  <img src="https://media.giphy.com/media/12XMGIWtrHBl5e/giphy-downsized.gif" width="320" alt="MEME: discovering the monthly spending total">
</p>

## Google Sheets layout

Configure `fintrack_spreadsheet_id` and share the target sheet with the service
account as an Editor:

```text
FinTrack
├── Summary       Month | Category | Total | Transactions
├── 2026-09      categorized transaction rows
├── 2026-10      categorized transaction rows
└── 2026-11      categorized transaction rows
```

SQLite is the source of truth and Sheets is a rebuildable mirror, so a failed
sync can be retried without re-uploading the PDF.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
streamlit run app.py --server.address 127.0.0.1
```

Open `http://127.0.0.1:8501`, upload a PDF, and click **Process**.

```bash
python cli.py process path/to/statement.pdf
python cli.py review
python cli.py sync
python cli.py check
```

## Monthly routine

1. Upload the new statement.
2. Confirm the balance check passes.
3. Review uncertain rows.
4. Read the suggestions and choose only sensible actions.
5. Sync to Google Sheets.
6. Open the Dashboard and discover which “small” purchases formed a small army.

See [AUTOMATION.md](AUTOMATION.md) for the exact workflow and safety
justification.

## Documentation

- [AUTOMATION.md](AUTOMATION.md) — workflow, use cases, safety boundaries
- [Architecture.md](Architecture.md) — current system design and data flow
- [Backend.md](Backend.md) — modules, configuration, and error handling
- [TESTING.md](TESTING.md) — local test strategy and verification
- [finance-tracker-plan.md](finance-tracker-plan.md) — roadmap and future work

## Testing

```bash
.venv/bin/ruff check app.py finance pages
.venv/bin/python -m pytest -q
```

The project currently has **212 passing tests** using fictional statements and
fake Sheets, so tests do not spend money or touch a real account.

## Privacy and safety

- PDFs, the SQLite ledger, categories, alerts, and suggestions run locally.
- Only explicit Google Sheets sync writes data externally.
- Keep `config.yaml`, `.env`, `service_account.json`, and `data/` private.
- The bank statement remains the source of truth.

> **Disclaimer:** FinTrack is a personal tracking tool, not financial, tax, or
> investment advice. If it says “you may want to save money,” it is making a
> suggestion—not presenting Exhibit A: your food-delivery history.
