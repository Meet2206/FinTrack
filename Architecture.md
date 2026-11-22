# 🏗️ Architecture

[Readme](Readme.md) · [Plan](Plan.md) · **Architecture** · [Backend](Backend.md) · [DB](DB.md) · [Testing](TESTING.md) · [Reason](Reason.md) · [Prompts](prompts/README.md)

| | |
|---|---|
| **What this document is** | How the system is put together: the parts, how data flows between them, where your data goes, and why it was designed this way. |
| **Who it's for** | Everyone. Each section starts with a plain-English summary (💡), followed by the technical detail. |
| **Read first** | [Plan](Plan.md) explains *what* we're building. This document explains *how*. |
| **Status** | ✅ Built (v1.0). The code matches this design. |

---

## 1. The big picture: a mailroom

> 💡 **In plain English:** picture a small, very careful mailroom.
>
> 1. An **envelope arrives** (your statement PDF).
> 2. A clerk **opens it**, using the key if it's locked.
> 3. A fast reader (**Claude, the AI**) **types out every line** onto a standard form.
> 4. An accountant **checks the math**: do the numbers add up to the balance the bank printed? If not, they stop and ask you.
> 5. A sorter **puts each line in the right tray**: Grocery, Travel, Subscriptions, Investments, Savings, Other, Not an expense.
> 6. Everything is written into a **master logbook** (the *ledger*) that never loses or duplicates anything.
> 7. You **glance at the few lines** the sorter wasn't sure about.
> 8. A copier **copies each tray into its own binder** (Google Sheet), one section per month.

| Mailroom | In our system | Technology |
|---|---|---|
| Envelope | Statement PDF | PDF file |
| Clerk who opens it | PDF tools | `pypdf` |
| Fast reader | Extractor | Claude API + Pydantic |
| Accountant | Reconciler | Plain Python |
| Sorter | Categorizer | Saved rules + Claude API |
| Master logbook | Ledger | SQLite database (`data/ledger.db`) |
| Your quick glance | Review queue | Streamlit web app |
| Copier and binders | Sheets mirror | Google Sheets API (`gspread`) |
| Mailroom manager | Pipeline | Plain Python |

---

## 2. System diagram

> 💡 **In plain English:** almost everything runs **on your laptop**. Only two things go over the internet: pages sent to **Claude** to be read, and finished rows sent to **Google Sheets**.

```
┌─────────────────────────────────── YOUR LAPTOP ───────────────────────────────────┐
│                                                                                    │
│   ┌────────────────────┐        ┌───────────────────────────────────────────────┐  │
│   │  YOU               │        │  THE ENGINE   (Python package: finance/)      │  │
│   │                    │        │                                               │  │
│   │  ┌──────────────┐  │        │   pipeline ── the manager that runs each step │  │
│   │  │ Web app      │──┼───────▶│     │                                         │  │
│   │  │ (Streamlit)  │  │        │     ├─▶ pdf_tools   open, unlock, split        │  │
│   │  └──────────────┘  │        │     ├─▶ extract     ask Claude to read pages   │  │
│   │  ┌──────────────┐  │        │     ├─▶ reconcile   check the math             │  │
│   │  │ Command line │──┼───────▶│     ├─▶ categorize  rules, then Claude         │  │
│   │  │ (cli.py)     │  │        │     ├─▶ alerts      spot weird charges         │  │
│   │  └──────────────┘  │        │     └─▶ sheets      mirror to Google Sheets    │  │
│   │  ┌──────────────┐  │        │                                               │  │
│   │  │ Folder       │──┼───────▶│   ledger ── reads and writes the database     │  │
│   │  │ watcher (P6) │  │        │   config ── reads config.yaml + .env          │  │
│   │  └──────────────┘  │        └──────┬──────────────────┬─────────────┬───────┘  │
│   └────────────────────┘               │                  │             │          │
│                                        ▼                  │             │          │
│   ┌──────────────────────┐   ┌──────────────────┐         │             │          │
│   │ data/statements/*.pdf│   │ data/ledger.db   │         │             │          │
│   │ (your original PDFs) │   │ (SQLite: master  │         │             │          │
│   └──────────────────────┘   │  copy of records)│         │             │          │
│                              └──────────────────┘         │             │          │
│   macOS Keychain: PDF passwords      .env: API keys       │             │          │
└───────────────────────────────────────────────────────────┼─────────────┼──────────┘
                                          HTTPS (encrypted) │             │ HTTPS (encrypted)
                                                            ▼             ▼
                                              ┌──────────────────┐  ┌──────────────────────┐
                                              │ Claude API       │  │ Google Sheets API    │
                                              │ (Anthropic)      │  │                      │
                                              │ reads PDF pages, │  │ 5 spreadsheets       │
                                              │ sorts rows       │  │ × monthly tabs       │
                                              └──────────────────┘  └──────────────────────┘
```

