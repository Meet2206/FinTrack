# Bank Statement → Google Sheets Expense Tracker

**Goal:** Upload a bank or credit card statement PDF. Every transaction is pulled out, checked against the statement's balances, and sorted into a category. Five categories (**Grocery, Travel, Subscriptions, Investments, Savings**) each get their own Google spreadsheet, with one tab per month that fills up as you upload more statements.

**Done looks like:** you upload last month's statement, review a few uncertain rows, click *Sync*, and the right rows appear in the right month tab of each of the 5 sheets, with totals that match the statement to the cent. Uploading the same statement again changes nothing.

---

## 1. How it works

```
  Upload statement PDF  (Streamlit UI / CLI / watched folder / later: Gmail)
          │
          ▼
  1. Open ───────── unlock if password-protected; file hash → skip if already processed
          │
          ▼
  2. Extract ────── Claude reads the PDF 4 pages at a time → list of transactions (Pydantic)
          │
          ▼
  3. Reconcile ──── opening balance + money in − money out must equal closing balance
          │          ✗ mismatch → statement goes to review, nothing is synced
          ▼
  4. Categorize ─── saved merchant rules first → Claude only for merchants it hasn't seen
          │          → Grocery | Travel | Subscriptions | Investments | Savings | Other | Not an expense
          ▼
  5. Ledger ─────── SQLite, one unique ID per transaction (duplicates impossible)
          │
          ▼
  6. Review ─────── you confirm low-confidence rows in the UI (your fixes become new rules)
          │
          ▼
  7. Sync ───────── append to the right spreadsheet → right month tab → Summary updates itself
```

### Design principles
1. **The SQLite ledger is the source of truth. Google Sheets is a view** that can be rebuilt from it at any time.
2. **Claude reads and labels; code counts and checks.** Every total comes from code or sheet formulas, never from the model.
3. **Nothing reaches Sheets unless the statement reconciles** (or you approve it manually).
4. **Repeatable:** uploading the same file twice, or two overlapping statements, never creates duplicates.

---

## 2. Google Sheets layout

Five spreadsheets, one per category, each split into monthly tabs:

```
Expenses – Grocery                          (same structure ×5)
├── Summary    Month   | Total  | # Txns
│              2026-11 | 412.30 | 18      ← formulas, update automatically
│              2026-10 | 389.95 | 21
├── 2026-11    Date | Description | Merchant | Amount | Account | Txn ID
├── 2026-10
└── 2026-09 ...

Expenses – Travel
Expenses – Subscriptions
Expenses – Investments
Expenses – Savings
(optional) Expenses – Other    ← recommended, so no spending silently disappears
```

**Rules**
- **Tab names use `YYYY-MM`** (e.g. `2026-11`). They sort correctly and can't be misread. Readable names like `Nov 2026` would also work.
- **Rows go into a month by transaction date**, not statement date. A statement covering Oct 15 – Nov 14 writes to both the `2026-10` and `2026-11` tabs.
- **Tabs are created automatically** the first time a month appears, and a matching row is added to the Summary tab (`=SUM('2026-11'!D2:D)`).
- **Older statements uploaded later** land in the correct older tab.
- **Amount:** positive = money out. A refund is a negative row in the original category, so totals net out correctly.
- **Treat the sheets as read-only.** Make changes in the app, which can rebuild any month tab from the ledger. Hand edits in Sheets would be overwritten by a rebuild.

**Setup (one time):** create the 5 spreadsheets yourself, add an empty `Summary` tab to each, and share each one with the service account's email address. Then put the spreadsheet IDs in `config.yaml`. The service account sees only those 5 files, not your whole Drive.

---

## 3. Categories

