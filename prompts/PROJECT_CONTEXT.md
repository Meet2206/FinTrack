# Project context: "Where Did My Money Go?"

You are continuing work on an existing, working project, possibly on a different
computer from the one it was built on. This file is the handoff. Read it fully
before you change anything. The code is the source of truth; when this file and
the code disagree, trust the code and fix this file.

Last updated: 2026-11-22

---

## 1. What the project is

A personal finance app that runs on one person's laptop (built on macOS). The
user uploads a bank or credit card statement PDF. The app:

1. reads every transaction with Claude;
2. checks Claude's reading against the balances printed on the statement;
3. sorts each transaction into a category;
4. mirrors the results into five Google Sheets (Grocery, Travel, Subscriptions,
   Investments, Savings), one tab per month, adding to them with every upload;
5. shows a dashboard with alerts for unusual charges.

It is a single-user, local-first app. It is not a multi-user web service.

The owner is learning and building a portfolio. They write casually and like
detailed explanations that a non-technical reader can follow.

---

## 2. Current state

- **v1.0 is built and works end to end.** The work is committed locally on the
  `main` branch (`git log --oneline` shows the history). There is no git remote
  yet, and nothing has been pushed.
- **Tests:** 210 automated tests pass with no keys and no internet
  (`python -m pytest`, about 10 seconds). There are also 19 opt-in live tests
  that call the real Claude (`python -m pytest -m live`, about $0.50), which skip
  without a key.
- **Never verified against real services:**
  - real Claude reading real statements (no API key has been added yet);
  - real Google Sheets access (no service account yet);
  - how the web pages look in a browser. They're tested with Streamlit's AppTest
    and HTTP 200 checks only.
- **Not set up yet:** `.env`, `config.yaml`, `service_account.json` and `data/`
  don't exist. No real statement has been processed.

---

## 3. First steps in a new session

1. Run `git status` and `git log --oneline -5` to see where things stand.
2. If `.venv/` is missing, set up the environment (section 9).
3. Run `python -m pytest`. It must pass before you change anything. If it fails
   on a fresh machine, fix the environment first, not the code.
4. Ask the user what they want to work on, and suggest items from section 12.

---

## 4. How a statement flows through the app

Statuses: `uploaded → processing → mismatch | ready → synced`, or `failed`.
`finance/pipeline.py` (`process_statement`) runs these steps in order:

1. **Fingerprint** the file (SHA-256). If it was uploaded before, stop.
2. **Unlock** it if it's password-protected: a typed password, or one saved
   with `keyring` (the macOS Keychain on a Mac).
