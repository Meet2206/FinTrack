# ⚙️ Backend

[Readme](Readme.md) · [Plan](Plan.md) · [Architecture](Architecture.md) · **Backend** · [DB](DB.md) · [Testing](TESTING.md) · [Reason](Reason.md)

| | |
|---|---|
| **What this document is** | How the engine works: setup, settings, every module with reference code, the command line, the web app, error handling and testing. |
| **Who it's for** | Developers building it, plus anyone curious. Each part starts with a 💡 plain-English summary, so you can skip the code and still follow along. |
| **Status** | ✅ Built (v1.0). The real code lives in `finance/`, `cli.py`, `app.py` and `pages/`. Snippets below are simplified excerpts: when they differ, the code wins. |

---

## 1. What "backend" means here

> 💡 **In plain English:** the backend is the **engine room**: the Python code that does all the real work (opening PDFs, talking to Claude, checking math, saving records, updating Google Sheets). It has no screens. The web app and the command line are just *buttons* that ask the engine to do things.

```
   Web app (Streamlit)  ─┐
   Command line (Typer) ─┼──▶  finance/  (the engine)  ──▶  SQLite · Claude API · Google Sheets API
   Folder watcher (P6)  ─┘
```

**Rule:** all logic lives in `finance/`. `app.py` and `cli.py` stay thin: they collect input, call the engine, and show the result.

---

## 2. Libraries

| Library | 💡 What it does for us | Used in |
|---|---|---|
| `anthropic` | Talks to Claude | `extract.py`, `categorize.py` |
| `pydantic` (v2) | Defines the "forms" the AI must fill in, and validates settings | everywhere |
| `pypdf[crypto]` | Opens, unlocks and splits PDFs (`[crypto]` adds support for encrypted PDFs) | `pdf_tools.py` |
| `gspread` | Writes to Google Sheets | `sheets.py` |
| `pandas` | Table calculations for alerts and the dashboard | `alerts.py`, `app.py` |
| `streamlit`, `plotly` | Web screens and charts | `app.py`, `pages/` |
| `typer` | Command-line commands | `cli.py` |
| `pyyaml`, `python-dotenv` | Read `config.yaml` and `.env` | `config.py` |
| `keyring` | Saves PDF passwords in the macOS Keychain | `pdf_tools.py`, `cli.py` |
| `watchdog` | Watches a folder for new PDFs (Phase 6) | `watcher.py` |
| `pytest`, `reportlab` | Tests, and generating fake statement PDFs | `tests/`, `scripts/` |
| `sqlite3`, `hashlib`, `re` | Database, fingerprints, text matching | built into Python |

`requirements.txt`:

```text
anthropic
pydantic>=2
pypdf[crypto]
gspread
pandas
plotly
streamlit
typer
pyyaml
python-dotenv
keyring
watchdog
pytest
reportlab
```

> After the first successful install, run `pip freeze > requirements.lock` and commit it, so every future install gets the exact same versions.

---

## 3. Folder structure

```
meet-project/
├── Readme.md  Plan.md  Architecture.md  Backend.md  DB.md  TESTING.md  Reason.md
├── app.py                      # Web app: Upload page (home)
├── ui_common.py                # Shared page setup + sidebar (sync button, counts)
├── pages/
│   ├── 1_Review.py             # Review queue
│   ├── 2_Dashboard.py          # Charts, totals, subscriptions, alerts
│   ├── 3_Transactions.py       # Browse and fix any row
│   ├── 4_Statements.py         # Every statement, mismatches, retries, forget
│   └── 5_Setup.py              # Checklist, AI costs, saved rules, backups
├── cli.py                      # Command line: process, sync, status, costs… (python cli.py --help)
├── config.example.yaml         # Settings template → copy to config.yaml
├── config.yaml                 # 🔒 Your settings (gitignored: holds your sheet IDs)
├── .env.example                # Secrets template → copy to .env
├── .env                        # 🔒 Secret: ANTHROPIC_API_KEY (+ optional Telegram)
├── service_account.json        # 🔒 Secret: Google robot key
├── requirements.txt
├── pyproject.toml              # pytest + ruff settings
├── finance/                    # ⚙️ THE ENGINE
│   ├── config.py               # Load and validate settings
│   ├── pdf_tools.py            # Fingerprint, unlock (Keychain), split PDFs
│   ├── extract.py              # Claude reads pages → transactions
│   ├── reconcile.py            # Check the math
│   ├── ids.py                  # Transaction and merchant fingerprints
│   ├── categorize.py           # Rules → keywords → Claude
│   ├── ledger.py               # All database reads and writes
│   ├── migrations/             # 001_init.sql, 002_synced_month.sql (see DB.md)
│   ├── sheets.py               # Google Sheets mirror
│   ├── sync.py                 # Decide which tabs to rebuild, then rebuild them
│   ├── alerts.py               # Double charges, price increases, forgotten subscriptions…
│   ├── costs.py                # Track what each AI call cost
│   ├── pipeline.py             # The manager: runs every step in order
│   ├── summary.py              # Monthly summary text + Telegram
│   ├── watcher.py              # Automation: process data/inbox/ (once, or keep watching)
│   ├── setup_check.py          # The setup checklist (cli check / Setup page)
│   └── demo.py                 # Fake statements + a pretend Claude (tests and demo)
├── scripts/
│   ├── demo.py                 # Build a no-key demo in demo/
│   ├── check_setup.py          # Same as: python cli.py check
│   ├── make_test_fixtures.py   # Re-create tests/fixtures/*.pdf
│   ├── make_fake_statement.py  # Generate a fake statement PDF (never use real ones)
│   └── eval_categories.py      # Measure categorization accuracy (real API)
├── conftest.py                 # The plain-English report: python -m pytest --report TESTING.md
├── tests/                      # 206 tests (+19 live): see TESTING.md
│   ├── conftest.py             # Temp database, fake sheets, in-memory Keychain
│   ├── scenarios.py            # 34 real-life statement scenarios + pretend Claudes
│   ├── fake_gspread.py         # An in-memory imitation of Google Sheets
│   ├── test_scenarios.py       # Every scenario end to end, plus multi-upload cases
│   ├── test_core.py            # Math check, fingerprints, rules, settings, PDFs
│   ├── test_pipeline.py        # PDF → database → sheets flows
│   ├── test_categorization.py  # Rules, keywords, AI, review, batching
│   ├── test_sheets_mirror.py   # The real Sheets writer + database upgrades
│   ├── test_alerts.py          # Every alert rule on both sides of its threshold
│   ├── test_cli.py             # Every command
│   ├── test_settings_and_automation.py
│   ├── test_app.py             # Every web page and its buttons
│   ├── test_live.py            # The real Claude (opt-in)
│   ├── fixtures/               # 18 fake statement PDFs + README (safe to share)
│   └── data/labeled.example.csv
└── data/                       # 🔒 Private, never committed
    ├── inbox/                  # Drop PDFs here (done/ and failed/ inside)
    ├── statements/             # Stored copies of processed PDFs
    ├── backups/                # Automatic database backups
    ├── logs/app.log
    └── ledger.db               # The database
```

`.gitignore` (already in the project; it was created **before the first commit**):

```gitignore
# ── Secrets: never commit these ──────────────────────────
.env
service_account.json
config.yaml

# ── Your private financial data ──────────────────────────
/data/
*.pdf
tests/data/labeled.csv

# ── Python ───────────────────────────────────────────────
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.DS_Store

# ── Demo (python scripts/demo.py) ─────────────────────────
demo/
```

---

## 4. Setup, step by step

> 💡 **In plain English:** a one-time checklist (about 30–45 minutes) to get keys and sheets ready. No coding needed for this part.

> ⚠️ **Tip:** this project folder's name currently ends with a space (`"meet-project "`). That's easy to trip over in the terminal, so rename it to `meet-project` before starting.

### Step 1: Install Python
1. Open **Terminal**.
2. Run `python3 --version`. You need **3.12 or newer**.
3. If it's older or missing: install from [python.org](https://www.python.org/downloads/), or `brew install python@3.12` if you use Homebrew.

### Step 2: Create the project environment
```bash
cd ~/Documents/meet-project
python3 -m venv .venv            # a private box for this project's libraries
source .venv/bin/activate        # step into the box (run this every new terminal)
pip install -r requirements.txt  # install the libraries
cp config.example.yaml config.yaml
cp .env.example .env
```