| Category | Means | Examples | Not this |
|---|---|---|---|
| **Grocery** | Food and household supplies to take home | Supermarkets, grocery delivery, markets | Restaurants and cooked-food delivery → Other |
| **Travel** | Getting around and trips | Cabs and ride-hailing, fuel, trains/metro, flights, hotels, tolls, parking | Car loan payments → Other |
| **Subscriptions** | Recurring charges for a service | Streaming, music, cloud storage, software, gym | One-off app purchases → Other |
| **Investments** | Money put into assets | Brokerage transfers, mutual fund SIPs, ETFs, stocks, crypto, retirement contributions | Insurance premiums → Other |
| **Savings** | Money set aside that stays cash-like | Transfers to your own savings account, fixed or recurring deposits, emergency fund | Transfers to other people → Other |
| **Other** | Real spending outside the five | Rent, dining, shopping, bills, healthcare | |
| **Not an expense** | Money coming in, or moving between your own accounts | Salary, interest, transfers in, **credit card bill payments** | |

Two things to keep in mind:
- **Investments and Savings aren't really expenses.** They're money set aside. The dashboard should show *Spending* (Grocery + Travel + Subscriptions + Other) separately from *Set aside* (Investments + Savings). Set aside ÷ income is your savings rate.
- **A credit card bill paid from your bank account is "Not an expense".** Otherwise everything is counted twice: once on the card statement and again as the bill payment. Upload the card statement itself to get the real purchases.

**Automatic subscription detection:** a merchant charging a similar amount roughly every 26–35 days, 3 or more times, becomes a Subscription even if no rule matches its name.

---

## 4. Reading the PDF

**Approach (v1):** send the PDF straight to Claude, which reads both text and layout, so it works across banks and even on scanned statements. Long statements are split into 4-page chunks so no single response gets too long. The reconciliation step (section 5) catches any misread number.

**Later, for your main bank:** add a free, deterministic `pdfplumber` table parser, and fall back to Claude only when reconciliation fails.

```python
# finance/extract.py
import base64, io
from pydantic import BaseModel, Field
from pypdf import PdfReader, PdfWriter
import anthropic

client = anthropic.Anthropic()


class Txn(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    description: str = Field(description="As printed; join the lines if it wraps")
    debit: float | None = Field(description="Money out, as a positive number")
    credit: float | None = Field(description="Money in, as a positive number")
    balance: float | None = Field(description="Running balance after this row, if printed")


class StatementChunk(BaseModel):
    bank_name: str | None
    account_last4: str | None
    currency: str | None = Field(description="ISO 4217 code, e.g. USD, EUR, INR")
    period_start: str | None = Field(description="YYYY-MM-DD")
    period_end: str | None = Field(description="YYYY-MM-DD")
    opening_balance: float | None = Field(description="Only if printed on these pages")
    closing_balance: float | None = Field(description="Only if printed on these pages")
    transactions: list[Txn]


RULES = """You extract transactions from bank statement pages.
- List every transaction row, in the order printed.
- Skip 'balance brought/carried forward' rows, page totals and repeated table headers.
- Copy amounts exactly as printed. Never calculate or guess a number.
- Use null for anything not shown on these pages."""


def pdf_chunks(path: str, password: str | None = None, size: int = 4):
    """Yield the PDF as base64 chunks of `size` pages. Needs `pip install pypdf[crypto]`."""
    reader = PdfReader(path)
    if reader.is_encrypted:
        reader.decrypt(password or "")
    for start in range(0, len(reader.pages), size):
        writer = PdfWriter()
        for page in reader.pages[start : start + size]:
            writer.add_page(page)
        buf = io.BytesIO()
        writer.write(buf)
        yield base64.standard_b64encode(buf.getvalue()).decode()


def extract_chunk(pdf_b64: str) -> StatementChunk:
    resp = client.messages.parse(
        model="claude-opus-5-5",
        max_tokens=16000,
        system=RULES,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                    },
                    {"type": "text", "text": "Extract the transactions on these pages."},
                ],
            }
        ],
        output_format=StatementChunk,
    )
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"Extraction stopped early: {resp.stop_reason}")
    return resp.parsed_output
```

**Merging chunks:** take header fields and the opening balance from the first chunk that has them, the closing balance from the last chunk that has it, and join the transaction lists in order.

---

## 5. Reconciliation: the accuracy guarantee