3. **Split** it into groups of 3 pages.
4. **Extract:** send each group to Claude (`claude-opus-5-5`) with
   `client.messages.parse(output_format=StatementChunk)` (structured outputs
   with Pydantic).
   - `stop_reason == "max_tokens"` (or the answer doesn't fit the form) raises
     `ChunkTooLong`, and the page group is halved and retried.
   - `"refusal"` raises `AIDeclined`.
   - No API key raises `MissingAPIKey`, via `claude_parse`, which wraps the
     SDK's `TypeError`.
5. **Merge** the groups: the header comes from the first group, the closing
   balance from the last.
6. **Reconcile** (`reconcile.check`): the opening balance plus every row must
   match every printed running balance and the closing balance, within 0.01.
   - On a credit card, spending makes the balance go up.
   - A wrong row is named exactly, and checking resumes from the printed
     balance so later rows aren't blamed.
   - `reconcile.check_dates` then checks that every date is real and within
     the statement period ±7 days.
   - Any problem sets the status to `mismatch` and holds the whole statement.
     The user can fix rows or approve it anyway.
7. **Save** the rows to SQLite with `INSERT OR IGNORE` on a content
   fingerprint: account + date + amount + normalized description + an
   occurrence counter for identical twins. Overlapping statements therefore
   never duplicate rows.
8. **Categorize** (`categorize.py`). Try these in order and stop at the first
   hit:
   1. A saved merchant rule. The user's own rules always beat rules learned
      from the AI.
   2. Keywords from config, matched as whole words; the first match wins.
   3. Claude, about 100 rows per request, using short row numbers and including
      the user's 40 most recent corrections as examples. It returns a clean
      shop name and a confidence of high, medium or low.

   A high-confidence answer becomes a saved rule. Medium and low answers go to
   the review queue. `ledger.uncategorized(db)` returns every pending row, not
   just this statement's.
9. **Alerts** (`alerts.py`): plain pandas arithmetic, never AI, wrapped in
   try/except so an alert bug can't fail a statement. Thresholds:
   - double charge within 2 days;
   - a charge more than 3× the median of at least 3 earlier charges at that
     shop (one alert per shop per day);
   - a shop's first charge of at least `large_charge` (200);
   - a free trial (a charge of 1.00 or less) followed by a real charge 7–30
     days later;
   - a subscription price rise of more than 2%;
   - a forgotten subscription: a monthly charge of 200 or less not filed as
     Subscriptions;
   - a category spike: more than 1.5× the previous 3-month average.

   A "monthly charge" is a shop in a spending category charged 3 or more
   times, with the last two gaps 26–35 days and the two charges before the
   latest within 10% of each other.
10. **Status:** the result reports the status saved in the database after
    `refresh_statement_statuses`.
11. **Sync** (`sync.py`, a separate step: a button or `cli.py sync`, or
    automatic with `auto_sync: true`).

---

## 5. Business rules (don't change these without asking the user)

- **Amounts:** one signed amount. Positive is money out, negative is money in.
- **Refunds** are negative, in the shop's original category. Money coming back
  from savings or investments is negative in that category.
- **"Not an expense":**
  - paying your own credit card bill, because the purchases are already on the
    card statement;
  - salary, interest, and transfers in.
- **Investments and Savings** are "set aside", reported separately from "spent".
  SPENDING categories means Grocery, Travel, Subscriptions and Other.
- **Months:** a row belongs to the month of its transaction date, not the
  statement's month.
- **Currency:** one currency, set in config. No conversion.
- **Account numbers:** only the last 4 digits are stored.
- **Review:** only medium- and low-confidence rows go to review. A math
  mismatch holds the whole statement, and nothing from a held statement
  reaches Google Sheets.

---

## 6. The Google Sheets model

- The SQLite ledger is the master. Google Sheets is a read-only mirror.
- Five spreadsheets, plus an optional sixth for Other. Their IDs are in
  `config.yaml`. A blank ID means "not set up yet", and that category is
  skipped.
- Each spreadsheet has a Summary tab first, then month tabs named `YYYY-MM`,
  newest first.
  - Month tab columns: Date, Merchant, Description, Amount, Currency, Account,
    Txn ID.
  - Values are written with `USER_ENTERED`.
  - Summary totals are formulas that point at the month tabs.
  - A tab that becomes empty is deleted.
- Sync rebuilds only the affected (category, month) tabs, each one whole. Every
  row stores `synced_category` and `synced_month`, so when a row's category or
  date changes, its old tab is rebuilt too. Running sync twice is always safe.
- Access is through a Google service account (`gspread`). If a sheet isn't
  shared with the service account, the message names the exact email address
  to share it with.

---

## 7. Code map

```
app.py, ui_common.py, pages/1_Review … 5_Setup.py   Streamlit web app (thin)
cli.py                                              Typer command line (thin)
finance/                                            ALL logic lives here
  config.py       Settings, load_settings (WDMMG_CONFIG env var picks the file; paths relative to it)
  pdf_tools.py    fingerprint, open_pdf (+ keyring passwords), page_groups, pages_as_pdf
  extract.py      Claude reads pages: Txn, StatementChunk, extract_statement, merge
  prompts.py      loads the AI's instructions from prompts/app/*.md
  reconcile.py    check (math), check_dates
  ids.py          transaction_ids, merchant_key, pretty_merchant
  categorize.py   rules → keywords → Claude; Labeled, Labels, ask_claude
  ledger.py       EVERY SQL statement lives here
  migrations/     001_init.sql, 002_synced_month.sql (PRAGMA user_version = 2)
  sheets.py       SheetsMirror: rebuild_tab, rebuild_summary, check_access
  sync.py         decides which tabs to rebuild
  alerts.py       alert rules (pandas)
  costs.py        token usage and cost of every AI call
  pipeline.py     process_statement, recheck_statement
  summary.py      monthly summary text + Telegram
  watcher.py      inbox folder: once, or keep watching (watchdog)
  setup_check.py  the setup checklist
  demo.py         fake statement builder, write_pdf, fake_claude (tests + demo)
prompts/app/      the LIVE prompts sent to Claude (text between prompt markers)
scripts/          demo.py, check_setup.py, make_fake_statement.py, make_test_fixtures.py,
                  eval_categories.py, check_doc_links.py
conftest.py       root: the `--report` option that writes results into TESTING.md
tests/            conftest.py (fixtures), scenarios.py (S01–S34 + pretend Claudes),
                  fake_gspread.py (in-memory Google Sheets), test_*.py, fixtures/*.pdf (18 fake PDFs)
```

**Database:** SQLite at `data/ledger.db`. There are 7 tables (`accounts`,
`statements`, `transactions`, `merchant_rules`, `alerts`, `sync_runs`,
`ai_calls`) plus a `monthly_totals` view. See DB.md.

---

## 8. Commands

```
python cli.py --help              process, inbox, watch, status, review, approve, forget, sync,
                                  rebuild, alerts, summary, costs, rules, backup, check, password
python cli.py process FILE.pdf    (--ask-password, --dry-run)
python cli.py check               setup checklist (--offline skips network checks)
streamlit run app.py --server.address localhost
python scripts/demo.py            no-key demo in demo/; then:
WDMMG_CONFIG=demo/config.yaml streamlit run app.py --server.address localhost
python -m pytest                  210 tests, free
python -m pytest --report TESTING.md   same, and rewrites TESTING.md's results section
python -m pytest -m live          real Claude, about $0.50, needs ANTHROPIC_API_KEY
python scripts/eval_categories.py categorization accuracy on tests/data/labeled.csv (real API)
ruff format . && ruff check .     formatting and lint (Markdown is excluded)
python scripts/check_doc_links.py every link between the docs
```

---

## 9. Setting up on a new computer

1. Install Python 3.13 (3.12 or newer works).
2. Create the environment:
   `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
   On Windows, activate with `.venv\Scripts\activate`.
3. Run `python -m pytest`. It needs no keys.
4. For real use:
   - `cp config.example.yaml config.yaml` and fill in the sheet IDs;
   - `cp .env.example .env` and add `ANTHROPIC_API_KEY`;
   - put the Google service account key at `service_account.json`;
   - run `python cli.py check`.
5. PDF passwords saved with keyring stay in the old computer's keychain. Re-add
   them with `python cli.py password add <name>`.
6. These are private, never in git, and must be copied by hand (USB, AirDrop
   or a password manager, never chat or email) once they exist: `.env`,
   `config.yaml`, `service_account.json`, and `data/`. `data/ledger.db` is the
   master record, and the Google Sheets can be rebuilt from it but not the
   reverse.

---

## 10. How to work on this project

- **Keep the layers.** All logic lives in `finance/`. `app.py`, `pages/` and
  `cli.py` only collect input, call the engine and show results. All SQL lives
  in `ledger.py`.
- **The AI only copies and labels; code does all the math.** Everything Claude
  returns is checked before it's trusted.
- **Prompts live in `prompts/app/*.md`**, between `<!-- prompt:start -->` and
  `<!-- prompt:end -->` markers on their own lines. Everything outside the
  markers is notes for people. After editing a prompt:
  - run `python -m pytest`;
  - for categorization, run `scripts/eval_categories.py`;
  - for extraction, run `-m live`;
  - restart Streamlit, because prompts are read once at import.
- **Schema changes** go in a new numbered migration, `finance/migrations/003_….sql`.
  Never edit an old one. `migrate()` backs up the database first. Update DB.md.
- **Every bug fix gets a test.** Tests never use real statements, only
  generated fakes (`finance/demo.py`, `tests/scenarios.py`). The default run
  must never call real APIs. Use the pretend Claudes in `tests/scenarios.py`
  (`reading_claude`, `failing_claude`) and `tests/fake_gspread.py`.
- **Keep the docs true.** When code changes, update the matching docs in the
  same piece of work:
  - Backend.md for modules and the folder tree;
  - Architecture.md for the flow;
  - DB.md for the schema;
  - TESTING.md for the test areas and counts;
  - Reason.md for a new decision card: Chose / Over / Why / Trade-off /
    Revisit when;
  - this file.

  Test counts appear in Readme.md, Backend.md, TESTING.md and this file. Grep
  for the old number.
- **Doc style.** Plain English first: a 💡 summary before any code, jargon
  explained the first time it appears, real examples with numbers. Readme.md
  is deliberately funny and sarcastic, with memes. The other docs are detailed
  and calm.
- **Before saying "done", run all four and report the real results:**
  1. `ruff format . && ruff check .`
  2. `python -m pytest --report TESTING.md`
  3. `python scripts/check_doc_links.py`
  4. a quick demo or CLI run if the UI changed.

  Say plainly what you couldn't verify.
- **Privacy:**
  - never commit `.env`, `config.yaml`, `service_account.json`, `data/` or any
    real PDF (`.gitignore` already covers them);
  - never put the user's personal details into requests to outside services.
- **Ask the user first before:**
  - pushing, or creating a GitHub repo or remote;
  - deleting data;
  - changing a business rule from section 5;
  - spending money on live API runs beyond a few cents.

---

## 11. Gotchas that already cost time

- The original folder name ends with a space (`meet-project `). Quote paths. On
  a new machine, prefer a folder name without spaces.
- The `--report` option is defined in the **root** `conftest.py`. pytest
  doesn't register options from `tests/conftest.py` in time.
- ruff excludes `*.md`, because it was reformatting the code samples inside
  the docs.
- `.gitignore`:
  - it uses `/data/`, not `data/`, so `tests/data/` stays tracked;
  - `!tests/fixtures/*.pdf` re-includes the fake PDFs;
  - never put a comment on the same line as a pattern.
- In tests, enter `failing_claude` after `reading_claude`.
- Never monkeypatch `Path.stat` globally, because it breaks pytest itself. The
  file-still-growing test grows a real file with a fake sleep instead.
- Rich wraps long CLI messages, so CLI tests compare text with the whitespace
  collapsed.
- `spending_frame` parses dates with `errors="coerce"` and drops bad ones, so
  an impossible date can't crash the dashboard or alerts.

---

## 12. Open items

**Waiting on the user:**
- Add an API key, then run `python -m pytest -m live` and `python cli.py check`.
- Create the Google service account and the 5 sheets (Backend.md §4 has the
  steps), then process a first real statement.
- Decide whether to push to a private GitHub repo.
- `finance-tracker-plan.md` is an old, superseded brainstorm. It's untracked
  and can be deleted.

**Ideas deliberately postponed** (Reason.md §11 lists what would trigger each
one):
- fetching statements from Gmail;
- a privacy mode that strips names and numbers before the AI sees a statement;
- a local no-AI reader for one dominant bank;
- multiple currencies;
- budgets with warnings;
- plain-English questions ("travel in Q3?");
- PostgreSQL and multiple users;
- a small FastAPI for phone uploads;
- integer-cent money storage;
- yearly and weekly subscription detection.

---

## 13. Where to read more

- Readme.md: overview and quick start.
- Plan.md: goals and phases.
- Architecture.md: the flow and the failure handling.
- Backend.md: setup, every module, the CLI and the pages.
- DB.md: tables and migrations.
- TESTING.md: what's tested, and the latest results.
- Reason.md: why each decision was made, and what was rejected.
- prompts/app/*.md: the exact words sent to Claude.