### Step 3: Get a Claude API key
1. Sign in to the **Claude Console** (platform.claude.com) and add a payment method or credits.
2. Go to **API Keys** → **Create Key** and copy it (it starts with `sk-ant-`).
3. Open the `.env` file in the project folder and fill in:
   ```bash
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
4. 💡 **Recommended:** set a monthly **spend limit** in the Console (e.g. $5), so a bug can never cost much.

### Step 4: Create the Google "robot" account (service account)
1. Go to **console.cloud.google.com** and create a project (e.g. `money-tracker`).
2. **APIs & Services → Library** → search **Google Sheets API** → **Enable**.
3. **APIs & Services → Credentials → Create credentials → Service account**. Name it `sheets-robot` and click **Done** (skip the optional steps).
4. Click the new service account → **Keys → Add key → Create new key → JSON**. A file downloads.
5. Rename it to `service_account.json` and move it into the project folder.
6. Open it and copy the `client_email` value (it looks like `sheets-robot@money-tracker.iam.gserviceaccount.com`). That's the robot's email address.

### Step 5: Create the 5 spreadsheets
For each of **Grocery, Travel, Subscriptions, Investments, Savings**:
1. In Google Sheets, create a new spreadsheet named `Expenses – Grocery` (and so on).
2. Rename the first tab (bottom left) to exactly **`Summary`**.
3. Click **Share**, paste the robot's email, choose **Editor**, untick "Notify people", and click **Share**.
4. Copy the **spreadsheet ID** from the address bar: the long code between `/d/` and `/edit`.
   `https://docs.google.com/spreadsheets/d/`**`1AbCdEfGh...`**`/edit`