Most statements print a running balance on every row, so you can check each row individually. A wrong amount is pinpointed to the exact row, not just "something is off".

```python
# finance/reconcile.py
def reconcile(opening, closing, txns, is_card=False, tol=0.01) -> list[str]:
    """Bank account: balance goes down with debits. Credit card: balance (amount owed) goes up."""
    sign = -1 if is_card else 1
    if opening is None and txns and txns[0].balance is not None:  # derive it from row 1
        t = txns[0]
        opening = t.balance - sign * ((t.credit or 0) - (t.debit or 0))
    if opening is None:
        return ["No opening or running balance printed, so the statement can't be verified"]

    issues, bal = [], opening
    for i, t in enumerate(txns, 1):
        bal += sign * ((t.credit or 0) - (t.debit or 0))
        if t.balance is not None and abs(bal - t.balance) > tol:
            issues.append(
                f"Row {i} {t.date} '{t.description[:30]}': "
                f"expected {bal:.2f}, statement shows {t.balance:.2f}"
            )
            bal = t.balance  # resync so one bad row doesn't flag every row after it
    if closing is not None and abs(bal - closing) > tol:
        issues.append(f"Closing balance: computed {bal:.2f}, statement shows {closing:.2f}")
    return issues  # empty = statement verified
```

If it fails: show the flagged rows next to the PDF page in the UI, let the user fix them, and run the check again.

---

## 6. Categorization

Same hybrid approach as the CSV version:

1. **Saved rules first.** Build a merchant key from the description (lowercase, letters only, first 3 words), then check `config.yaml` keyword rules and rules learned earlier. This is free and instant.
2. **Claude for the rest,** about 100 transactions per call, using the category definitions from section 3 plus your past corrections in the prompt.
3. **Low confidence or "Other" goes to the review queue.** Your fixes are saved as rules, so the system learns how *you* categorize.

```python
from typing import Literal

Category = Literal["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other", "Not an expense"]


class Labeled(BaseModel):
    id: str
    merchant: str = Field(description="Clean name, e.g. 'AMZN Mktp US*2K4L9' -> 'Amazon'")
    category: Category
    confidence: Literal["high", "medium", "low"]


class Labels(BaseModel):
    items: list[Labeled]
```

After each call, check that every transaction ID came back, and retry any the model skipped.

---

## 7. No duplicates

Duplicates are blocked at two levels:

1. **Same file uploaded twice:** a SHA-256 hash of the PDF. If it's already in `statements`, stop immediately.
2. **Overlapping statements:** every transaction gets a stable ID built from account, date, amount, description and an occurrence counter. The counter keeps two identical coffees on the same day as two separate rows.

```python
import hashlib, re
from collections import Counter


def assign_ids(account: str, txns) -> list[str]:
    seen, ids = Counter(), []
    for t in txns:
        desc = re.sub(r"[^a-z0-9]", "", t.description.lower())  # ignore spacing/punctuation
        base = f"{account}|{t.date}|{t.debit}|{t.credit}|{desc}"
        seen[base] += 1
        ids.append(hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:16])
    return ids
```

The `transactions` table uses that ID as its primary key, and `synced_at` records whether a row has already been written to Sheets.

```sql
CREATE TABLE statements (
  file_hash TEXT PRIMARY KEY, bank TEXT, account_last4 TEXT,
  period_start TEXT, period_end TEXT,
  status TEXT,            -- extracted | needs_review | verified | synced
  issues TEXT, uploaded_at TEXT
);

CREATE TABLE transactions (
  id TEXT PRIMARY KEY,    -- from assign_ids(), so re-imports can't duplicate
  file_hash TEXT REFERENCES statements(file_hash),
  date TEXT, description TEXT, merchant TEXT,
  amount REAL,            -- positive = money out, negative = money in / refund
  category TEXT, confidence TEXT,
  source TEXT,            -- rule | llm | user
  synced_at TEXT          -- NULL until written to Google Sheets
);

CREATE TABLE merchant_rules (key TEXT PRIMARY KEY, merchant TEXT, category TEXT);
```