**Three ways in, one engine.** The web app, the command line and (later) the folder watcher are just different *doors*. They all call the same engine, so there's only one copy of the real logic.

---

## 3. The components

| Component | 💡 Plain English | Tech | File | Details |
|---|---|---|---|---|
| **Web app** | The screens you click: upload, review, dashboard | Streamlit | `app.py`, `pages/` | [Backend §9](Backend.md#9-the-web-app-apppy) |
| **Command line** | The same features, typed in a terminal | Typer | `cli.py` | [Backend §8](Backend.md#8-the-command-line-clipy) |
| **Pipeline** | The manager: runs each step in order and handles problems | Python | `finance/pipeline.py` | [Backend §7.12](Backend.md#712-pipelinepy-the-manager) |
| **PDF tools** | Opens the PDF, unlocks it, splits it into small page groups | `pypdf` | `finance/pdf_tools.py` | [Backend §7.2](Backend.md#72-pdf_toolspy-open-unlock-split) |
| **Extractor** | Sends page groups to Claude and gets back a filled-in form | Anthropic SDK, Pydantic | `finance/extract.py` + [`prompts/app/extract-statement.md`](prompts/app/extract-statement.md) | [Backend §7.3](Backend.md#73-extractpy-claude-reads-the-pages) |
| **Reconciler** | Checks the math row by row | Python | `finance/reconcile.py` | [Backend §7.4](Backend.md#74-reconcilepy-check-the-math) |
| **IDs** | Makes fingerprints for transactions and shop names | `hashlib`, `re` | `finance/ids.py` | [Backend §7.5](Backend.md#75-idspy-fingerprints) |
| **Categorizer** | Saved rules first, then Claude for unknown shops | Anthropic SDK | `finance/categorize.py` + [`prompts/app/categorize-transactions.md`](prompts/app/categorize-transactions.md) | [Backend §7.6](Backend.md#76-categorizepy-sort-into-categories) |
| **Ledger** | Reads and writes the master database | `sqlite3` | `finance/ledger.py` | [DB](DB.md) |
| **Sheets mirror** | Copies the ledger into the 5 Google Sheets | `gspread` | `finance/sheets.py` | [Backend §7.8](Backend.md#78-sheetspy-the-google-sheets-mirror) |
| **Alerts** | Looks for double charges, price increases and so on | `pandas` | `finance/alerts.py` | [Backend §7.10](Backend.md#710-alertspy-spot-weird-charges) |
| **Cost tracker** | Logs what every AI call cost | Python | `finance/costs.py` | [Backend §7.11](Backend.md#711-costspy-what-did-the-ai-cost) |
| **Config** | Reads the settings file and secret keys | Pydantic, PyYAML, python-dotenv | `finance/config.py` | [Backend §5](Backend.md#5-configuration) |

---

## 4. The journey of one statement

> 💡 **In plain English:** this is everything that happens between "you drop a PDF" and "it's in Google Sheets", step by step.

### Sequence diagram

```
 You         Web app/CLI      Pipeline          Claude API      Ledger (SQLite)     Google Sheets
  │               │               │                  │                 │                  │
  │ drop PDF ────▶│               │                  │                 │                  │
  │               │ process() ───▶│                  │                 │                  │
  │               │               │ fingerprint file │                 │                  │
  │               │               │─────────────────────────────────── ▶ seen before?     │
  │               │               │◀─────────────────────────────────── no, new statement  │
  │               │               │ unlock + split   │                 │                  │
  │               │               │ (3 pages/group)  │                 │                  │
  │               │               │ pages 1–3 ──────▶│                 │                  │
  │               │               │◀──── form: rows  │                 │                  │
  │               │               │ pages 4–6 ──────▶│                 │                  │
  │               │               │◀──── form: rows  │                 │                  │
  │               │               │ join + check math│                 │                  │
  │               │               │ save rows ─────────────────────────▶ (duplicates      │
  │               │               │                  │                 │  ignored)        │
  │               │               │ saved rules?  ─────────────────────▶                  │
  │               │               │ unknown shops ──▶│                 │                  │
  │               │               │◀── categories    │                 │                  │
  │               │               │ save categories ───────────────────▶                  │
  │               │◀── summary ───│                  │                 │                  │
  │◀── "7 to review"              │                  │                 │                  │
  │ approve rows ▶│ save fixes ───────────────────────────────────────▶ (+ learn rules)   │
  │ click Sync ──▶│ sync() ──────▶│ what changed? ─────────────────────▶                  │
  │               │               │ rebuild changed month tabs ───────────────────────────▶
  │               │               │ mark as synced ────────────────────▶                  │
  │◀── "Done ✅" ──│               │                  │                 │                  │
```

### The steps in detail

| # | Step | 💡 What happens | Technical detail |
|---|---|---|---|
| 1 | **Fingerprint** | Make a unique code from the file. If we've seen it, stop: nothing to do. | SHA-256 of the file's bytes, looked up in `statements.file_hash` |
| 2 | **Unlock** | If the PDF is password-protected, unlock it on your laptop. The password never leaves your computer. | `pypdf` decrypts locally; password from the form or the macOS Keychain |
| 3 | **Split** | Cut the PDF into groups of 3 pages, so each AI answer stays short and reliable. | `pypdf` writes new, unlocked mini-PDFs in memory |
| 4 | **Read (extract)** | Claude reads each group and fills in a strict form: date, description, money out, money in, balance. | `client.messages.parse(..., output_format=StatementChunk)` returns a validated Pydantic object |
| 5 | **Join** | Put the groups back together in order. | Header fields from the first group, closing balance from the last |
| 6 | **Check the math and dates** | Start from the opening balance, apply every row, and compare to the bank's printed balance each time. Also check every date is real and inside the statement period. | Tolerance of 0.01; any mismatch is pinpointed to its row; dates ±7 days around the period |
| 7 | **Save** | Write the rows to the ledger. Rows we already have (from an overlapping statement) are skipped. | `INSERT OR IGNORE` keyed on the transaction fingerprint |
| 8 | **Categorize** | Known shops: instant, from saved rules. Unknown shops: Claude, about 100 rows per request. | Rule lookup → keyword match → AI with your past corrections as examples |
| 9 | **Flag for review** | Rows the AI wasn't sure about, plus every row of a statement whose math didn't check out. | `needs_review = 1` plus a reason |
| 10 | **Alerts** | Look for double charges, unusual amounts, new subscriptions. | pandas over the ledger history |
| 11 | **You review** | Fix or approve flagged rows. Your fixes become saved rules. | `category_source = 'user'`, rule saved in `merchant_rules` |
| 12 | **Sync** | Find which (category, month) tabs changed, rebuild just those, refresh the Summary tabs. | See [D4](#d4-sync-rebuilds-whole-month-tabs) |

---

## 5. Statement lifecycle

> 💡 **In plain English:** every statement has a *status* that tells you where it's up to, like a parcel tracking page.

```
                    ┌──────────────────────────── retry ─────────────────────────────┐
                    ▼                                                                │
  ┌──────────┐   ┌────────────┐   math OK    ┌─────────┐   all rows synced   ┌────────┐
  │ uploaded │──▶│ processing │─────────────▶│  ready  │────────────────────▶│ synced │
  └──────────┘   └─────┬──────┘              └─────────┘                     └────────┘
                       │  │                        ▲
                       │  │ math doesn't match     │ you fix the rows or approve
                       │  └──────────▶ ┌──────────┐│
                       │               │ mismatch │┘
                       │               └──────────┘
                       │ wrong password / not a statement / AI error
                       └──────────────▶ ┌────────┐
                                        │ failed │──── (fix the cause, then retry)
                                        └────────┘
```

| Status | 💡 Meaning | What you see in the app |
|---|---|---|
| `uploaded` | File received, not started yet | ⚪ Waiting |
| `processing` | Being read and sorted | 🔵 Working… |
| `mismatch` | The numbers don't add up. Waiting for you. | 🔴 "Numbers don't match – check row 37" |
| `ready` | Verified and sorted. Rows sync once reviewed. | 🟡 "7 rows to review", or 🟢 "Ready to sync" |
| `synced` | Every row is in Google Sheets | 🟢 In Google Sheets |
| `failed` | Couldn't be processed. The reason is saved. | 🔴 "Wrong password" / "Not a bank statement" |

## 6. Transaction lifecycle

```
 read from PDF ─▶ saved in ledger ─▶ categorized ─┬─▶ confident ──────────────┐
                                                  │                           ▼
                                                  └─▶ unsure ─▶ you review ─▶ approved
                                                                              │
                                     ┌──────────── in Google Sheets ◀── sync ─┘
                                     │
                                     └─▶ you change it later ─▶ marked "changed" ─▶ next sync moves it
```

A row is copied to Google Sheets only when it is **approved** (confident, or reviewed by you) and its statement's math checked out (or you approved the statement).

---

## 7. Design decisions (and why)

> 💡 **In plain English:** every system involves trade-offs. These are the big choices we made, what we gave up, and what we considered instead.

### D1. Claude reads the PDF directly
- **Decision:** send each group of pages to Claude, which returns a strict form (structured output).
- **Why:** every bank's PDF layout is different. Hand-written readers break whenever a bank changes its layout, and they can't handle scanned statements. Claude reads text *and* visual layout, so it works with any bank from day one.
- **Trade-off:** a few cents per statement, and the AI could misread a number. That's why D2 exists.
- **Alternatives considered:** `pdfplumber` table extraction (free and exact, but needs per-bank tuning; planned as a Phase 7 fast path), traditional OCR (poor on tables), bank CSV exports (not every bank offers them).

### D2. The math check is a gate
- **Decision:** nothing reaches Google Sheets unless opening balance + money in − money out matches the printed balances (or you explicitly approve the statement).
- **Why:** the bank's own running balance is a free answer key. If every row's balance agrees, every amount is right. This turns "the AI is probably right" into "the numbers are *proven* right".
- **Trade-off:** statements without any printed balance can't be verified automatically, so they always go to review.

### D3. The ledger is the master, Google Sheets is a mirror
- **Decision:** the SQLite database on your laptop is the single source of truth. Google Sheets are generated from it.
- **Why:** with two places you can edit, they eventually disagree. With one master you can rebuild the sheets anytime (after a bug, a category change, or an accidental deletion), and duplicates are impossible by design.
- **Trade-off:** hand edits in Sheets get overwritten. Mitigation: all editing happens in the app, and the docs say so clearly.
- **Alternative considered:** using Google Sheets as the database. That's slower, there's no real duplicate protection, and it's easy to corrupt by accident.

### D4. Sync rebuilds whole month tabs
- **Decision:** a sync finds which (category, month) tabs are affected by changed rows, then **clears and rewrites those tabs completely** from the ledger. It never adds rows one by one.
- **Why:** this makes sync **repeatable**. Run it twice and you get the same result. If it crashes halfway, just run it again. A row that changes category automatically disappears from the old sheet and appears in the new one.
- **Trade-off:** slightly more data written than an "append" approach. That doesn't matter at personal scale (a few hundred rows a month).

### D5. 5 spreadsheets × monthly tabs
- **Decision:** one spreadsheet per category, one tab per month (`YYYY-MM`), plus a `Summary` tab with formula totals.
- **Why:** it's what was asked for. Each category is easy to open, share or chart on its own.
- **Trade-off:** comparing categories means opening several files. Mitigation: the app's dashboard shows everything together, and a single "Overview" sheet is a Phase 7 option.
- **Alternatives considered:** one spreadsheet with 5 tabs plus a Month column (easier pivot tables), or one spreadsheet per month. Either could be added later by changing only `sheets.py`, because the ledger doesn't care.

### D6. Saved rules before AI
- **Decision:** check (1) rules learned from you and from earlier confident AI answers, then (2) keyword rules from the settings file, and only then (3) ask Claude.
- **Why:** it's cheaper (repeat shops cost nothing), faster, and **consistent**: the same shop always gets the same category.
- **Trade-off:** a wrong rule repeats its mistake. Mitigation: you can see and edit rules, and your own fixes always win.

### D7. Confidence labels and a review queue
- **Decision:** the AI labels each answer `high`, `medium` or `low` confidence. By default, medium and low go to the review queue.
- **Why:** you spend your attention only where it's needed. We use labels instead of percentages because AI-reported percentages (like "87% sure") are poorly calibrated; three simple levels are more honest.

### D8. Streamlit + a command line (not a separate front-end and back-end)
- **Decision:** a Streamlit web app and a Typer command line, both calling the same Python engine directly.
- **Why:** a single developer can build real screens in Python alone, without JavaScript or a separate server. It's the right size for a personal tool.
- **Trade-off:** less control over design, and not suited to many users. If that's ever needed, a small FastAPI layer can sit in front of the same engine (see [§13](#13-future-architecture-phase-6)).

### D9. Runs on your laptop
- **Decision:** no cloud server in version 1.
- **Why:** privacy (your financial records stay with you), zero hosting cost, and nothing to secure on the public internet.
- **Trade-off:** automation only runs while your laptop is on. Phase 6 can move it to an always-on mini computer.

### D10. Python
- **Why:** the best-supported language for AI SDKs, PDFs, data analysis (pandas) and Google APIs, and the easiest to read for a learning project.

---

## 8. What leaves your computer

> 💡 **In plain English:** a clear list of exactly what goes where. Anything not listed here never leaves your laptop.

| Data | Stays on your laptop | Sent to Claude (Anthropic) | Sent to Google Sheets |
|---|---|---|---|
| Statement PDF (original) | ✅ `data/statements/` | Page groups, after unlocking ⚠️ | ❌ |
| Your name and address (on the PDF) | ✅ | ⚠️ Yes, as part of the pages (v1). Removed in Phase 7 "privacy mode". | ❌ |
| Full account number | ✅ | ⚠️ Yes, as part of the pages (v1) | ❌ Only the **last 4 digits** |
| PDF passwords | ✅ macOS Keychain only | ❌ The PDF is unlocked *before* sending | ❌ |
| Transactions (date, description, amount) | ✅ ledger | ✅ for categorizing unknown shops | ✅ Only the 5 categories (plus "Other" if you turn it on) |
| "Not an expense" rows (salary etc.) | ✅ | ✅ for categorizing | ❌ Never written to any sheet |
| Your corrections | ✅ | ✅ as examples, so the AI copies your choices | ❌ |
| API keys | ✅ `.env` file | Used to authenticate | Used to authenticate |

**Security rules built into the design:**
1. **Secrets are never committed to git.** `.env`, `service_account.json`, `data/` and `*.pdf` are in `.gitignore` from the very first commit.
2. **The robot account has minimal access.** The Google service account can open only the 5 spreadsheets you shared with it, not your Drive.
3. **The web app is reachable only from your own computer.** Start it with `--server.address localhost` so others on your Wi-Fi can't open it.
4. **The 5 spreadsheets stay private.** They describe your finances. Don't share them publicly.
5. **Logs record IDs and counts,** not full descriptions or account numbers.
6. **Tests use made-up statements.** Real statements never go into the `tests/` folder.

---

## 9. When things go wrong

> 💡 **In plain English:** what you'll see, and what the system does, when something fails. The guiding rule is **fail safely**: never write half-finished or unverified data to your sheets.

| What goes wrong | What you see | What the system does |
|---|---|---|
| Wrong or missing PDF password | "This PDF is locked. Enter its password." | Status `failed`. Nothing is sent anywhere. Retry with the right password. |
| PDF isn't a bank statement | "This doesn't look like a bank or card statement." | Status `failed`. Nothing saved. |
| Same file uploaded again | "Already processed on 22 Nov. Nothing to do." | Stops immediately. Zero cost. |
| The math doesn't add up | "Row 37: expected 1,204.50, statement shows 1,240.50" | Status `mismatch`. All rows held for review. You fix the row or approve the statement. |
| Statement has no balances at all | "Can't verify this statement automatically." | All rows go to review |
| A date is impossible or outside the statement period | "Row 4: date 2027-11-05 is outside the statement period" | Status `mismatch`. Fix the date on the Transactions page (it's re-checked automatically) or approve. |
| A quiet month with no transactions | "Read 0 transactions. ✅ Balances match" | Accepted. Nothing to sync. |
| Re-uploading a fresh copy after a failed attempt | Normal result | Rows already saved are skipped, and any still uncategorized are sorted now |
| The AI's answer was cut off (very long page group) | Nothing, it's automatic | Retries that group with fewer pages |
| Claude is busy or slow (rate limit, server error) | "Claude is busy. Try again in a minute." | The SDK retries automatically (twice). If it still fails: status `failed`, safe to retry. |
| No internet | "Can't reach Claude / Google. Check your connection." | Nothing half-written. Retry later. |
| The AI declines to process the content | "The AI couldn't process this statement." | Status `failed` with the reason. Very unlikely for bank statements. |
| A spreadsheet isn't shared with the robot | "Can't open the Grocery sheet. Share it with robot@….iam.gserviceaccount.com" | Sync stops before writing anything |
| Google rate limit | "Google asked us to slow down. Retrying…" | Waits and retries. Sync is repeatable, so this is always safe. |
| Sync crashed halfway | "Sync incomplete. Run it again." | The next sync rebuilds the affected tabs correctly |
| Database file deleted or corrupted | — | Restore from automatic backup (`data/backups/`), or re-process the PDFs |

---

## 10. Limits and performance

| Thing | Limit or expectation | Why it's fine |
|---|---|---|
| Statement size | The Claude API accepts PDFs up to 32 MB and 600 pages per request | We send 3 pages at a time |
| Processing time | Roughly 1–2 minutes for a typical 5–6 page statement | Groups could run in parallel later if needed |
| Categorizing | About 100 rows per AI request | A typical month is 1–2 requests, and fewer as rules build up |
| Google Sheets size | 10 million cells per spreadsheet | A month tab is about 7 columns × a few hundred rows. That's centuries of data. |
| Google API rate limits | Writes per minute are capped per user and per project | We write each tab in one request, and a typical sync makes only tens of requests |
| Database size | SQLite handles gigabytes easily | Personal finance is a few MB per decade |

---

## 11. Technology stack

| Layer | Tool | 💡 What it is | Why we chose it |
|---|---|---|---|
| Language | **Python 3.12+** | The programming language | Best AI and data libraries, readable |
| AI | **Claude Opus 5.5** via the `anthropic` SDK | The model that reads statements and sorts rows | Reads PDFs natively (text + visuals) and supports structured output |
| Data validation | **Pydantic** | Defines the "forms" the AI must fill in, and rejects bad answers | Catches malformed AI output instantly |
| PDF handling | **pypdf** (with `cryptography`) | Opens, unlocks and splits PDFs | Pure Python, handles encrypted PDFs |
| Database | **SQLite** (built into Python) | A database in a single file | No server, no setup, easy to back up |
| Google Sheets | **gspread** | Talks to the Google Sheets API | The simplest well-maintained library |
| Analysis | **pandas** | Spreadsheet-like data handling in code | For alerts and dashboard numbers |
| Web app | **Streamlit** + **Plotly** | Web screens and charts written in Python | No front-end coding needed |
| Command line | **Typer** | Turns Python functions into terminal commands | Clean, self-documenting commands |
| Settings | **PyYAML**, **python-dotenv** | Reads `config.yaml` and `.env` | Human-friendly settings, secrets kept separate |
| Secrets | **keyring** | Stores PDF passwords in the macOS Keychain | Passwords never sit in a plain text file |
| Testing | **pytest**, **reportlab** | Automated tests, and generating fake statement PDFs | Test without ever using real statements |

---

## 12. Deployment: where it runs

| Stage | Where | How it's started | Notes |
|---|---|---|---|
| **v1 (Phases 1–5)** | Your laptop | `streamlit run app.py --server.address localhost` | Simplest and most private |
| **v2 (Phase 6)** | Your laptop, in the background | The folder watcher starts at login (macOS `launchd`), plus a monthly scheduled job | Automation works while the laptop is on |
| **v3 (optional)** | An always-on mini computer at home (e.g. a Raspberry Pi) or a small private server | `systemd` service + cron | Needs a login screen, an encrypted disk and backups first |

Not planned: a public cloud deployment. That would mean adding user accounts, encryption at rest and much more security work, all for a single-person tool.

---

## 13. Future architecture (Phase 6+)

```
                ┌───────────────┐
 Gmail ────────▶│ Email fetcher │──┐
 (bank emails)  └───────────────┘  │     ┌─────────────────┐
                ┌───────────────┐  ├────▶│  data/inbox/    │
 You ──────────▶│ Drop a PDF in │──┘     └────────┬────────┘
                │ a folder      │                 │ watched
                └───────────────┘                 ▼
                                          ┌────────────────┐     ┌──────────────┐
                                          │  Folder watcher│────▶│  THE ENGINE  │ (unchanged)
                                          └────────────────┘     └──────┬───────┘
                                                                        │
                       ┌────────────────────────────┬───────────────────┤
                       ▼                            ▼                   ▼
               ┌───────────────┐           ┌────────────────┐   ┌──────────────┐
               │ Google Sheets │           │ Notifier       │   │ Small API    │
               │ (sync)        │           │ (Telegram /    │   │ (FastAPI,    │
               └───────────────┘           │  email)        │   │  optional)   │
                                           └────────────────┘   └──────────────┘
                                            "You spent 2,340      for phone
                                             in Nov. Travel ▲40%" shortcuts
```

**Key point:** the engine doesn't change. New features are new *doors in* (email fetcher, folder watcher, API) and new *doors out* (notifier). That's the payoff of keeping all the logic in one place.
