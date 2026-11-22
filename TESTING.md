# 🧪 Testing: how we know it works

[Readme](Readme.md) · [Plan](Plan.md) · [Architecture](Architecture.md) · [Backend](Backend.md) · [DB](DB.md) · **Testing** · [Reason](Reason.md) · [Prompts](prompts/README.md)

| | |
|---|---|
| **What this document is** | Everything about how the app is tested: what is checked, how, with which files, what the tests caught, and what they *can't* check. |
| **Who it's for** | Everyone. You don't need to read code. Each section starts with a 💡 plain-English summary. |
| **Current status** | See [Latest results](#13-latest-results) at the bottom. It's written by the test run itself, so it's never out of date. |

---

## 1. The one-minute version

> 💡 A **test** is a small program that uses the app the way a person would, then checks the result. For example: *"upload a statement where the AI misreads one amount, and check that the app catches it and holds everything back."* We have hundreds of them, and they run in about 10 seconds.

| Number | What it means |
|---|---|
| **210** automated tests | Run with one command, free, no internet needed |
| **34** statement scenarios | Real-life situations: normal months, locked PDFs, credit cards, AI mistakes, broken files, AI outages… |
| **18** fixture files | Fake statement PDFs in [`tests/fixtures/`](tests/fixtures/) that you can open or upload yourself |
| **19** live tests | The same fixture files sent to the **real** Claude (optional, costs about $0.50) |
| **10** real bugs | Found by these tests and fixed before you ever saw them ([§9](#9-bugs-the-tests-caught)) |
| **0** real bank statements | Tests only ever use made-up data |

---

## 2. How to run the tests

```bash
cd ~/Documents/meet-project
source .venv/bin/activate

python -m pytest                          # all 210 automated tests (~10 seconds, free)
python -m pytest --report TESTING.md      # same, and refresh the results at the bottom of this file
python -m pytest tests/test_scenarios.py  # just the statement scenarios
python -m pytest -k credit                # just tests with "credit" in their name
python -m pytest -m live                  # the REAL Claude (needs ANTHROPIC_API_KEY, ~$0.50)
python scripts/make_test_fixtures.py      # re-create the fixture PDFs in tests/fixtures/
```

What you'll see:

```
........................................................................ [ 35%]
........................................................................ [ 70%]
..............................................................           [100%]
210 passed, 19 deselected in 8.09s
```

Each dot is one passed test. An `F` would mean a failure, followed by an explanation of what went wrong. "19 deselected" are the live tests, which only run when you ask for them.

---

## 3. What's real and what's simulated

> 💡 The tests run the **real app code** almost everywhere. Only the outside services are swapped for stand-ins: Claude, Google Sheets, your Keychain and Telegram. Using the real ones in automated tests would cost money, need your passwords, change your real spreadsheets, and give different answers on different days.

| Part of the app | In the tests | How |
|---|---|---|
| Opening, unlocking and splitting PDFs | ✅ **Real** | Real PDFs drawn by `finance/demo.py`, some password-locked with AES-256 |
| The math check (reconciliation) and date check | ✅ **Real** | |
| Fingerprints, duplicate protection | ✅ **Real** | |
| Database (SQLite), upgrades, backups | ✅ **Real** | A fresh temporary database for every test |
| Categorization rules, keywords, review queue | ✅ **Real** | |
| Sync decisions (which tabs to rebuild) | ✅ **Real** | |
| The Google Sheets writer (`SheetsMirror`) | ✅ **Real code** against 🎭 a fake Google | `tests/fake_gspread.py` behaves like Google: fixed grid sizes, unique tab names, unshared sheets refuse to open, formulas can be evaluated |
| Alerts, summaries | ✅ **Real** | |
| Command line | ✅ **Real** | Every command run as if typed (`typer.testing.CliRunner`) |
| Web pages | ✅ **Real** | Streamlit's own headless tester runs each page and clicks buttons |
| **Claude** | 🎭 Stand-ins (see §4) | Plus 🌐 optional live tests with the real Claude |
| **Google Sheets API** | 🎭 Fake | `tests/fake_gspread.py` |
| **macOS Keychain** | 🎭 In-memory | Your real Keychain is never touched by tests |
| **Telegram** | 🎭 Fake network | |

---

## 4. The three stand-in "Claudes"

> 💡 To test how the app copes with the AI, we need an AI that behaves *exactly* the way each test wants: perfectly, wrongly in a specific way, or not at all. So the tests use three pretend versions.

| Stand-in | What it does | Used to test |
|---|---|---|
| **The reader** (`reading_claude`) | Actually **reads the text** of each page group it is sent, just like Claude receives them, and works out money in and out from how the balance moves | The real page-splitting, the "answer too long, so split and retry" logic, and the stitching of page groups back together |
| **The actor** (`fake_claude`) | Returns exactly the transactions the test tells it to, including **deliberate mistakes** (a misread amount, a skipped row, a wrong year…) | That every kind of AI mistake is caught |
| **The failure** (`failing_claude`) | Raises the same errors the real service does: busy, offline, server error, declined | That outages fail safely, with a clear message, and can be retried |

All three live in [`tests/scenarios.py`](tests/scenarios.py) (the actor in [`finance/demo.py`](finance/demo.py)).

---

## 5. What is tested, area by area

| Area | File | Tests | What it covers |
|---|---|---|---|
| 📄 Statement scenarios | [`test_scenarios.py`](tests/test_scenarios.py) | 40 | 34 single-statement situations ([§6](#6-the-34-statement-scenarios)) + 6 multi-upload situations (duplicates, overlaps, renamed copies, two accounts, card bill not double-counted, retry after failure) |
| 🧮 Building blocks | [`test_core.py`](tests/test_core.py) | 30 | Math check edge cases, fingerprints, keyword matching, settings, PDF locking, page splitting, cut-off answers, missing API key, the prompt files in `prompts/app/` (load exactly, every category described, broken or missing files explained) |
| 🔁 End-to-end flows | [`test_pipeline.py`](tests/test_pipeline.py) | 23 | PDF → database → sheets, review, rules learning, sync idempotence, forgetting, backups, inbox |
| 🗂️ Categorization | [`test_categorization.py`](tests/test_categorization.py) | 14 | Rules before AI, learning, your fixes win, configurable review threshold, batching by 100, what's sent to Claude, safe retries |
| 📊 Google Sheets + DB upgrades | [`test_sheets_mirror.py`](tests/test_sheets_mirror.py) | 18 | Tabs, headers, Summary formulas = ledger totals, tab order, moving rows between sheets and months, deleting empty tabs, 1,200-row months, unshared sheets, upgrading an old database |
| 🚨 Alerts | [`test_alerts.py`](tests/test_alerts.py) | 28 | Every alert rule tested **just above and just below** its threshold, plus false-alarm checks |
| ⌨️ Command line | [`test_cli.py`](tests/test_cli.py) | 19 | Every command, including mistakes (missing file, wrong password, no config, asking before deleting) |
| ⚙️ Settings & automation | [`test_settings_and_automation.py`](tests/test_settings_and_automation.py) | 24 | Mistakes in config.yaml, summary text, Telegram, inbox folder, auto-sync, file-still-copying, setup checklist |
| 🖥️ Web app | [`test_app.py`](tests/test_app.py) | 14 | Every page renders (with data and empty), buttons: approve all, dismiss alert, approve statement, back up, filters |
| 🌐 Live (opt-in) | [`test_live.py`](tests/test_live.py) | 19 | Real Claude reads every fixture so all balances match; real Claude categorizes obvious rows correctly |

---

## 6. The 34 statement scenarios

> 💡 Each scenario is one thing that can happen in real life. The test creates the PDF, runs the full app on it, and checks the outcome. The complete list with results is in [§13](#13-latest-results).

| Group | Scenarios | The app must… |
|---|---|---|
| **Normal statements** | S01 standard month · S02 320 rows over 20 pages · S03 answers too long for the AI · S04 one row · S05 a quiet month with zero rows | Read every row and verify it. Long statements are read in groups of 3 pages and stitched back together. |
| **Different kinds** | S06 credit card · S07 euros · S08 accents and quotes (`CAFÉ MÜLLER & SÖHNE`, `O'NEILL'S`) · S09 amounts over a million · S10 a 0.00 row · S11 a statement covering two months · S12 two identical coffees | Handle them all correctly. On a credit card, spending makes the balance go **up**. |
| **Locked PDFs** | S13 right password · S14 no password · S15 wrong password · S16 password saved in the Keychain | Unlock only with the right password, fail safely otherwise, never send the password anywhere |
| **Fewer balances printed** | S17 no opening balance · S18 only opening and closing · S19 no balances at all | Verify with whatever is printed. If nothing can be verified, hold every row for you. |
| **The AI makes a mistake** | S20 misread amount · S21 money in/out swapped · S22 skipped row · S23 row read twice · S24 misread closing balance · S25 wrong year · S26 impossible date (30 Feb) | **Catch it**, point at the exact row, and hold everything back from Google Sheets |
| **Wrong or broken files** | S27 a restaurant menu · S28 a blank page · S29 a half-downloaded file · S30 a page with too many rows | Reject politely, with a clear reason |
| **AI service problems** | S31 AI declines · S32 busy · S33 offline · S34 server error | Fail safely with a plain message. Retrying later is always safe. |

### Safety rules checked in *every* scenario
1. If a statement isn't fully verified, **none** of its rows can reach Google Sheets.
2. A failed statement saves **no** transactions and records a plain-English reason.
3. The statement's status in the database matches what the app reported.

---

## 7. How tests prove the math check works

> 💡 The math check is the app's most important safety net, so it gets the most attention: 7 deliberate AI mistakes (S20–S26), each of which must be caught.

```
What's printed on the PDF          What the "AI" read              Caught?
────────────────────────────────   ─────────────────────────────   ─────────────────────────────
CITY CABS      18.40               18.04                           ✅ Row 3: expected …, shows …
FRESH MART     54.20 out           54.20 in                        ✅ Row 2: balance moved the wrong way
STREAMFLIX     15.99               (skipped)                       ✅ Row 4: the next balance jumps
CITY CABS      18.40               (read twice)                    ✅ Row 4: the copy breaks the balance
Closing      3,584.31              3,684.31                        ✅ Closing balance doesn't match
05 Nov 2026                        05 Nov 2027                     ✅ Date outside the statement period
05 Nov 2026                        30 Feb 2026                     ✅ Not a valid date
```

The last two **couldn't** be caught by balances alone: a wrong date doesn't change any amount. The tests revealed that gap, and a date check was added (see [§9](#9-bugs-the-tests-caught), bug 5).

---

## 8. How the alert rules are tested

> 💡 An alert rule that fires too often gets ignored. One that never fires is useless. So every rule is tested **just inside** and **just outside** its limit.

| Rule | Fires | Doesn't fire |
|---|---|---|
| Double charge (same amount within 2 days) | same day ✅, 2 days later ✅ | 3 days later, a different amount |
| Unusually big charge (> 3× usual) | 151 when usual is 50 | exactly 150; fewer than 3 earlier charges |
| Big first charge from a new shop (≥ 200) | 200.00 | 199.99; transfers to savings |
| Free trial turned paid (≤ 1.00, then a charge 7–30 days later) | 7 days, 30 days | 6 days, 32 days, a 1.50 "trial" |
| Subscription price increase (> 2%) | 12.99 → 15.99 | 12.99 → 13.10 |
| Forgotten subscription (steady monthly charge ≤ 200, not filed as a subscription) | GymCo 29.99 × 3 months | rent, varying fuel, known subscriptions, savings, only 2 months |
| Category spike (> 1.5× the 3-month average) | with 3 months of history | with only 2 months of history |

---

## 9. Bugs the tests caught

> 💡 A test suite earns its keep by finding problems before you do. These were all found by tests or test runs during the build, and fixed. Each now has a test that keeps it fixed.

| # | What went wrong | What a user would have seen | Fix |
|---|---|---|---|
| 1 | The subscription detector flagged rent, fuel and savings transfers | A wall of useless alerts | Only steady, spending-category, monthly charges ≤ 200 not already filed as Subscriptions |
| 2 | One double charge produced two "big charge" alerts | Duplicate alerts | At most one big-charge alert per shop per day |
| 3 | With no API key, an obscure `TypeError` | "Something unexpected went wrong" | Clear "No Claude API key found. Add it to .env" |
| 4 | "Top shops" listed savings transfers | Savings shown as a shop | Top shops only counts spending |
| 5 | A misread **date** wasn't caught (balances can't see dates) | A row silently filed in the wrong month | New check: every date must be valid and inside the statement period (±7 days) |
| 6 | An impossible date (30 Feb) crashed the alert checker | A correct "please check" became "failed" | Alerts skip unreadable dates, and an alert problem can never fail a statement |
| 7 | A quiet month (0 transactions) was rejected as "not a statement" | A valid statement refused | Zero-transaction statements are accepted |
| 8 | The status reported after processing could differ from the saved status | "Ready" on screen, "In Google Sheets" in the list | The app reports the saved status |
| 9 | Fixing a misread date left a stale copy in the old month's tab | The same transaction in two month tabs | Database upgrade 002 also remembers the month tab, so the old tab is rebuilt |
| 10 | If categorizing failed half-way and you uploaded a freshly downloaded copy, the first rows stayed uncategorized forever | Rows stuck without a category | Every run sorts all rows still waiting for a category |

---

## 10. The fixture files: try it yourself

> 💡 [`tests/fixtures/`](tests/fixtures/) holds 18 fake statement PDFs, one per situation. Open them to see what the tests use, or **upload them in the app** (with a Claude key) to watch each situation happen.

The full list, with expected results and passwords, is in [`tests/fixtures/README.md`](tests/fixtures/README.md).

### A 10-minute hands-on check (needs a Claude key)

1. `streamlit run app.py --server.address localhost`
2. Upload **`S01-standard.pdf`** → expect *"Read 31 transactions. ✅ Balances match to the cent."* and a few rows to review.
3. Upload **`S01-standard.pdf` again** → expect *"Already processed… Nothing to do."*
4. Upload **`S14-locked-no-password.pdf`** without a password → expect *"This PDF is locked"*. Type `Dob-1990`, tick **Remember**, and process again → expect it to read.
5. Upload **`S06-credit-card.pdf`** → on **Transactions**, the flight is +289.00 (Travel) and the card payment is −400.00 (Not an expense).
6. Upload **`S27-not-a-statement.pdf`** → expect *"This doesn't look like a bank or card statement."*
7. Open **Review**, approve everything, then press **Sync to Google Sheets** (if Google is set up) and check each sheet has a `2026-11` tab and a Summary.
8. Open **Dashboard** → you should see a *double charge* alert for City Cabs.

---

## 11. Live tests with the real Claude

> 💡 Everything above uses stand-ins. The live tests send the fixture PDFs to the **real** Claude and check that it reads every one so that **all balances match**, and that it sorts obvious transactions correctly. Run them once after setup, and again whenever you change the AI instructions.

```bash
python -m pytest -m live      # skipped automatically if ANTHROPIC_API_KEY isn't set
```

- **Cost:** about $0.50 for the whole set (the 20-page statement is the biggest part).
- **What passing proves:** the real model, with our real instructions, reads these layouts perfectly.
- **What it can't prove:** that your bank's layout reads equally well. That's why the app checks the math on every real statement, every time.

---

## 12. What the tests do *not* cover (honestly)

| Not covered automatically | Why | What covers it instead |
|---|---|---|
| How well Claude reads **your bank's** layout | We can't put real statements in tests | The math check on every statement, plus the review queue |
| **Scanned, image-only** PDFs | The fixtures are text PDFs | Claude reads images. Try one of yours and the math check verifies it. |
| The real Google Sheets API (quotas, login) | Needs your account | `python cli.py check` tests your real access, and the fake Google mimics the important rules |
| How pages look in a real browser | Streamlit's tester runs headless | The hands-on check in [§10](#10-the-fixture-files-try-it-yourself) |
| The macOS Keychain itself | Tests must not touch your Keychain | `python cli.py password add/list` on your Mac |
| The long-running `watch` loop | It runs forever | The parts it uses (handler, file-still-copying wait, inbox processing) are tested |
| Real Telegram delivery | Needs your bot | `python cli.py summary --send` |

---

## 13. Latest results

> 💡 Everything between the markers below is written automatically by `python -m pytest --report TESTING.md`. Click an area to expand it.

<!-- TEST-RESULTS:START -->

**Last run:** 2026-11-22 18:55 · **210 passed** · 0 failed · 0 skipped · 6.2 s of test time · Python 3.13.13

<details><summary><b>📄 Statement scenarios: reading and checking real-life statements</b>: 40/40 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | **S01-standard**: A normal month: 2-page bank statement, 31 transactions → *Read every row, balances match, everything categorized* | ✅ |
| 2 | **S02-long-20-pages**: A very busy month: 320 transactions over 20 pages → *Read in groups of 3 pages, stitched back together, nothing lost* | ✅ |
| 3 | **S03-answer-too-long**: Page groups too long for one AI answer → *Split the group in half and re-read until it fits* | ✅ |
| 4 | **S04-one-row**: A statement with a single transaction → *Works the same as a big one* | ✅ |
| 5 | **S05-quiet-month**: A quiet month: zero transactions, opening = closing → *Accepted as a valid statement with 0 rows (nothing to sync, so it's already 'synced')* | ✅ |
| 6 | **S06-credit-card**: A credit card statement (balance = what you owe) → *Purchases count as money out, the card payment is 'Not an expense', refunds are negative* | ✅ |
| 7 | **S07-euro**: A statement in euros → *Currency stored as EUR* | ✅ |
| 8 | **S08-special-characters**: Descriptions with accents, quotes and symbols → *Saved exactly as printed* | ✅ |
| 9 | **S09-big-amounts**: Amounts over a million → *Stored to the cent* | ✅ |
| 10 | **S10-zero-amount**: A 0.00 line (a waived fee) → *Kept as a 0.00 row; math still checks out* | ✅ |
| 11 | **S11-two-months**: A statement covering Oct 15 – Nov 14 → *Rows land in both month tabs* | ✅ |
| 12 | **S12-identical-twins**: Two identical coffees on the same day → *Both are kept (both happened)* | ✅ |
| 13 | **S13-locked-right-password**: Password-protected PDF, correct password typed → *Opens and reads* | ✅ |
| 14 | **S14-locked-no-password**: Password-protected PDF, no password given → *Fails safely and asks for the password* | ✅ |
| 15 | **S15-locked-wrong-password**: Password-protected PDF, wrong password typed → *Fails safely and asks for the password* | ✅ |
| 16 | **S16-locked-saved-password**: Password-protected PDF, password saved earlier in the Keychain → *Opens automatically without asking* | ✅ |
| 17 | **S17-no-opening-balance**: No opening balance printed (running balances are) → *Opening worked out from row 1; verified* | ✅ |
| 18 | **S18-only-opening-and-closing**: Only opening and closing balances printed → *Verified by the closing balance alone* | ✅ |
| 19 | **S19-no-balances**: No balances printed at all → *Can't be verified: every row held for you* | ✅ |
| 20 | **S20-misread-amount**: AI misreads one amount (18.40 → 18.04) → *Caught: points at row 3, holds every row* | ✅ |
| 21 | **S21-misread-money-direction**: AI reads money out as money in → *Caught: the balance moves the wrong way* | ✅ |
| 22 | **S22-skipped-row**: AI skips a row → *Caught: the next balance jumps* | ✅ |
| 23 | **S23-duplicated-row**: AI reads a row twice → *Caught: the copy breaks the balance* | ✅ |
| 24 | **S24-misread-closing**: AI misreads the closing balance → *Caught at the closing line* | ✅ |
| 25 | **S25-misread-date**: AI misreads a year (2026 → 2027) → *Caught: date is outside the statement period* | ✅ |
| 26 | **S26-impossible-date**: AI returns an impossible date (30 February) → *Caught: not a valid date* | ✅ |
| 27 | **S27-not-a-statement**: A restaurant menu PDF uploaded by mistake → *Politely rejected* | ✅ |
| 28 | **S28-blank-pdf**: A blank PDF page → *Politely rejected* | ✅ |
| 29 | **S29-broken-file**: A corrupted / half-downloaded PDF → *Rejected as unreadable* | ✅ |
| 30 | **S30-page-too-dense**: One page holds more rows than the AI can return → *Fails with a clear message instead of guessing* | ✅ |
| 31 | **S31-ai-declines**: The AI declines the request → *Fails safely, can retry* | ✅ |
| 32 | **S32-ai-busy**: Claude is busy (rate limit) → *Fails safely: 'try again in a minute'* | ✅ |
| 33 | **S33-offline**: No internet connection → *Fails safely: 'check your connection'* | ✅ |
| 34 | **S34-ai-server-error**: Claude has a server error (500) → *Fails safely with the error code* | ✅ |
| 35 | Same file uploaded twice adds nothing | ✅ |
| 36 | Renamed copy is recognized as the same file | ✅ |
| 37 | Overlapping statements share rows without duplicates | ✅ |
| 38 | Two accounts with the same shop are kept apart | ✅ |
| 39 | Bank statement pays the card bill; card statement holds the purchases. Spending counts them once. | ✅ |
| 40 | Failed statement can be retried after fixing the cause | ✅ |

</details>

<details><summary><b>🧮 Building blocks: math check, fingerprints, settings, PDFs</b>: 30/30 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Balanced statement passes | ✅ |
| 2 | Wrong row is pinpointed and later rows are not flagged | ✅ |
| 3 | Credit card balance goes up with spending | ✅ |
| 4 | Opening balance is worked out from first row | ✅ |
| 5 | No balances at all cannot be verified | ✅ |
| 6 | Closing balance mismatch is reported | ✅ |
| 7 | Demo statement reconciles | ✅ |
| 8 | Identical coffees get different ids | ✅ |
| 9 | Same rows always get same ids | ✅ |
| 10 | Spacing and punctuation do not change ids | ✅ |
| 11 | Different accounts get different ids | ✅ |
| 12 | Merchant key ignores reference codes | ✅ |
| 13 | Keywords match whole words only | ✅ |
| 14 | First matching category wins | ✅ |
| 15 | Missing config gives a helpful error | ✅ |
| 16 | Config paths are relative to the config file and empty sheets dropped | ✅ |
| 17 | Bad setting is explained | ✅ |
| 18 | Locked pdf opens only with the right password | ✅ |
| 19 | Saved password is tried automatically | ✅ |
| 20 | Not a pdf is rejected | ✅ |
| 21 | Pages are split into groups | ✅ |
| 22 | Merge takes header from first and closing from last | ✅ |
| 23 | Cut off answer raises chunk too long | ✅ |
| 24 | Refusal raises ai declined | ✅ |
| 25 | Long page groups are split in half and retried | ✅ |
| 26 | Missing api key gives a clear message | ✅ |
| 27 | The ai instructions are read from the prompts folder | ✅ |
| 28 | Every category is explained in the sorting instructions | ✅ |
| 29 | A prompt file with broken markers is explained | ✅ |
| 30 | A missing prompt file says how to restore it | ✅ |

</details>

<details><summary><b>🔁 End-to-end: PDF → database → Google Sheets</b>: 23/23 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Statement is read checked and categorized | ✅ |
| 2 | Second statement uses learned rules | ✅ |
| 3 | Same file twice is ignored | ✅ |
| 4 | Overlapping statements create no duplicates | ✅ |
| 5 | Misread amount holds the whole statement | ✅ |
| 6 | User can approve a mismatched statement | ✅ |
| 7 | Locked pdf fails then succeeds with password | ✅ |
| 8 | Random pdf is politely rejected | ✅ |
| 9 | Review with remember creates user rule that ai cannot overwrite | ✅ |
| 10 | Sync fills category month tabs | ✅ |
| 11 | Second sync changes nothing | ✅ |
| 12 | Recategorized row moves between sheets | ✅ |
| 13 | Statement spanning two months fills both tabs | ✅ |
| 14 | Rows waiting for review are not synced | ✅ |
| 15 | Forgetting a statement removes its rows from sheets | ✅ |
| 16 | Sync without sheets configured explains what to do | ✅ |
| 17 | Sync failure is recorded and safe to retry | ✅ |
| 18 | Alerts across three months | ✅ |
| 19 | Recurring needs a steady monthly amount | ✅ |
| 20 | Monthly overview and summary | ✅ |
| 21 | Ai calls are logged | ✅ |
| 22 | Backup keeps the newest copies | ✅ |
| 23 | Inbox processing moves files | ✅ |

</details>

<details><summary><b>🗂️ Categorization: rules, keywords, AI, review</b>: 14/14 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Keyword rows never reach the ai | ✅ |
| 2 | Known shops are free the second month | ✅ |
| 3 | Only confident ai answers become rules | ✅ |
| 4 | Your correction wins over the ai next month | ✅ |
| 5 | Ai rule never overwrites your rule | ✅ |
| 6 | Review threshold is configurable (`default-low-and-medium`) | ✅ |
| 7 | Review threshold is configurable (`only-low`) | ✅ |
| 8 | Review threshold is configurable (`never`) | ✅ |
| 9 | Review threshold is configurable (`everything-the-ai-decides`) | ✅ |
| 10 | Row the ai skipped goes to review as other | ✅ |
| 11 | Unknown shops are sent in batches of 100 | ✅ |
| 12 | Categorization failure is safe to retry | ✅ |
| 13 | Ai request contains rows rules and your corrections | ✅ |
| 14 | Cut off categorization answer raises | ✅ |

</details>

<details><summary><b>📊 Google Sheets writer and database upgrades</b>: 18/18 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | First sync builds month tabs and summary | ✅ |
| 2 | Summary counts match the tabs | ✅ |
| 3 | Salary and transfers never reach any sheet | ✅ |
| 4 | Other sheet is written only when enabled | ✅ |
| 5 | Missing summary tab is created first | ✅ |
| 6 | Nothing changed means no writes at all | ✅ |
| 7 | Recategorized row moves to the other sheet | ✅ |
| 8 | Fixed date moves row to another month and cleans the old tab | ✅ |
| 9 | Tab left empty is deleted | ✅ |
| 10 | Older statement later keeps newest month first | ✅ |
| 11 | Huge month grows the tab instead of overflowing | ✅ |
| 12 | Unshared spreadsheet stops sync and names the robot | ✅ |
| 13 | Missing robot key file is explained | ✅ |
| 14 | Rebuild all rewrites every tab | ✅ |
| 15 | Forgetting a statement removes its rows from the sheets | ✅ |
| 16 | Check access reports each spreadsheet | ✅ |
| 17 | Old database is upgraded with a backup first | ✅ |
| 18 | New database starts at the latest version | ✅ |

</details>

<details><summary><b>🚨 Alerts: every rule on both sides of its threshold</b>: 28/28 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Double charge within 2 days (`same-day`) | ✅ |
| 2 | Double charge within 2 days (`2-days-later`) | ✅ |
| 3 | Double charge within 2 days (`3-days-later`) | ✅ |
| 4 | Double charge needs the same amount | ✅ |
| 5 | One alert per double charge pair | ✅ |
| 6 | Big charge is more than 3x the usual (`over-3x`) | ✅ |
| 7 | Big charge is more than 3x the usual (`exactly-3x`) | ✅ |
| 8 | Big charge needs 3 earlier charges | ✅ |
| 9 | Big first charge from a new shop (`at-threshold`) | ✅ |
| 10 | Big first charge from a new shop (`just-below`) | ✅ |
| 11 | Moving money to savings is not a new merchant alert | ✅ |
| 12 | Free trial turned paid (`7-days`) | ✅ |
| 13 | Free trial turned paid (`6-days-too-soon`) | ✅ |
| 14 | Free trial turned paid (`30-days`) | ✅ |
| 15 | Free trial turned paid (`32-days-too-late`) | ✅ |
| 16 | Free trial turned paid (`not-a-trial-amount`) | ✅ |
| 17 | Subscription price increase (`23%-rise`) | ✅ |
| 18 | Subscription price increase (`under-2%`) | ✅ |
| 19 | Forgotten subscription is spotted | ✅ |
| 20 | No forgotten subscription false alarms (`rent`) | ✅ |
| 21 | No forgotten subscription false alarms (`varying-fuel`) | ✅ |
| 22 | No forgotten subscription false alarms (`known-subscription`) | ✅ |
| 23 | No forgotten subscription false alarms (`savings`) | ✅ |
| 24 | No forgotten subscription false alarms (`only-2-months`) | ✅ |
| 25 | Category spike (`3-months`) | ✅ |
| 26 | Category spike (`2-months`) | ✅ |
| 27 | Alerts are never stored twice | ✅ |
| 28 | Dismissed alerts disappear | ✅ |

</details>

<details><summary><b>⌨️ Command line</b>: 19/19 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Help lists every command | ✅ |
| 2 | Process reads checks and sorts | ✅ |
| 3 | Dry run saves nothing | ✅ |
| 4 | Missing file is rejected before anything runs | ✅ |
| 5 | Locked pdf asks for the password | ✅ |
| 6 | Information commands after processing | ✅ |
| 7 | Commands on an empty database explain what to do | ✅ |
| 8 | Sync without google set up fails with instructions | ✅ |
| 9 | Sync and rebuild with google | ✅ |
| 10 | Approve only applies to mismatched statements | ✅ |
| 11 | Approve a mismatched statement | ✅ |
| 12 | Forget deletes the statement rows and pdf | ✅ |
| 13 | Forget asks before deleting | ✅ |
| 14 | Rules can be removed | ✅ |
| 15 | Inbox processes every waiting pdf | ✅ |
| 16 | Summary send without telegram set up | ✅ |
| 17 | Check offline lists what is missing | ✅ |
| 18 | Missing settings file is explained | ✅ |
| 19 | Password add list remove | ✅ |

</details>

<details><summary><b>⚙️ Settings, monthly summary, Telegram, automation, setup checklist</b>: 24/24 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Mistakes in settings are explained (`broken-yaml`) | ✅ |
| 2 | Mistakes in settings are explained (`word-instead-of-number`) | ✅ |
| 3 | Mistakes in settings are explained (`zero-pages`) | ✅ |
| 4 | Mistakes in settings are explained (`unknown-category`) | ✅ |
| 5 | Mistakes in settings are explained (`unknown-confidence`) | ✅ |
| 6 | Empty settings file uses safe defaults | ✅ |
| 7 | Paths are relative to the settings file | ✅ |
| 8 | Settings file can be chosen with an environment variable | ✅ |
| 9 | Example settings file is valid | ✅ |
| 10 | Env file next to settings is loaded | ✅ |
| 11 | Summary compares with last month | ✅ |
| 12 | Summary of a first month has no comparison | ✅ |
| 13 | Summary without income skips the savings rate | ✅ |
| 14 | Summary for an unknown month | ✅ |
| 15 | Telegram message is sent | ✅ |
| 16 | Telegram network failure is explained | ✅ |
| 17 | Inbox sorts files into done and failed | ✅ |
| 18 | Auto sync runs after processing | ✅ |
| 19 | Auto sync failure is reported not crashed | ✅ |
| 20 | Watcher only picks up new pdfs | ✅ |
| 21 | A PDF that is still being copied keeps growing; processing must wait until it's complete. | ✅ |
| 22 | Checklist when nothing is set up | ✅ |
| 23 | Checklist when everything is set up | ✅ |
| 24 | Checklist reports a broken settings file | ✅ |

</details>

<details><summary><b>🖥️ Web app pages</b>: 14/14 passed</summary>

| # | What is checked | Result |
|---|---|---|
| 1 | Page renders (`app.py`) | ✅ |
| 2 | Page renders (`pages/1_Review.py`) | ✅ |
| 3 | Page renders (`pages/2_Dashboard.py`) | ✅ |
| 4 | Page renders (`pages/3_Transactions.py`) | ✅ |
| 5 | Page renders (`pages/4_Statements.py`) | ✅ |
| 6 | Page renders (`pages/5_Setup.py`) | ✅ |
| 7 | Pages render with an empty database | ✅ |
| 8 | Missing config shows instructions | ✅ |
| 9 | Review page approve all empties the queue | ✅ |
| 10 | Dashboard shows alerts and can dismiss | ✅ |
| 11 | Statements page shows the problem and approves | ✅ |
| 12 | Sidebar warns about statements that dont add up | ✅ |
| 13 | Setup page backup button | ✅ |
| 14 | Transactions page filters | ✅ |

</details>

<!-- TEST-RESULTS:END -->

---

## 14. For developers: adding a test

- **A new real-life situation:** add a `Scenario(...)` to `SCENARIOS` in [`tests/scenarios.py`](tests/scenarios.py): an id, a plain-English title and expectation, how to build the PDF, how the AI should behave, and the expected status, message or issue. It automatically becomes a test, a fixture file (if tagged `"fixture"`) and a live test.
- **Anything else:** add a `test_…` function to the matching file. Name it as a sentence (`test_your_correction_wins_over_the_ai_next_month`); the report turns the name into its description.
- **Before committing:** `ruff format . && ruff check . && python -m pytest --report TESTING.md`