---

## 8. Syncing to Google Sheets

```python
# finance/sheets.py
from collections import defaultdict
import gspread

HEADERS = ["Date", "Description", "Merchant", "Amount", "Account", "Txn ID"]
gc = gspread.service_account(filename="service_account.json")


def month_tab(sh: gspread.Spreadsheet, month: str) -> gspread.Worksheet:
    """Get the tab for e.g. '2026-11', creating it (plus its Summary row) the first time."""
    try:
        return sh.worksheet(month)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=month, rows=500, cols=len(HEADERS), index=1)
        ws.append_row(HEADERS)
        sh.worksheet("Summary").append_row(
            [month, f"=SUM('{month}'!D2:D)", f"=COUNTA('{month}'!A2:A)"],
            value_input_option="USER_ENTERED",
        )
        return ws


def sync(txns: list[dict], sheet_ids: dict[str, str]) -> None:
    """txns: ledger rows where synced_at IS NULL. sheet_ids: {"Grocery": "<id>", ...}"""
    groups = defaultdict(list)
    for t in txns:
        if t["category"] in sheet_ids:
            groups[(t["category"], t["date"][:7])].append(
                [t["date"], t["description"], t["merchant"], t["amount"], t["account"], t["id"]]
            )

    books = {cat: gc.open_by_key(sid) for cat, sid in sheet_ids.items()}
    for (category, month), rows in sorted(groups.items()):
        ws = month_tab(books[category], month)
        ws.append_rows(sorted(rows), value_input_option="USER_ENTERED")  # one API call per tab
        # → then set synced_at for these IDs in SQLite
```

- **One write per tab, not per row.** The Sheets API has per-minute rate limits.
- **New month tabs are inserted right after Summary.** After uploading old statements, use `sh.reorder_worksheets()` to put the tabs back in order.
- **Rebuild a month:** clear the tab and rewrite it from the ledger. Use this after you change a category for a row that's already synced.

---

## 9. Alerts (from the CSV plan, still apply)

- A charge over 3× the merchant's usual amount
- A new merchant with a large charge
- Possible double charge: same merchant and amount within 2 days
- A new subscription, or a subscription price increase
- A free trial that turned into a paid charge
- A category over 1.5× its 3-month average

All of these are computed with pandas over the ledger, not by the LLM.

---

## 10. Project structure

```
finance-tracker/
├── app.py                   # Streamlit: upload, password prompt, review queue, Sync button
├── cli.py                   # python cli.py statement.pdf  (works without the UI)
├── config.yaml              # sheet IDs, keyword rules, thresholds
├── finance/
│   ├── extract.py           # unlock + split PDF, Claude → StatementChunk
│   ├── reconcile.py         # balance checks
│   ├── ledger.py            # SQLite, transaction IDs, dedupe
│   ├── categorize.py        # rules → Claude → review queue
│   ├── sheets.py            # monthly tabs, batch appends, Summary rows, rebuild
│   └── alerts.py            # spikes, double charges, subscriptions
├── scripts/setup_sheets.py  # checks the 5 spreadsheets have a Summary tab with headers
├── tests/                   # fake statements only, never real ones
├── data/                    # gitignored: statement PDFs + ledger.db
├── .env                     # gitignored: ANTHROPIC_API_KEY, statement passwords
└── service_account.json     # gitignored: Google credentials
```

```yaml
# config.yaml
sheets:                 # spreadsheet IDs (the long part of each sheet's URL)
  Grocery: "…"
  Travel: "…"
  Subscriptions: "…"
  Investments: "…"
  Savings: "…"
  # Other: "…"          # optional 6th sheet

rules:                  # whole-word, case-insensitive matches, checked before calling Claude
  Grocery: [supermarket, grocery, groceries, hypermarket]
  Travel: [uber, lyft, airline, airways, railway, metro, hotel, fuel, parking, toll]
  Subscriptions: [netflix, spotify, icloud, adobe, gym]
  Investments: [mutual fund, sip, brokerage, etf, stocks]
  Savings: [fixed deposit, recurring deposit, to savings]

review:
  confidence_below: medium     # rows below this wait for you before syncing
  large_charge: 200
```