### Step 6: Fill in `config.yaml`
Paste the 5 IDs into `config.yaml` (full reference in [§5](#5-configuration)).

### Step 7: Save PDF passwords (if your statements are locked)
```bash
python cli.py password add mainbank      # asks for the password, stores it in the Keychain
```
That's it: the app tries every saved password automatically, so you won't be asked again. (In the web app, tick **Remember this password** instead.) `python cli.py password list` shows the names, never the passwords.

### Step 8: Check everything
```bash
python cli.py check            # or: python scripts/check_setup.py
```
```
✅ Python 3.12.7
✅ .env found, Claude API key works
✅ service_account.json found (robot: sheets-robot@money-tracker.iam.gserviceaccount.com)
✅ Grocery sheet opens, Summary tab found
✅ Travel sheet opens, Summary tab found
❌ Savings sheet: permission denied → share it with sheets-robot@money-tracker.iam.gserviceaccount.com
✅ data/ folder is writable
✅ .gitignore protects .env, service_account.json and data/
```
`check_setup.py` checks the Claude key with `client.models.list()`, which is free, and opens each spreadsheet with `gspread`.

### Step 9: Run it
```bash
python cli.py process ~/Downloads/statement_nov.pdf     # command line
streamlit run app.py --server.address localhost          # web app → http://localhost:8501
```

---

## 5. Configuration

> 💡 **In plain English:** `config.yaml` holds your **settings** (safe to read, shouldn't hold secrets). `.env` holds your **secrets** (never shared, never committed).

### `config.yaml` (full reference)

```yaml
# Where Did My Money Go? settings
# Copy this file to config.yaml and fill it in:  cp config.example.yaml config.yaml
# Settings only. Secrets (API keys) go in .env, PDF passwords in the Keychain.

# ─── Google Sheets ───────────────────────────────────────────────────────
# Spreadsheet IDs: the long code in each sheet's URL between /d/ and /edit
# Leave a category out (or the whole block empty) until you've set it up.
sheets:
  Grocery: ""
  Travel: ""
  Subscriptions: ""
  Investments: ""
  Savings: ""
  # Other: ""                     # remove the # to turn on the optional 6th sheet

service_account_file: service_account.json

# ─── Money ───────────────────────────────────────────────────────────────
currency: USD                     # your statements' currency (USD, EUR, INR, GBP…)

# ─── AI ──────────────────────────────────────────────────────────────────
model: claude-opus-5-5
pages_per_chunk: 3                # pages sent to Claude per request
categorize_batch_size: 100        # transactions per categorization request
pricing_per_million_tokens:       # only used for the cost log; check current prices
  claude-opus-5-5: { input: 4.00, output: 20.00 }

# ─── Keyword rules: checked BEFORE asking the AI ─────────────────────────
# Whole words, any capitalization. Checked top to bottom; first match wins.
keywords:
  Subscriptions: [netflix, spotify, icloud, adobe, gym]
  Travel: [uber, lyft, airline, airways, railway, metro, hotel, fuel, parking, toll]
  Grocery: [supermarket, grocery, groceries, hypermarket]
  Investments: [mutual fund, sip, brokerage, etf]
  Savings: [fixed deposit, recurring deposit]
  Not an expense: [salary, payroll]   # also add your credit card's bill-payment wording here

# ─── Review ──────────────────────────────────────────────────────────────
review:
  review_if_confidence: [low, medium]   # AI answers at these levels wait for you
  large_charge: 200                      # first-ever charge from a shop above this → alert

# ─── Automation ──────────────────────────────────────────────────────────
auto_sync: false                  # inbox/watch: sync to Google Sheets right after processing

# ─── Files (relative to this config file) ────────────────────────────────
db_path: data/ledger.db
statements_dir: data/statements
backups_dir: data/backups
inbox_dir: data/inbox
logs_dir: data/logs
```

### `.env`

| Variable | Required | What it is |
|---|---|---|
| `ANTHROPIC_API_KEY` | ✅ | Your Claude API key. The Anthropic client reads it automatically. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | optional | For `python cli.py summary --send` (how to get them is in `.env.example`) |
| `WDMMG_CONFIG` | optional | Use a different settings file, e.g. `WDMMG_CONFIG=demo/config.yaml` |

---

## 6. The pipeline at a glance

> 💡 **In plain English:** this is the order in which the engine's parts are called when you process one statement.

```
pipeline.process_statement(pdf)
 ├─ pdf_tools.fingerprint()           seen this file before? → stop
 ├─ pdf_tools.open_pdf()              unlock (typed password or saved ones)
 ├─ extract.extract_statement()
 │    ├─ pdf_tools.page_groups()      [pages 1–3] [4–6] …
 │    ├─ extract.extract_pages() ×N   Claude fills in the StatementChunk form
 │    │    └─ too long? split the group in half and retry
 │    └─ extract.merge()              one statement, rows in order
 ├─ reconcile.check()                 math OK? list of issues
 ├─ reconcile.check_dates()           every date real and inside the period (±7 days)?
 ├─ ledger.upsert_account()
 ├─ ids.transaction_ids()             a fingerprint for every row
 ├─ ledger.save_transactions()        duplicates silently skipped
 ├─ categorize.categorize_statement() rules → keywords → Claude
 ├─ alerts.scan()                     double charges, big charges…
 └─ ledger.set_status()               ready / mismatch / failed

sync.sync()   (separate step, run whenever you like)
 ├─ ledger.rows_needing_sync()        what changed since the last sync?
 ├─ sheets.SheetsMirror.rebuild_tab() for each affected (category, month)
 ├─ sheets.SheetsMirror.rebuild_summary()
 └─ ledger.mark_synced()
```

---

## 7. The modules, one by one

### 7.1 `config.py`: load settings

> 💡 Reads `config.yaml`, checks every setting has the right type (a typo like `pages_per_chunk: three` fails immediately with a clear message), and loads secrets from `.env`.

```python
# finance/config.py
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

Category = Literal["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other", "Not an expense"]
SheetCategory = Literal["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other"]
Confidence = Literal["high", "medium", "low"]


class Price(BaseModel):
    input: float  # USD per million input tokens
    output: float  # USD per million output tokens


class ReviewSettings(BaseModel):
    review_if_confidence: list[Confidence] = ["low", "medium"]
    large_charge: float = 200


class Settings(BaseModel):
    sheets: dict[SheetCategory, str]
    service_account_file: Path = Path("service_account.json")
    currency: str = "USD"
    model: str = "claude-opus-5-5"
    pages_per_chunk: int = 3
    categorize_batch_size: int = 100
    pricing_per_million_tokens: dict[str, Price] = {}
    keywords: dict[Category, list[str]] = {}
    review: ReviewSettings = ReviewSettings()
    auto_sync: bool = False
    db_path: Path = Path("data/ledger.db")
    statements_dir: Path = Path("data/statements")
    backups_dir: Path = Path("data/backups")
    inbox_dir: Path = Path("data/inbox")
    logs_dir: Path = Path("data/logs")


def load_settings(path: str | Path = "config.yaml") -> Settings:
    """Read config.yaml and put the secrets from .env into the environment."""
    load_dotenv()
    return Settings(**yaml.safe_load(Path(path).read_text()))
```

---

### 7.2 `pdf_tools.py`: open, unlock, split

> 💡 Three jobs:
> 1. **Fingerprint:** a unique code for the file, so we never process it twice (even if it's renamed).
> 2. **Unlock:** try the password you typed, then any saved in the Keychain. This happens **on your laptop**; the password is never sent anywhere.
> 3. **Split:** cut the PDF into small groups of pages, each saved as a new, *unlocked* mini-PDF in memory.

```python
# finance/pdf_tools.py
import base64
import hashlib
import io
from pathlib import Path

import keyring
from pypdf import PdfReader, PdfWriter

KEYCHAIN_SERVICE = "where-did-my-money-go"


class WrongPassword(Exception):
    """The PDF is locked and none of the passwords opened it."""


def fingerprint(path: Path) -> str:
    """SHA-256 of the file's bytes: same file → same fingerprint, even if renamed."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def open_pdf(path: Path, password: str | None = None) -> PdfReader:
    """Open a PDF, unlocking it with the typed password or any saved one."""
    reader = PdfReader(path)
    if not reader.is_encrypted:
        return reader
    candidates = ([password] if password else []) + _saved_passwords()  # Keychain
    for candidate in candidates:
        if not candidate:
            continue
        reader = PdfReader(path)  # fresh reader for each attempt
        if reader.decrypt(candidate):  # returns 0 ("not decrypted") on failure
            return reader
    raise WrongPassword(path.name)


def page_groups(reader: PdfReader, size: int) -> list[range]:
    """[range(0, 3), range(3, 6), …]: page numbers to send together."""
    total = len(reader.pages)
    return [range(start, min(start + size, total)) for start in range(0, total, size)]


def pages_as_pdf(reader: PdfReader, pages: range) -> str:
    """Copy some pages into a new, unlocked mini-PDF and return it as base64 text."""
    writer = PdfWriter()
    for i in pages:
        writer.add_page(reader.pages[i])
    buffer = io.BytesIO()
    writer.write(buffer)
    return base64.standard_b64encode(buffer.getvalue()).decode()
```

---

### 7.3 `extract.py`: Claude reads the pages

> 💡 We send Claude a few pages and a strict **form** to fill in (that's what the `Txn` and `StatementChunk` classes are). Claude returns the form filled in, and Pydantic checks that every field has the right type. If a group of pages is too long for one answer, we cut it in half and try again.
>
> **Why a form and not free text?** Free text ("On Nov 2nd you spent about 54 dollars at…") is hard for code to use reliably. A form gives us exact fields our code can trust.

```python
# finance/extract.py
import time
from typing import Callable, Literal

import anthropic
import pydantic
from pydantic import BaseModel, Field

from finance import costs
from finance.pdf_tools import page_groups, pages_as_pdf

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment


class Txn(BaseModel):
    date: str = Field(description="Transaction date as YYYY-MM-DD")
    description: str = Field(description="Exactly as printed; join the lines if it wraps")
    debit: float | None = Field(description="Money out (or a charge on a credit card), as a positive number")
    credit: float | None = Field(
        description="Money in (or a payment/refund on a credit card), as a positive number"
    )
    balance: float | None = Field(description="Running balance printed after this row, if any")


class StatementChunk(BaseModel):
    looks_like_statement: bool = Field(
        description="False if these pages are not from a bank or credit card statement"
    )
    kind: Literal["bank", "card"] | None = Field(description="'card' for a credit card statement")
    bank_name: str | None
    account_last4: str | None = Field(description="Last 4 digits of the account/card number only")
    currency: str | None = Field(description="ISO 4217 code, e.g. USD, EUR, INR")
    period_start: str | None = Field(description="YYYY-MM-DD")
    period_end: str | None = Field(description="YYYY-MM-DD")
    opening_balance: float | None = Field(description="Only if printed on these pages")
    closing_balance: float | None = Field(description="Only if printed on these pages")
    transactions: list[Txn]


EXTRACT_PROMPT = """You read bank and credit card statement pages and copy out the transactions.

Rules:
- List every transaction row on these pages, in the order printed.
- Skip rows that are not transactions: 'balance brought forward', 'carried forward',
  page totals, subtotals and repeated table headers.
- Copy amounts exactly as printed. Never calculate, round or guess a number.
- Write dates as YYYY-MM-DD. Use the statement period to work out the year, and
  whether dates are printed day-first or month-first.
- If a description wraps onto several lines, join it into one line.
- For the account or card number, return only the last 4 digits.
- Use null for anything not shown on these pages."""


class ChunkTooLong(Exception):
    """Claude's answer was cut off: send fewer pages at a time."""


class AIDeclined(Exception):
    """Claude declined to process these pages."""


def extract_pages(pdf_b64: str, model: str, on_call: Callable) -> StatementChunk:
    """Send one group of pages to Claude and get the filled-in form back."""
    started = time.monotonic()
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=16000,
            system=EXTRACT_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                        },
                        {"type": "text", "text": "Copy out the transactions on these pages."},
                    ],
                }
            ],
            output_format=StatementChunk,
        )
    except pydantic.ValidationError as e:
        # The answer didn't fit the form, which usually means it was cut off mid-way.
        raise ChunkTooLong() from e

    on_call(costs.from_response("extract", model, resp, started))  # log the cost
    if resp.stop_reason == "max_tokens":
        raise ChunkTooLong()
    if resp.stop_reason == "refusal":
        raise AIDeclined()
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"Unexpected stop reason: {resp.stop_reason}")
    return resp.parsed_output


def extract_statement(reader, settings, on_call: Callable) -> StatementChunk:
    """Read every page group and join the results into one statement."""
    chunks: list[StatementChunk] = []
    for pages in page_groups(reader, settings.pages_per_chunk):
        chunks += _extract_with_retry(reader, pages, settings.model, on_call)
    return merge(chunks)


def _extract_with_retry(reader, pages: range, model: str, on_call) -> list[StatementChunk]:
    try:
        return [extract_pages(pages_as_pdf(reader, pages), model, on_call)]
    except ChunkTooLong:
        if len(pages) == 1:
            raise  # can't split a single page further
        middle = pages.start + len(pages) // 2  # split the group in half and retry
        return _extract_with_retry(reader, range(pages.start, middle), model, on_call) + _extract_with_retry(
            reader, range(middle, pages.stop), model, on_call
        )


def merge(chunks: list[StatementChunk]) -> StatementChunk:
    """Header details from the first group that has them, closing balance from the
    last group that has it, and every transaction in order."""

    def first(field, items):
        return next((getattr(c, field) for c in items if getattr(c, field) is not None), None)

    header = [
        "kind",
        "bank_name",
        "account_last4",
        "currency",
        "period_start",
        "period_end",
        "opening_balance",
    ]
    return StatementChunk(
        looks_like_statement=chunks[0].looks_like_statement,
        **{field: first(field, chunks) for field in header},
        closing_balance=first("closing_balance", reversed(chunks)),
        transactions=[t for c in chunks for t in c.transactions],
    )
```

**Why these choices:**

| Choice | Reason |
|---|---|
| 3 pages per request | Each answer stays short, so it's never cut off, and one bad read affects only a few rows |
| `looks_like_statement` field | Lets us politely reject a random PDF (a menu, a ticket) instead of producing garbage |
| Last 4 digits only | The full account number never enters our database or Google Sheets |
| "Never calculate" in the prompt | We want copied numbers, not computed ones. The *code* does all the math. |
| `stop_reason` checks | `max_tokens` means "cut off, so retry smaller", `refusal` means "declined, so fail clearly" |

---

### 7.4 `reconcile.py`: check the math

> 💡 Like counting the till at the end of the day: start with the opening balance, apply each row (minus money out, plus money in), and after every row compare against the balance the bank printed. If they disagree, we know **exactly which row** is wrong.
>
> Credit cards work the other way round: the "balance" is what you *owe*, so spending makes it go **up**.

```python
# finance/reconcile.py
def check(opening, closing, txns, is_card: bool = False, tolerance: float = 0.01) -> list[str]:
    """Return a list of problems. An empty list means the statement is verified."""
    sign = -1 if is_card else 1
    if opening is None and txns and txns[0].balance is not None:
        first = txns[0]  # no opening balance printed: work it out from row 1
        opening = first.balance - sign * ((first.credit or 0) - (first.debit or 0))
    if opening is None:
        return ["No opening or running balance printed, so the statement can't be verified"]

    issues, balance = [], opening
    for row_number, t in enumerate(txns, start=1):
        balance += sign * ((t.credit or 0) - (t.debit or 0))
        if t.balance is not None and abs(balance - t.balance) > tolerance:
            issues.append(
                f"Row {row_number} ({t.date}, '{t.description[:30]}'): "
                f"expected {balance:,.2f}, statement shows {t.balance:,.2f}"
            )
            balance = t.balance  # resync, so one bad row doesn't flag every row after it
    if closing is not None and abs(balance - closing) > tolerance:
        issues.append(f"Closing balance: worked out {balance:,.2f}, statement shows {closing:,.2f}")
    return issues
```

**Dates are checked too.** Balances can't reveal a misread *date*, so `check_dates()` flags any date that isn't real ("2026-02-30") or falls outside the statement period by more than 7 days (card statements can include purchases from a few days before). Tests found this gap; see [TESTING.md §9](TESTING.md#9-bugs-the-tests-caught).

**Example:**
```
Opening balance 1,000.00
Row 1  Fresh Mart   −54.20  → expected   945.80, statement shows   945.80 ✅
Row 2  Salary    +3,000.00  → expected 3,945.80, statement shows 3,945.80 ✅
Row 3  City Cabs    −46.00  → expected 3,899.80, statement shows 3,881.80 ❌
         → "Row 3 (2026-11-05, 'CITY CABS'): expected 3,899.80, statement shows 3,881.80"
         (the AI probably read 64.00 as 46.00)
```

---

### 7.5 `ids.py`: fingerprints

> 💡 Two kinds of fingerprint:
> - **Transaction ID:** built from the account, date, amounts and description. The same transaction always gets the same ID, so if it appears in two overlapping statements, it's saved only once. A counter keeps two *identical* coffees on the same day as two separate rows.
> - **Merchant key:** a simplified shop name used to look up saved rules. `"AMZN Mktp US*2K4L95 Seattle WA"` becomes `"amzn mktp us"`, so next month's `"AMZN Mktp US*9QX71 Seattle WA"` matches the same rule.

```python
# finance/ids.py
import hashlib
import re
from collections import Counter


def account_ref(kind: str | None, last4: str | None) -> str:
    """'bank:1234'. Used inside transaction IDs and to identify accounts."""
    return f"{kind or 'bank'}:{last4 or 'unknown'}"


def transaction_ids(account: str, txns) -> list[str]:
    seen: Counter[str] = Counter()
    ids = []
    for t in txns:
        description = re.sub(r"[^a-z0-9]", "", t.description.lower())  # ignore spacing/punctuation
        base = f"{account}|{t.date}|{t.debit}|{t.credit}|{description}"
        seen[base] += 1  # 1st identical coffee → |1, 2nd → |2
        ids.append(hashlib.sha256(f"{base}|{seen[base]}".encode()).hexdigest()[:16])
    return ids


def merchant_key(description: str) -> str:
    """'AMZN Mktp US*2K4L95 Seattle WA' → 'amzn mktp us' (letters only, first 3 words)."""
    words = re.sub(r"[^a-z ]", " ", description.lower()).split()
    return " ".join(words[:3])
```

---

### 7.6 `categorize.py`: sort into categories

> 💡 For each transaction, we try three things in order and stop at the first that works:
> 1. **Saved rule:** "we've seen this shop before" (from your fixes, or a confident earlier AI answer). Free and instant.
> 2. **Keyword:** a word from `config.yaml` appears in the description (e.g. "netflix"). Free and instant.
> 3. **Ask Claude:** about 100 unknown rows per request. Your past corrections are included, so Claude learns your preferences.
>
> Claude also says how sure it is (high, medium or low). Medium and low go to your review queue.
>
> Each run sorts **every** row still waiting for a category, not just the new statement's. If an earlier attempt failed half-way and you upload a freshly downloaded copy, the rows the first attempt saved still get sorted.

```python
# finance/categorize.py
import re
import time
from itertools import batched
from typing import Callable, Literal

import anthropic
from pydantic import BaseModel, Field

from finance import costs, ledger
from finance.config import Category, Settings
from finance.ids import merchant_key

client = anthropic.Anthropic()

CATEGORIZE_PROMPT = """You sort personal bank transactions into exactly one category each.

Categories:
- Grocery: food and household supplies bought to take home (supermarkets, grocery
  delivery, markets).
- Travel: getting around and trips (cabs, ride-hailing, fuel, parking, tolls, trains,
  metro, flights, hotels).
- Subscriptions: recurring charges for a service (streaming, music, cloud storage,
  software, gym, phone and internet plans).
- Investments: money put into assets (brokerage, mutual funds, SIPs, ETFs, stocks,
  crypto, retirement contributions).
- Savings: money moved to the user's own savings account, fixed deposit or recurring deposit.
- Other: any other real spending (rent, restaurants, cafés, food delivery, shopping, bills,
  insurance, loan payments, healthcare, cash withdrawals, money sent to other people).
- Not an expense: money coming in (salary, interest, transfers in) and payments of the
  user's own credit card bill.

Rules:
- Amount is positive for money out and negative for money in.
- A refund (money in from a shop) keeps that shop's category.
- Money coming back from the user's own savings or investments keeps that category.
- merchant: a short, clean shop name, e.g. 'AMZN Mktp US*2K4L9' -> 'Amazon'.
- If the description is too vague to tell, choose 'Other' with low confidence.
  Do not guess."""


class Labeled(BaseModel):
    n: int = Field(description="The row number given in the input")
    merchant: str = Field(description="Short, clean shop name")
    category: Category
    confidence: Literal["high", "medium", "low"]


class Labels(BaseModel):
    items: list[Labeled]


def keyword_category(description: str, keywords: dict[str, list[str]]) -> str | None:
    """First category whose keyword appears as a whole word ('sip' won't match 'gossip')."""
    for category, words in keywords.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", description, re.IGNORECASE):
                return category
    return None


def categorize_statement(db, settings: Settings, statement_id: int, on_call: Callable) -> None:
    rows = ledger.uncategorized(db, statement_id)
    rules = ledger.merchant_rules(db)  # {merchant_key: (merchant, category)}
    updates, for_ai = [], []

    for r in rows:
        key = merchant_key(r["description"])
        if key in rules:  # 1. saved rule
            merchant, category = rules[key]
            updates.append(
                dict(id=r["id"], merchant=merchant, category=category, confidence="high", source="rule")
            )
        elif category := keyword_category(r["description"], settings.keywords):  # 2. keyword
            updates.append(
                dict(id=r["id"], merchant=None, category=category, confidence="high", source="keyword")
            )
        else:
            for_ai.append(r)  # 3. ask Claude

    corrections = ledger.recent_corrections(db, limit=40)
    for batch in batched(for_ai, settings.categorize_batch_size):
        labels = ask_claude(batch, corrections, settings.model, on_call)
        for n, r in enumerate(batch, start=1):
            label = labels.get(n)
            if label is None:  # Claude skipped this row: send it to review
                updates.append(
                    dict(id=r["id"], merchant=None, category="Other", confidence="low", source="ai")
                )
                continue
            updates.append(
                dict(
                    id=r["id"],
                    merchant=label.merchant,
                    category=label.category,
                    confidence=label.confidence,
                    source="ai",
                )
            )
            if label.confidence == "high":  # learn it, so next month it's free
                ledger.save_rule(
                    db, merchant_key(r["description"]), label.merchant, label.category, source="ai"
                )

    ledger.apply_categories(db, updates, review_if=settings.review.review_if_confidence)


def ask_claude(batch, corrections: list[str], model: str, on_call: Callable) -> dict[int, Labeled]:
    lines = "\n".join(
        f"{n} | {r['txn_date']} | {r['amount']:.2f} | {r['description']}"
        for n, r in enumerate(batch, start=1)
    )
    system = CATEGORIZE_PROMPT
    if corrections:
        system += (
            "\n\nThe user corrected these before. Make the same choices for similar rows:\n"
            + "\n".join(corrections)
        )
    started = time.monotonic()
    resp = client.messages.parse(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": f"n | date | amount | description\n{lines}"}],
        output_format=Labels,
    )
    on_call(costs.from_response("categorize", model, resp, started))
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"Categorization stopped early: {resp.stop_reason}")
    return {label.n: label for label in resp.parsed_output.items}
```

**Design notes:**
- **Short row numbers (`n`) instead of 16-character IDs:** the AI only has to echo back `1…100`, which avoids typos in long codes.
- **Confidence as words, not percentages:** AI-reported percentages ("87% sure") aren't reliable. Three levels are honest and easy to act on.
- **Your corrections come first:** `ledger.recent_corrections()` returns lines like `"UBER *EATS 8812" → Other`, so Claude copies *your* choices.
- **Priority order:** your own fixes are saved as rules (source `user`) and always beat AI-learned rules. `save_rule()` never overwrites a `user` rule with an `ai` one.

---

### 7.7 `ledger.py`: the database layer

> 💡 Every read and write to the database goes through this one file. No other module writes SQL, so the database rules live in a single place. The tables themselves are explained in [DB.md](DB.md).

```python
# finance/ledger.py  (selected functions)
import json
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row  # rows work like dicts: row["amount"]
    db.execute("PRAGMA foreign_keys = ON")  # enforce the links between tables
    db.execute("PRAGMA journal_mode = WAL")  # safer writes; reading doesn't block writing
    migrate(db)
    return db


def migrate(db: sqlite3.Connection) -> None:
    """Apply any migration files newer than the database's version number."""
    current = db.execute("PRAGMA user_version").fetchone()[0]
    for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(file.name.split("_")[0])  # 001_init.sql → 1
        if version > current:
            db.executescript(file.read_text())
            db.execute(f"PRAGMA user_version = {version}")
            db.commit()


def save_transactions(db, statement_id, account_id, stmt, txn_ids, currency, hold_for_review: bool) -> int:
    """Insert new rows and silently skip ones we already have. Returns how many were new."""
    reason = "Statement totals don't match" if hold_for_review else None
    rows = [
        {
            "id": txn_id,
            "statement_id": statement_id,
            "account_id": account_id,
            "row_number": n,
            "txn_date": t.date,
            "description": t.description,
            "amount": round((t.debit or 0) - (t.credit or 0), 2),  # + out, − in
            "balance_after": t.balance,
            "currency": stmt.currency or currency,
            "needs_review": int(hold_for_review),
            "review_reason": reason,
        }
        for n, (t, txn_id) in enumerate(zip(stmt.transactions, txn_ids), start=1)
    ]
    before = db.total_changes
    db.executemany(
        """
        INSERT OR IGNORE INTO transactions
            (id, statement_id, account_id, row_number, txn_date, description, amount,
             balance_after, currency, needs_review, review_reason)
        VALUES
            (:id, :statement_id, :account_id, :row_number, :txn_date, :description, :amount,
             :balance_after, :currency, :needs_review, :review_reason)""",
        rows,
    )
    db.commit()
    return db.total_changes - before


def mark_synced(db, ids: list[str]) -> None:
    """Remember that Google Sheets now matches these rows."""
    db.executemany(
        "UPDATE transactions SET synced_at = ?, synced_category = category WHERE id = ?",
        [(now(), i) for i in ids],
    )
    db.commit()
```

**Full list of ledger functions:**

| Function | 💡 What it does |
|---|---|
| `connect(path)` / `migrate(db)` | Open the database and create or upgrade the tables |
| `find_statement(db, file_hash)` | Have we seen this file? Returns its row or `None` |
| `create_statement(db, file_hash, file_name)` | Register a new upload, returns its ID |
| `set_status(db, id, status, issues=None, error=None)` | Move a statement through its lifecycle |
| `save_statement_details(db, id, stmt, page_count)` | Store the period, balances and page count |
| `upsert_account(db, stmt, currency)` | Find or create the account (by type + last 4 digits) |
| `save_transactions(...)` | Insert rows, skipping duplicates |
| `uncategorized(db, statement_id)` | Rows that still need a category |
| `merchant_rules(db)` / `save_rule(...)` | Read and write learned rules (`user` rules always win) |
| `apply_categories(db, updates, review_if)` | Save categories and flag unsure rows for review |
| `recent_corrections(db, limit)` | Your latest fixes, formatted as examples for the AI |
| `review_queue(db)` | Rows waiting for you, as a table (pandas DataFrame) |
| `apply_user_review(db, edited, remember)` | Save your fixes, optionally as rules, and mark them for re-sync |
| `approve_statement(db, id)` | Accept a statement whose math didn't match (after you've checked it) |
| `rows_needing_sync(db)` | Approved rows that changed since the last sync |
| `rows_for_tab(db, category, month)` | Exactly what one month tab should contain |
| `months_for(db, category)` | Which months have rows in this category |
| `mark_synced(db, ids)` | Record that Sheets now matches these rows |
| `record_ai_call(db, statement_id, call, cost)` | Log tokens and cost |
| `save_alerts(db, alerts)` | Store alerts (each alert is stored only once) |
| `forget_statement(db, id)` | Delete a statement and its rows. Run a sync afterwards. |
| `backup(db, backups_dir)` | Copy the database to `data/backups/` and keep the last 10 copies |

The SQL behind these is in [DB.md → Common queries](DB.md#9-common-queries).

---

### 7.8 `sheets.py`: the Google Sheets mirror

> 💡 The mirror **only writes, never reads**. For each affected month it **wipes the tab and rewrites it** with exactly what the ledger says. That sounds wasteful, but it means:
> - running sync twice gives the same result,
> - a crashed sync is fixed by running it again,
> - a row that changes category automatically leaves its old sheet.

```python
# finance/sheets.py
import gspread

HEADERS = ["Date", "Merchant", "Description", "Amount", "Currency", "Account", "Txn ID"]


class SheetsMirror:
    """Writes ledger rows into the Google Sheets. Never reads data back."""

    def __init__(self, settings):
        gc = gspread.service_account(filename=str(settings.service_account_file))
        self.books = {category: gc.open_by_key(sheet_id) for category, sheet_id in settings.sheets.items()}

    def rebuild_tab(self, category: str, month: str, rows: list[list]) -> None:
        """Make the month tab contain exactly `rows`, nothing more, nothing less."""
        book = self.books[category]
        try:
            ws = book.worksheet(month)
        except gspread.exceptions.WorksheetNotFound:
            if not rows:
                return
            ws = book.add_worksheet(title=month, rows=len(rows) + 50, cols=len(HEADERS))
        if not rows:  # every row moved elsewhere: remove the empty tab
            book.del_worksheet(ws)
            return
        ws.clear()
        ws.resize(rows=len(rows) + 50, cols=len(HEADERS))
        ws.update(range_name="A1", values=[HEADERS] + rows, value_input_option="USER_ENTERED")
        ws.freeze(rows=1)

    def rebuild_summary(self, category: str, months: list[str]) -> None:
        """Rewrite the Summary tab, then order tabs: Summary first, newest month next."""
        book = self.books[category]
        summary = book.worksheet("Summary")
        newest_first = sorted(months, reverse=True)
        values = [["Month", "Total", "Transactions"]] + [
            [m, f"=SUM('{m}'!D2:D)", f"=COUNTA('{m}'!A2:A)"] for m in newest_first
        ]
        summary.clear()
        summary.update(range_name="A1", values=values, value_input_option="USER_ENTERED")
        month_tabs = sorted(
            (ws for ws in book.worksheets() if ws.title != "Summary"), key=lambda ws: ws.title, reverse=True
        )
        book.reorder_worksheets([summary] + month_tabs)
```

- `USER_ENTERED` makes Google treat `2026-11-02` as a real date and `54.20` as a number, as if you'd typed them.
- One `update()` per tab is a single API request, which keeps us well within Google's per-minute limits.
- If Google does say "slow down", gspread 6 includes a `BackOffHTTPClient` that waits and retries automatically. Pass it as `http_client=` when connecting.

---

### 7.9 `sync.py`: decide what to rebuild

> 💡 Sync looks at every approved row that changed since last time and works out which **(category, month)** tabs are affected, *including the tab a row moved away from*. Then it rebuilds only those tabs and refreshes the Summary tabs.

```python
# finance/sync.py
import gspread

from finance import ledger
from finance.sheets import SheetsMirror


class SyncError(Exception):
    pass


def sync(db, settings) -> dict:
    enabled = set(settings.sheets)
    changed = ledger.rows_needing_sync(db)  # approved rows with synced_at IS NULL
    if not changed:
        return {"tabs": [], "rows": 0}

    tabs = {(r["category"], r["month"]) for r in changed if r["category"] in enabled}
    tabs |= {
        (r["synced_category"], r["month"])  # the tab a row moved away from
        for r in changed
        if r["synced_category"] in enabled
    }

    try:
        mirror = SheetsMirror(settings)
    except (gspread.exceptions.APIError, gspread.exceptions.SpreadsheetNotFound, PermissionError) as e:
        raise SyncError(
            "Can't open one of the spreadsheets. Is it shared with the robot email from service_account.json?"
        ) from e

    run_id = ledger.start_sync_run(db)
    for category, month in sorted(tabs):
        mirror.rebuild_tab(category, month, ledger.rows_for_tab(db, category, month))
    for category in sorted({c for c, _ in tabs}):
        mirror.rebuild_summary(category, ledger.months_for(db, category))

    ledger.mark_synced(db, [r["id"] for r in changed])
    ledger.finish_sync_run(db, run_id, tabs=sorted(tabs), rows=len(changed))
    return {"tabs": sorted(tabs), "rows": len(changed)}
```

**Example:** you move one row from Grocery to Other (with the Other sheet off) in November.
→ affected tabs = `{("Grocery", "2026-11")}`
→ the Grocery `2026-11` tab is rebuilt without that row, and the Grocery Summary updates.
→ the row is marked synced with `synced_category = "Other"`.

---

### 7.10 `alerts.py`: spot weird charges

> 💡 After each statement, compare the new rows against your history. This is plain arithmetic in pandas, with **no AI**, so it's free, instant and explainable.

| Alert | Rule |
|---|---|
| `new_merchant` | First-ever charge from this shop, and above `large_charge` |
| `big_charge` | More than 3× this shop's usual (median) charge, with at least 3 earlier charges |
| `double_charge` | Same shop and same amount within 2 days |
| `new_subscription` | Same shop 3+ times, 26–35 days apart, similar amount |
| `price_increase` | A recurring charge's latest amount is more than 2% above the previous one |
| `trial_converted` | A tiny (≤ 1) charge, then a real charge from the same shop 7–30 days later |
| `category_spike` | This month's category total is more than 1.5× its 3-month average |

```python
# finance/alerts.py  (first three rules)
import pandas as pd

from finance import ledger


def scan(db, statement_id: int, settings) -> int:
    df = pd.read_sql_query(
        """SELECT id, statement_id, txn_date, COALESCE(merchant, description) AS merchant, amount
           FROM transactions
           WHERE amount > 0 AND category != 'Not an expense'""",
        db,
        parse_dates=["txn_date"],
    )
    new = df[df.statement_id == statement_id]
    found = []
    for _, t in new.iterrows():
        same_shop = df[df.merchant == t.merchant]
        earlier = same_shop[same_shop.txn_date < t.txn_date].amount
        if earlier.empty and t.amount >= settings.review.large_charge:
            found.append((t.id, "new_merchant", f"First charge from {t.merchant}: {t.amount:,.2f}"))
        elif len(earlier) >= 3 and t.amount > 3 * earlier.median():
            found.append(
                (t.id, "big_charge", f"{t.merchant}: {t.amount:,.2f} (usually about {earlier.median():,.2f})")
            )
        twins = same_shop[
            (same_shop.id != t.id)
            & (same_shop.amount == t.amount)
            & ((same_shop.txn_date - t.txn_date).abs() <= pd.Timedelta(days=2))
        ]
        if not twins.empty:
            found.append((t.id, "double_charge", f"{t.merchant} charged {t.amount:,.2f} twice within 2 days"))
    return ledger.save_alerts(db, found)  # each (transaction, kind) is stored only once
```

---

### 7.11 `costs.py`: what did the AI cost?

> 💡 Every Claude response reports how many tokens it read and wrote. We multiply by the prices in `config.yaml` and log the result, so `python cli.py costs` can show exactly what you've spent.

```python
# finance/costs.py
import time
from dataclasses import dataclass


@dataclass
class AICall:
    purpose: str  # "extract" or "categorize"
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    stop_reason: str | None


def from_response(purpose: str, model: str, resp, started: float) -> AICall:
    return AICall(
        purpose,
        model,
        resp.usage.input_tokens,
        resp.usage.output_tokens,
        int((time.monotonic() - started) * 1000),
        resp.stop_reason,
    )


def cost_usd(call: AICall, settings) -> float:
    price = settings.pricing_per_million_tokens.get(call.model)
    if price is None:
        return 0.0
    return (call.input_tokens * price.input + call.output_tokens * price.output) / 1_000_000
```

---

### 7.12 `pipeline.py`: the manager

> 💡 Runs every step in order. If anything fails, it records a **plain-English reason** on the statement and stops safely: nothing half-finished ever reaches Google Sheets.

```python
# finance/pipeline.py
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from finance import alerts, categorize, costs, extract, ids, ledger, pdf_tools, reconcile
from finance.config import Settings


class NotAStatement(Exception):
    pass


@dataclass
class Result:
    statement_id: int | None
    status: str
    message: str
    new_rows: int = 0
    to_review: int = 0
    issues: list[str] = field(default_factory=list)


def process_statement(path: Path, settings: Settings, db, password: str | None = None) -> Result:
    file_hash = pdf_tools.fingerprint(path)
    existing = ledger.find_statement(db, file_hash)
    if existing and existing["status"] != "failed":
        return Result(
            existing["id"],
            existing["status"],
            f"Already processed on {existing['uploaded_at'][:10]}. Nothing to do.",
        )

    stored = settings.statements_dir / f"{file_hash[:16]}.pdf"  # keep our own copy
    stored.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, stored)
    sid = existing["id"] if existing else ledger.create_statement(db, file_hash, path.name)
    ledger.set_status(db, sid, "processing")

    def log_call(call):
        ledger.record_ai_call(db, sid, call, costs.cost_usd(call, settings))

    try:
        reader = pdf_tools.open_pdf(stored, password)
        stmt = extract.extract_statement(reader, settings, on_call=log_call)
        if not stmt.looks_like_statement:
            raise NotAStatement()

        issues = reconcile.check(
            stmt.opening_balance, stmt.closing_balance, stmt.transactions, is_card=(stmt.kind == "card")
        )
        account_id = ledger.upsert_account(db, stmt, settings.currency)
        txn_ids = ids.transaction_ids(ids.account_ref(stmt.kind, stmt.account_last4), stmt.transactions)
        new_rows = ledger.save_transactions(
            db, sid, account_id, stmt, txn_ids, settings.currency, hold_for_review=bool(issues)
        )
        ledger.save_statement_details(db, sid, stmt, page_count=len(reader.pages))

        categorize.categorize_statement(db, settings, sid, on_call=log_call)
        alerts.scan(db, sid, settings)

        status = "mismatch" if issues else "ready"
        ledger.set_status(db, sid, status, issues=issues)
        to_review = ledger.count_review(db, sid)
        message = f"Read {len(stmt.transactions)} transactions ({new_rows} new). " + (
            "⚠️ The numbers don't match the statement. Please check the rows listed."
            if issues
            else f"✅ Balances match. {to_review} rows need your review."
        )
        return Result(sid, status, message, new_rows, to_review, issues)

    except pdf_tools.WrongPassword:
        return _fail(
            db,
            sid,
            "This PDF is locked. Enter its password, or save it with 'python cli.py password add <name>'.",
        )
    except NotAStatement:
        return _fail(db, sid, "This doesn't look like a bank or card statement.")
    except extract.ChunkTooLong:
        return _fail(db, sid, "A single page has too many rows to read in one go.")
    except extract.AIDeclined:
        return _fail(db, sid, "The AI couldn't process this statement.")
    except anthropic.RateLimitError:
        return _fail(db, sid, "Claude is busy right now. Try again in a minute.")
    except anthropic.APIConnectionError:
        return _fail(db, sid, "Couldn't reach Claude. Check your internet connection.")
    except anthropic.APIStatusError as e:
        return _fail(db, sid, f"Claude API error ({e.status_code}). Try again later.")


def _fail(db, sid: int, message: str) -> Result:
    ledger.set_status(db, sid, "failed", error=message)
    return Result(sid, "failed", message)
```

**Re-running is always safe.** A `failed` statement can be processed again: rows that were already saved are skipped (`INSERT OR IGNORE`), and only uncategorized rows go to the AI.

---

## 8. The command line (`cli.py`)

> 💡 Everything the web app does, as typed commands. Handy for automation and for developers.

| Command | What it does |
|---|---|
| `python cli.py check [--offline]` | Checklist: settings, Claude key, spreadsheets, folders, .gitignore |
| `python cli.py process FILE.pdf [--ask-password] [--dry-run]` | Read, check and categorize one statement (`--dry-run` saves nothing) |
| `python cli.py inbox` | Process every PDF in `data/inbox/` once (for a scheduled job) |
| `python cli.py watch` | Keep watching `data/inbox/` and process new PDFs automatically |
| `python cli.py status` | Every statement and its status |
| `python cli.py review` | List rows waiting for review |
| `python cli.py approve STATEMENT_ID` | Accept a statement whose numbers didn't match (after checking) |
| `python cli.py sync` | Update Google Sheets |
| `python cli.py rebuild 2026-11` / `--all` | Rebuild sheet tabs from the database |
| `python cli.py alerts` | Open alerts |
| `python cli.py summary [--month 2026-11] [--send]` | Monthly summary, optionally to Telegram |
| `python cli.py costs [--month 2026-11]` | AI spend so far |
| `python cli.py rules [--remove KEY]` | List (or forget) saved shop rules |
| `python cli.py forget STATEMENT_ID [--yes]` | Delete a statement and its rows, then refresh the sheets |
| `python cli.py backup` | Back up the database |
| `python cli.py password add/remove/list NAME` | Manage saved PDF passwords in the Keychain |

```python
# cli.py  (excerpt)
from pathlib import Path

import keyring
import typer

from finance import ledger, pipeline, sync as sync_module
from finance.config import load_settings
from finance.pdf_tools import KEYCHAIN_SERVICE

app = typer.Typer(help="Where Did My Money Go? Command line.")
password_app = typer.Typer(help="Manage saved PDF passwords (stored in the macOS Keychain).")
app.add_typer(password_app, name="password")


@app.command()
def process(pdf: Path, ask_password: bool = typer.Option(False, "--ask-password")):
    """Read, check and categorize one statement PDF."""
    settings = load_settings()
    db = ledger.connect(settings.db_path)
    password = typer.prompt("PDF password", hide_input=True) if ask_password else None
    result = pipeline.process_statement(pdf, settings, db, password)
    typer.echo(result.message)
    for issue in result.issues:
        typer.echo(f"  ⚠ {issue}")


@app.command()
def sync():
    """Update Google Sheets with every approved change."""
    settings = load_settings()
    result = sync_module.sync(ledger.connect(settings.db_path), settings)
    typer.echo(f"Rebuilt {len(result['tabs'])} tabs, {result['rows']} rows changed.")


@password_app.command("add")
def password_add(name: str):
    """Save a PDF password under a short name, e.g. 'mainbank'."""
    secret = typer.prompt(f"Password for {name}", hide_input=True)
    pdf_tools.save_password(name, secret)  # Keychain, plus a list of saved names
    typer.echo(f"Saved '{name}'. Locked statements will now open automatically.")


if __name__ == "__main__":
    app()
```

---

## 9. The web app (`app.py`)

> 💡 Streamlit turns short Python scripts into web pages. Each file is a page, and each page simply calls the engine.

| Page | File | What it shows |
|---|---|---|
| Upload | `app.py` | Drop zone (several PDFs at once), password box with "remember", live progress, result |
| Review | `pages/1_Review.py` | Editable table of unsure rows with a category drop-down, "Approve all" |
| Dashboard | `pages/2_Dashboard.py` | Spent / set aside / money in / savings rate, monthly chart, top shops, monthly charges, alerts (dismissable), summary text |
| Transactions | `pages/3_Transactions.py` | Every row, filterable; fix shop, category or a misread amount (re-checks the statement) |
| Statements | `pages/4_Statements.py` | Status of every upload; mismatch details with "approve", retry failed ones, download the PDF, forget |
| Setup | `pages/5_Setup.py` | Checklist, AI costs, saved rules, backup button |

Every page shares a sidebar (`ui_common.py`) showing rows to review, rows not yet synced, and the **🔄 Sync to Google Sheets** button.

**Upload page (excerpt):**
```python
# app.py
import tempfile
from pathlib import Path

import streamlit as st

from finance import ledger, pipeline
from finance.config import load_settings

st.set_page_config(page_title="Where Did My Money Go?", page_icon="💸")
settings = load_settings()
db = ledger.connect(settings.db_path)  # a fresh connection on every run (see note below)

st.title("💸 Upload a statement")
uploaded = st.file_uploader("Statement PDF", type="pdf")
password = st.text_input("Password (only if the PDF is locked)", type="password")

if uploaded and st.button("Process ▶"):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / uploaded.name
        path.write_bytes(uploaded.getvalue())
        with st.spinner("Reading your statement… usually 1–2 minutes"):
            result = pipeline.process_statement(path, settings, db, password or None)

    if result.status == "failed":
        st.error(result.message)
    elif result.status == "mismatch":
        st.warning(result.message)
        for issue in result.issues:
            st.write("•", issue)
    else:
        st.success(result.message)
        if result.to_review:
            st.page_link("pages/1_Review.py", label=f"Review {result.to_review} rows →")
```

**Review page (excerpt):**
```python
# pages/1_Review.py
import streamlit as st

from finance import ledger
from finance.config import load_settings

CATEGORIES = ["Grocery", "Travel", "Subscriptions", "Investments", "Savings", "Other", "Not an expense"]

settings = load_settings()
db = ledger.connect(settings.db_path)
st.title("👀 Review")

rows = ledger.review_queue(
    db
)  # DataFrame: id, txn_date, description, merchant, amount, category, review_reason
if rows.empty:
    st.success("Nothing to review 🎉")
    st.stop()

edited = st.data_editor(
    rows,
    column_config={
        "id": None,  # hide the fingerprint column
        "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, required=True),
    },
    disabled=["txn_date", "description", "merchant", "amount", "review_reason"],
    hide_index=True,
)
remember = st.checkbox("Remember my choices for these shops", value=True)
if st.button("Approve all ✓"):
    ledger.apply_user_review(db, edited, remember=remember)
    st.success(f"Saved {len(edited)} rows. Click Sync to update Google Sheets.")
```

> **Note on database connections:** Streamlit re-runs the page script on every click, sometimes on different threads. SQLite connections shouldn't be shared between threads, so each run opens its own connection. That's cheap, so don't wrap it in `st.cache_resource`.

**Always start the app with** `streamlit run app.py --server.address localhost`, so only your own computer can open it.

---

## 10. Error handling

> 💡 Three principles: **(1)** fail safely, never writing unverified or half-finished data to Google Sheets; **(2)** explain problems in plain English; **(3)** make "try again" always safe.

| Where | Error | Handling |
|---|---|---|
| `pdf_tools` | `WrongPassword` | Statement `failed`, ask for the password. Nothing sent anywhere. |
| `extract` | `ChunkTooLong` | Split the page group in half and retry, down to a single page |
| `extract` | `AIDeclined` (`stop_reason == "refusal"`) | Statement `failed`, with a clear message |
| `extract`, `categorize` | `anthropic.RateLimitError`, `APIConnectionError`, `APIStatusError` | The SDK retries twice on its own. Then the statement is `failed` with a plain message, and retrying is safe. |
| `pipeline` | `NotAStatement` | Statement `failed`: "This doesn't look like a bank statement" |
| `reconcile` | Issues found | Not an error: status `mismatch`, all rows held for review |
| `sync` | Can't open a spreadsheet | `SyncError` telling you which robot email to share it with. Nothing written. |
| `sync` | Google rate limit | Automatic back-off and retry. Re-running sync is always safe. |
| anywhere | Unexpected bug | Logged with details in `data/logs/app.log`. The statement stays in `processing` or `failed` and can be retried. |

Catch errors from **most specific to least specific** (`RateLimitError` before `APIStatusError`), so each problem gets the right message.

---

## 11. Logging

- Location: `data/logs/app.log` (rotates at 1 MB, keeps 5 files).
- **Log:** statement IDs, row counts, statuses, timings, token counts, error types.
- **Don't log:** full descriptions, amounts, account numbers or passwords. Logs get shared when asking for help, so keep them boring.
- Turn on Anthropic SDK debug logging only while troubleshooting: `ANTHROPIC_LOG=debug`.

---

## 12. Testing

> 💡 Tests are small programs that check the real program still works after every change. We **never** use real statements in tests. We generate fake ones.

### Run them

```bash
python -m pytest                 # 206 tests, about 10 seconds, free (no real APIs)
python -m pytest --report TESTING.md   # …and refresh the results in TESTING.md
python -m pytest -m live         # opt-in: the fixtures through the real Claude (~$0.50)
python scripts/demo.py           # build a no-key demo, then:
WDMMG_CONFIG=demo/config.yaml streamlit run app.py --server.address localhost
```

**Everything about testing is explained in [TESTING.md](TESTING.md).** In short: the tests use **fake statements** (`finance/demo.py` draws them with reportlab), a **pretend Claude** that reads those fake PDFs perfectly, and a **fake Google Sheets** that lives in memory. The real code runs everywhere else: PDF unlocking, the math check, the database, categorization rules, sync decisions, alerts and every web page.

### Test pyramid

| Level | What | Costs money? | Run |
|---|---|---|---|
| **Unit tests** | Math check, fingerprints, keyword rules, month splitting, sync tab selection | No | `pytest` (every change) |
| **Database tests** | Duplicates skipped, review flags, sync bookkeeping, using a temporary database | No | `pytest` |
| **Sheets tests** | Sync against a fake in-memory mirror | No | `pytest` |
| **Live tests** | A fake PDF goes through the real Claude API and must reconcile | Yes (cents) | `pytest -m live` |
| **Accuracy eval** | Categorize your 150 hand-labeled transactions and report the score | Yes (cents) | `python scripts/eval_categories.py` |

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["live: calls real APIs (costs money)"]
addopts = "-m 'not live'"
```

### Example unit tests
```python
# tests/test_reconcile.py
from finance.extract import Txn
from finance.reconcile import check


def row(date, debit=None, credit=None, balance=None):
    return Txn(date=date, description="test", debit=debit, credit=credit, balance=balance)


def test_balanced_statement_passes():
    rows = [row("2026-11-01", debit=50, balance=950), row("2026-11-02", credit=100, balance=1050)]
    assert check(1000, 1050, rows) == []


def test_wrong_row_is_pinpointed():
    rows = [row("2026-11-01", debit=50, balance=950), row("2026-11-02", debit=10, balance=900)]
    issues = check(1000, 900, rows)
    assert len(issues) == 1 and issues[0].startswith("Row 2")


def test_credit_card_balance_goes_up_with_spending():
    rows = [row("2026-11-01", debit=40, balance=140)]
    assert check(100, 140, rows, is_card=True) == []
```

```python
# tests/test_ids.py
from finance.extract import Txn
from finance.ids import merchant_key, transaction_ids


def coffee():
    return Txn(date="2026-11-01", description="CAFE 12", debit=3.5, credit=None, balance=None)


def test_identical_coffees_get_different_ids():
    a, b = transaction_ids("bank:1234", [coffee(), coffee()])
    assert a != b


def test_same_statement_twice_gives_same_ids():
    assert transaction_ids("bank:1234", [coffee()]) == transaction_ids("bank:1234", [coffee()])


def test_merchant_key_ignores_reference_codes():
    assert merchant_key("AMZN Mktp US*2K4L95 Seattle") == merchant_key("AMZN Mktp US*9QX71 Seattle")
```

### Fake statement generator
```python
# scripts/make_fake_statement.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROWS = [  # date, description, money out, money in
    ("2026-11-02", "POS 4471 FRSHMRT*CTY", 54.20, None),
    ("2026-11-03", "SALARY ACME CORP", None, 3000.00),
    ("2026-11-05", "CITY CABS 0091", 64.00, None),
    ("2026-11-06", "STREAMFLIX.COM", 15.99, None),
]


def money(x):
    return f"{x:,.2f}" if x else ""


def make(path="tests/data/fake_statement.pdf", opening=1000.00):
    c = canvas.Canvas(path, pagesize=A4)
    c.drawString(50, 800, "EXAMPLE BANK  -  Statement 01 Nov 2026 to 30 Nov 2026")
    c.drawString(50, 785, f"Account ending 1234     Opening balance: {opening:,.2f}")
    y, balance = 750, opening
    for date, description, out, money_in in ROWS:
        balance += (money_in or 0) - (out or 0)
        c.drawString(
            50, y, f"{date}  {description:<26}{money(out):>12}{money(money_in):>12}{balance:>14,.2f}"
        )
        y -= 16
    c.drawString(50, y - 10, f"Closing balance: {balance:,.2f}")
    c.save()


if __name__ == "__main__":
    make()
```

### Categorization accuracy
`tests/data/labeled.csv` holds about 150 of your own transactions with the correct category (keep this file **local**, as it's real data). `scripts/eval_categories.py` runs them through `ask_claude()` and prints:

```
Accuracy: 143/150 = 95.3%  ✅ (target ≥ 95%)
Most common mix-ups:
  Grocery → Other        3   (e.g. "CORNER STORE 22")
  Subscriptions → Other  2   (e.g. "APPLE.COM/BILL")
  Savings → Investments  2   (e.g. "TRF TO RD A/C")
Cost of this run: $0.04
```

Run it again after every prompt change, to check the change actually helped.

---

## 13. Cost and speed controls

| Lever | Effect |
|---|---|
| **Saved rules and keywords first** | Repeat shops cost nothing. Most rows are free from month 2. |
| **Fingerprint check first** | Re-uploads cost nothing |
| **3 pages per request** | Answers stay short and reliable, and a retry only redoes a small piece |
| **~100 rows per categorization request** | The instructions are sent once per 100 rows, not once per row |
| **Spend limit in the Claude Console** | A bug can't produce a surprise bill |
| **`ai_calls` cost log** | `python cli.py costs` shows the actual spend per statement |
| **Later: test a smaller model** | Once the accuracy eval exists, try a cheaper model for categorization and keep it only if the score holds |

---

## 14. Coding conventions

- **Formatting:** `ruff format` and `ruff check` before every commit.
- **Type hints** on every function, so editors and readers know what goes in and comes out.
- **Engine functions return results, never `print()`.** Only `cli.py` and `app.py` talk to the user.
- **Small functions with plain-English docstrings.** If a non-developer can't follow the docstring, rewrite it.
- **No secrets in code.** Keys come from `.env`, passwords from the Keychain.
- **All SQL lives in `ledger.py`.**
- **Every bug fix comes with a test** that would have caught it.

---

## 15. Phase 6: optional small API

> 💡 Only needed if you want phone shortcuts or other apps to talk to the engine. It's the same engine behind a different door.

| Method | Path | Does |
|---|---|---|
| `POST` | `/statements` | Upload a PDF → returns the `Result` |
| `GET` | `/statements` | List statements and statuses |
| `GET` | `/review` | Rows waiting for review |
| `PATCH` | `/transactions/{id}` | Change a row's category |
| `POST` | `/sync` | Run a sync |
| `GET` | `/summary?month=2026-11` | Totals per category for a month |

Built with FastAPI, bound to `localhost` only, and protected with a secret token if it's ever reachable from another device.