Keep secrets out of this file. Statement passwords belong in `.env` or the macOS Keychain (Python `keyring` package).

---

## 11. Build phases

| # | Build | Done when |
|---|---|---|
| 1 | CLI: PDF → transactions JSON + reconciliation | 3 real statements from your bank reconcile to the cent |
| 2 | SQLite ledger + transaction IDs | Uploading the same statement twice adds 0 rows |
| 3 | Categorization (rules + Claude) | At least 95% correct on 150 transactions you labeled by hand |
| 4 | Google Sheets sync | All 5 sheets fill in with monthly tabs, and Summary totals match the ledger |
| 5 | Streamlit UI + review queue | You can upload, fix rows and sync without touching code |
| 6 | Automation + alerts | A new statement in a folder or email reaches Sheets with no clicks, plus a monthly summary message |

---

## 12. Edge cases checklist

- [ ] Password-protected PDFs (most emailed statements): ask once, store in `.env` or Keychain
- [ ] Scanned, image-only PDFs: Claude reads the images, and reconciliation catches misreads
- [ ] Descriptions that wrap onto 2–3 lines
- [ ] Repeated table headers, "brought forward" rows, page subtotals
- [ ] DD/MM vs MM/DD dates: infer from the statement period, then save per bank
- [ ] A statement spanning two months: split by transaction date
- [ ] Re-uploads and overlapping statements: file hash + transaction IDs
- [ ] Credit card statements: balance rises with spending, so `is_card=True`
- [ ] Credit card bill payments from the bank account: "Not an expense"
- [ ] Refunds and reversals: negative amount in the original category
- [ ] Failed transactions (debit, then the same amount credited back the same day): flag them
- [ ] Foreign currency charges and the fees that come with them
- [ ] Several accounts in one PDF
- [ ] Very long statements (300+ rows): chunking + reconciliation across chunks

---

## 13. Privacy and security

- A statement contains your **name, address and account number**. In v1 the PDF is sent to the Claude API and nowhere else.
- **Privacy mode (later):** extract the text locally with `pdfplumber`, blank out account numbers and the address, and send only the text. More private, but less reliable on unusual layouts.
- Add `data/`, `.env` and `service_account.json` to `.gitignore` **on day one**.
- Keep the 5 spreadsheets private. The service account gets access to those files only.
- Tests use **made-up statements**, never real ones.

---

## 14. Cost (rough)

- **Extraction:** about 10–25¢ for a typical 5-page statement on Claude Opus 5.5 ($4 / $20 per million input / output tokens)
- **Categorization:** a few cents per statement, falling toward zero as merchant rules build up
- **Google Sheets API:** free
- **2–3 statements a month:** well under $1

---

## 15. Stretch ideas

- Fetch statements from Gmail automatically (bank sender + PDF attachment)
- An **Overview** spreadsheet: a months × categories table with a chart and your savings rate
- Category budgets with a phone notification at 80% (e.g. via Telegram)
- Ask questions in plain English ("How much did I spend on travel in Q3?") over the ledger
- Match receipts from the invoice extractor to statement rows
- A free `pdfplumber` parser for your main bank, with Claude as the fallback

---

## 16. Open questions (decide before Phase 4)

1. **Sheet layout:** 5 spreadsheets with monthly tabs (this plan, as requested), or 1 spreadsheet with 5 tabs plus a Month column? The single file is easier to filter, pivot and share.
2. **Spending outside the 5 categories:** a 6th "Other" sheet (recommended) or don't write it anywhere?
3. **Restaurants and food delivery:** Grocery or Other?
4. **Fuel, parking, tolls:** Travel?
5. **Phone/internet plans and gym:** Subscriptions?
6. **Insurance premiums and loan payments:** Other?
7. **One currency or several?**
8. **Which bank first?** Collect 2–3 sample statements for Phase 1.
