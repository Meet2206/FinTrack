# 🗺️ Project Plan: "Where Did My Money Go?"

[Readme](Readme.md) · **Plan** · [Architecture](Architecture.md) · [Backend](Backend.md) · [DB](DB.md) · [Testing](TESTING.md) · [Reason](Reason.md)

| | |
|---|---|
| **What this document is** | The full plan: what we're building, why, what's in and out of scope, and the order we'll build it in. |
| **Who it's for** | Everyone, no coding knowledge needed. The technical details are in [Architecture](Architecture.md), [Backend](Backend.md) and [DB](DB.md). |
| **Status** | ✅ Built: version 1.0 covers Phases 1–6. Phase 0 is your one-time setup ([Backend → Setup](Backend.md#4-setup-step-by-step)); Phase 7 holds future ideas. |

> 💡 **Words you might not know** are explained in the [Glossary](#14-glossary) at the bottom.

---

## 1. The one-minute version

You upload your **bank statement** (the PDF your bank emails you every month).

The app:
1. **reads every transaction** in it,
2. **double-checks the math** against the bank's own balances, so no number is ever wrong,
3. **decides what each payment was for**: Grocery, Travel, Subscriptions, Investments or Savings,
4. **copies the results into 5 Google Sheets**, one per category, with **a separate tab for each month**.

Next month you upload the next statement, and each sheet gets a new month tab. Over time you get a full history of where your money went, without typing a single number.

### Before vs. after

| Today (by hand) | With the app |
|---|---|
| Open the PDF and squint at 150 rows | Drop the PDF into the app |
| Type each row into Excel | The AI reads every row for you |
| Guess what `POS 4471 FRSHMRT*CTY` was | The AI recognizes it ("Fresh Mart") and files it under Grocery |
| Add up totals and hope there's no typo | Totals are checked against the bank's own balance, to the cent |
| About 2 hours a month | About 2 minutes, plus a quick look at anything the AI wasn't sure about |

---

## 2. Why build this?

**The problem:**
- A bank statement tells you **what** happened, not **what it means**. "You spent 2,340 this month" doesn't say *on what*.
- Budgeting apps usually want your **bank login** (a privacy risk) or don't support your bank.
- Tracking it by hand in a spreadsheet is so tedious that most people give up by month 2.

**What we get:**
- A clear, automatic monthly answer to "where did my money go?"
- A growing history, so you can compare months and spot trends ("Travel doubled since March").
- Alerts for things you'd otherwise miss: double charges, sneaky subscription price increases, free trials that quietly became paid.

**What the builder learns** (this is also a learning project):
- Having AI read documents and return **structured data** (filling in a form instead of writing free text)
- **Checking AI output** instead of trusting it blindly
- Databases, Google APIs, dashboards, and automation

---

## 3. Goals and non-goals

### ✅ Goals (version 1)

| # | Goal | Why it matters |
|---|---|---|
| G1 | Read **any** bank or credit card statement PDF, including password-protected and scanned ones | Every bank formats statements differently |
| G2 | Every amount is **100% correct**, verified against the statement's balances | A finance tool with wrong numbers is worse than no tool |
| G3 | Sort spending into **5 categories** (plus "Other" and "Not an expense") | This is what you actually want to know |
| G4 | Write to **5 Google Sheets** with **one tab per month** and automatic monthly totals | Easy to view, share and chart anywhere |
| G5 | **Never** create duplicate rows, even if the same statement is uploaded twice | Duplicates silently inflate your totals |
| G6 | **Learn from your corrections** | Fix a category once and it stays fixed |
| G7 | Cost under **$1 a month** to run | It has to be cheaper than the problem it solves |

### 🚫 Non-goals (deliberately *not* in version 1)

| Not doing | Why not |
|---|---|
| Logging into your bank automatically | Big security risk, and every bank works differently. Uploading the PDF is safer. |
| Replacing a full budgeting app | We focus on "where did it go?", not envelopes and goals (maybe later) |
| Multiple users or shared family accounts | Keeps it simple and private |
| Tracking investment *performance* | We record money moved *into* investments, not what it's worth today |
| A mobile app | It runs in the browser on your laptop |
| Editing the Google Sheets by hand | The sheets are a *mirror* of the app's records (see [section 7](#7-google-sheets-what-youll-see)) |
| Tax advice | Not a tax tool |

---

## 4. Who uses it (user stories)

> A *user story* describes a feature from the user's point of view: "As a ___, I want ___, so that ___."

| # | As a… | I want to… | So that… |
|---|---|---|---|
| U1 | person who wants clarity | upload my statement and see each category's total for the month | I know where my money went |
| U2 | careful person | see which rows the AI wasn't sure about and fix them in one click | nothing is filed wrong |
| U3 | forgetful person | be warned about double charges and subscription price increases | I catch them before they cost me |
| U4 | busy person | have next month's statement processed automatically when it arrives *(later phase)* | I don't have to remember |
| U5 | privacy-minded person | keep my data on my own laptop, sending only what the AI needs to read | my finances stay mine |
| U6 | curious person | compare months and see trends | I can change my habits |

---

## 5. What it does (features)

| Feature | In plain English | Phase |
|---|---|---|
| **Upload a statement** | Drag a PDF into the app. Locked PDFs ask for the password once and remember it securely. | 1 |
| **Read transactions** | The AI reads every row: date, description, money in, money out, balance. | 1 |
| **Check the math** | Starting balance + money in − money out must equal the closing balance, row by row. | 1 |
| **No duplicates** | Each file and each transaction gets a "fingerprint", so nothing is counted twice. | 2 |
| **Categorize** | Known shops are sorted instantly by saved rules; new ones are sorted by the AI. | 3 |
| **Review queue** | Rows the AI wasn't sure about wait for your OK. | 3 + 5 |
| **Learns from you** | Your fixes become rules for next time. | 3 |
| **Google Sheets sync** | 5 spreadsheets, a tab per month, plus a Summary tab with totals. | 4 |
| **Dashboard** | Charts: spending per month, per category, top shops, subscriptions. | 5 |
| **Alerts** | Double charges, unusually large charges, new subscriptions, price increases. | 6 |
| **Automation** | Drop a PDF in a folder (or have it pulled from email) and it's processed on its own. | 6 |
| **Monthly summary** | A short message every month: "You spent X. Travel is up 40%." | 6 |

---

## 6. The categories (the rules, in plain English)

### The 5 main categories (each gets its own Google Sheet)

| Category | What goes in | Examples | What does **not** go in |
|---|---|---|---|
| 🛒 **Grocery** | Food and household supplies you take home | Supermarkets, grocery delivery apps, markets, household supplies | Restaurants and cooked-food delivery → **Other** |
| ✈️ **Travel** | Getting around, and trips | Cabs and ride-hailing, fuel, parking, tolls, trains, metro, flights, hotels | Car loan payments → **Other** |
| 🔁 **Subscriptions** | Recurring charges for a service | Streaming, music, cloud storage, software, gym, phone and internet plans | One-off app purchases → **Other** |
| 📈 **Investments** | Money put into assets | Brokerage transfers, mutual funds/SIPs, ETFs, stocks, crypto, retirement contributions | Insurance premiums → **Other** |
| 🏦 **Savings** | Money set aside that stays as cash | Transfers to your own savings account, fixed or recurring deposits, emergency fund | Money sent to other people → **Other** |

### The 2 helper categories (no sheet by default)

| Category | What goes in | Why it exists |
|---|---|---|
| **Other** | Real spending outside the 5: rent, restaurants, food delivery, shopping, bills, insurance, loan payments, healthcare, cash withdrawals | So nothing silently disappears. You can turn on a 6th "Other" sheet with one line in the settings file. |
| **Not an expense** | Money coming **in** (salary, interest) and money moving between **your own** accounts, including **credit card bill payments** | So these aren't counted as spending |

### Default choices for the grey areas (all changeable in the settings file)

| Situation | Goes to | Why |
|---|---|---|
| Restaurants, cafés, food delivery | Other | It's eating out, not groceries |
| Grocery delivery apps | Grocery | It's groceries, just delivered |
| Fuel, parking, tolls | Travel | It's the cost of getting around |
| Phone and internet plans, gym | Subscriptions | They charge you every month |
| Insurance, loan payments | Other | Not one of the five |
| Cash withdrawal (ATM) | Other | We can't see what the cash was spent on |
| **Refund** from a shop | Same category, **negative amount** | So the month's total nets out correctly |
| Money coming **back** from savings or investments | Savings / Investments, **negative amount** | So the total shows what you *really* set aside |
| **Credit card bill** paid from your bank account | Not an expense | ⚠️ Otherwise every card purchase would be counted twice: once on the card statement and again as the bill payment |
| Mixed-purchase shops (e.g. a big online store) | Other, unless you set a rule | We can't see what was in the basket |

### Spending vs. setting money aside

Investments and Savings aren't really "expenses". The money is still yours, just moved somewhere else. So the dashboard shows them separately:

- **Spending** = Grocery + Travel + Subscriptions + Other
- **Set aside** = Investments + Savings
- **Savings rate** = Set aside ÷ Money in (a great number to watch every month)

---

## 7. Google Sheets: what you'll see

### Layout

```
📗 Expenses – Grocery          ← one spreadsheet per category (×5)
   ├── Summary                 ← totals for every month, updated automatically
   ├── 2026-11                 ← one tab per month, newest first
   ├── 2026-10
   └── 2026-09 …

📗 Expenses – Travel
📗 Expenses – Subscriptions
📗 Expenses – Investments
📗 Expenses – Savings
📗 Expenses – Other            ← optional 6th sheet (off by default)
```

### A month tab (e.g. `2026-11` in "Expenses – Grocery")

| Date | Merchant | Description (as printed) | Amount | Currency | Account | Txn ID |
|---|---|---|---|---|---|---|
| 2026-11-02 | Fresh Mart | POS 4471 FRSHMRT*CTY | 54.20 | USD | Bank ••1234 | 9f2c41d0a7b3e815 |
| 2026-11-09 | Green Grocer Co | CARD 1234 GREEN GROCER CO | 23.75 | USD | Bank ••1234 | 1b77e0c94d2a6f03 |
| 2026-11-15 | Fresh Mart | REFUND FRSHMRT*CTY | −8.99 | USD | Bank ••1234 | c0e5a8f1937b2d46 |

- **Amount:** positive = money out, negative = refund or money coming back.
- **Account:** only the last 4 digits, never the full account number.
- **Txn ID:** the transaction's unique fingerprint. You can ignore it; the app uses it to prevent duplicates.

### The Summary tab

| Month | Total | Transactions |
|---|---|---|
| 2026-11 | 412.30 | 18 |
| 2026-10 | 389.95 | 21 |
| 2026-09 | 401.10 | 19 |

The totals are **spreadsheet formulas**, so they always match the month tabs.

### Rules for months
- A row goes into a month by its **transaction date**, not the statement date. A statement covering **Oct 15 – Nov 14** fills **both** the `2026-10` and `2026-11` tabs.
- New month tabs are **created automatically**.
- If you upload an **older** statement later, its rows land in the correct older tab and the Summary updates.
- Tabs are named `YYYY-MM` (e.g. `2026-11`) so they sort correctly and can't be misread.

### ⚠️ The sheets are a mirror: don't edit them by hand
The app keeps the master copy of your records (the *ledger*) on your laptop, and the Google Sheets are a **copy** of it. If you change something by hand in a sheet, the next sync overwrites it. To fix something, fix it **in the app** and it flows to the sheets.

*Why?* With a single master copy there's no "which version is right?" confusion, and the sheets can always be rebuilt perfectly. Details in [Architecture → D3](Architecture.md#d3-the-ledger-is-the-master-google-sheets-is-a-mirror).

---

## 8. Screens (what the app looks like)

The app runs in your web browser, on your own laptop.

### Upload

```
┌──────────────────────────────────────────────────────────────────────┐
│  💸 Where Did My Money Go?    [Upload] Review (7)  Dashboard  Statements │
├──────────────────────────────────────────────────────────────────────┤
│   ┌──────────────────────────────────────────────────────────┐        │
│   │        📄  Drag your statement PDF here                   │        │
│   │            or click to browse                             │        │
│   └──────────────────────────────────────────────────────────┘        │
│   Password (only if the PDF is locked): [••••••••]   ☑ Remember it    │
│                                                       [ Process ▶ ]   │
│                                                                        │
│   ✅ Opened the PDF (6 pages)                                          │
│   ✅ Read 142 transactions                                             │
│   ✅ Balances match the statement to the cent                          │
│   ✅ Sorted 135 automatically, 7 need your review                      │
│                                          [ Review 7 rows → ]           │
└──────────────────────────────────────────────────────────────────────┘
```

### Review queue

```
┌──────────────────────────────────────────────────────────────────────┐
│  Review: 7 rows need a quick look                                     │
├────────────┬──────────────────────────┬────────┬───────────────┬──────┤
│ Date       │ Description              │ Amount │ Category ▼    │ Why  │
├────────────┼──────────────────────────┼────────┼───────────────┼──────┤
│ 2026-11-03 │ TRF TO A/C ••5678        │ 500.00 │ [Savings    ▼]│ Not sure │
│ 2026-11-08 │ PAYPAL *JD STORE 22      │  39.99 │ [Other      ▼]│ Not sure │
│ 2026-11-21 │ MERCHANT 8812 LLC        │ 249.00 │ [Other      ▼]│ Big, new shop │
├────────────┴──────────────────────────┴────────┴───────────────┴──────┤
│  ☑ Remember my choices for these shops          [ Approve all ✓ ]     │
└──────────────────────────────────────────────────────────────────────┘
```

### Dashboard

```
┌──────────────────────────────────────────────────────────────────────┐
│  November 2026                                                        │
│  Spent 2,340 (▲ 8% vs Oct)   Set aside 900   Savings rate 24%   ⚠ 2 alerts │
│                                                                        │
│  Spending by month (stacked by category)      Top shops this month    │
│  ▇▇▇▆▆  ▇▇▇▇▆  ▇▇▇▇▇▆                         1. Fresh Mart   210     │
│   Sep     Oct     Nov                         2. City Cabs     180     │
│                                                3. StreamFlix     15    │
│  ⚠ "City Cabs" charged 64.00 twice on Nov 12 — double charge?         │
│  ⚠ "StreamFlix" went from 12.99 to 15.99                              │
└──────────────────────────────────────────────────────────────────────┘
```

### Statements

```
┌──────────────────────────────────────────────────────────────────────┐
│  File                      Period                  Status              │
│  bank_nov_2026.pdf         Oct 15 – Nov 14         🟢 In Google Sheets │
│  card_nov_2026.pdf         Nov 01 – Nov 30         🟡 7 rows to review │
│  bank_oct_2026.pdf         Sep 15 – Oct 14         🔴 Numbers don't match – check row 37 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 9. How we'll build it: phases

We build in small steps, and each phase ends with something that **works and can be shown**.

> ⏱️ Times are in *focused working days* for one intermediate developer. Working evenings, the whole project takes roughly **3–5 weeks**.

```
Phase 0  Setup              ▓░░░░░░░░░░░░░░░░░   ½ day
Phase 1  Read statements    ░▓▓▓░░░░░░░░░░░░░░   2–3 days
Phase 2  Ledger (memory)    ░░░░▓▓░░░░░░░░░░░░   1–2 days
Phase 3  Categorize         ░░░░░░▓▓▓░░░░░░░░░   2–3 days
Phase 4  Google Sheets      ░░░░░░░░░▓▓░░░░░░░   1–2 days
Phase 5  App screens        ░░░░░░░░░░░▓▓▓░░░░   2–3 days
Phase 6  Automation+alerts  ░░░░░░░░░░░░░░▓▓▓▓   3–4 days
```

### Phase 0: Setup (½ day)
**Goal:** all the accounts and tools are ready before any real code.
- [ ] Install Python 3.12+ and create the project folder with git
- [ ] Add `.gitignore` **first**, so private files (statements, keys, database) can never be committed
- [ ] Get a Claude API key
- [ ] Create a Google "service account" (a robot Google user the app logs in as) and download its key file
- [ ] Create the 5 Google Sheets, each with an empty `Summary` tab, and share each one with the robot's email address
- [ ] Fill in `config.yaml` (the settings file)
- [ ] Collect 2–3 real statements from your bank for testing

**Done when:** `python scripts/check_setup.py` shows all green ticks.
Step-by-step instructions: [Backend → Setup](Backend.md#4-setup-step-by-step).

### Phase 1: Read statements (2–3 days)
**Goal:** PDF in, a correct list of transactions out.
- [x] Unlock password-protected PDFs
- [x] Split long PDFs into small page groups
- [x] Ask Claude to read each group and fill in a fixed "form" (date, description, money in/out, balance)
- [x] Join the groups back together
- [x] **Check the math** (reconciliation), pinpointing any wrong row
- [x] Command: `python cli.py process statement.pdf --dry-run` prints the transactions as a table

**Done when:** 3 real statements match their balances to the cent, a locked PDF opens with its password, and a random non-statement PDF is politely rejected.

### Phase 2: Ledger, the app's memory (1–2 days)
**Goal:** save everything permanently, with no duplicates.
- [x] Create the database (one file on your laptop: `data/ledger.db`)
- [x] Fingerprint each PDF so the same file is never processed twice
- [x] Fingerprint each transaction so overlapping statements don't create duplicates
- [x] Track each statement's status (processing / needs a look / ready / in Sheets)
- [x] Record what each AI call cost

**Done when:** uploading the same statement twice adds **0** new rows, two overlapping statements produce no duplicates, and `python cli.py status` lists your statements.

### Phase 3: Categorize (2–3 days)
**Goal:** every transaction gets the right category.
- [x] Keyword rules from the settings file (e.g. "netflix" → Subscriptions)
- [x] Learned rules: once a shop is categorized confidently, remember it
- [x] Claude for unknown shops, about 100 rows per request
- [x] Mark rows the AI wasn't sure about for review
- [x] **Hand-label 150 real transactions** and measure how often the app agrees with you

**Done when:** the app agrees with your labels at least **95%** of the time, and from the second month on, at least **70%** of rows are sorted by saved rules (free and instant).

### Phase 4: Google Sheets (1–2 days)
**Goal:** the 5 sheets fill themselves.
- [x] Create month tabs automatically
- [x] Write each month's rows in one go (fast, and gentle on Google's limits)
- [x] Keep the Summary tab up to date
- [x] Keep tabs in order: Summary first, then newest month
- [x] If you change a category in the app, the row moves to the right sheet on the next sync

**Done when:** all 5 sheets show the right monthly tabs, the Summary totals match the app exactly, and a re-categorized row moves sheets after a sync.

### Phase 5: App screens (2–3 days)
**Goal:** no terminal needed.
- [x] Upload screen with password prompt and live progress
- [x] Review queue with drop-down categories and "remember my choice"
- [x] Dashboard with charts and alerts
- [x] Statements list with status
- [x] Settings check (are the keys and sheets working?)

**Done when:** a non-technical friend can process a statement and sync it to Google Sheets **without any help from you**.

### Phase 6: Automation and alerts (3–4 days)
**Goal:** it runs itself and taps you on the shoulder when something's odd.
- [x] Alerts: double charges, unusually large charges, big charges at new shops, new subscriptions, price increases, free trials turning paid, category spikes
- [x] Watch a folder: drop a PDF in and it's processed automatically
- [ ] *(Optional)* fetch statement PDFs from Gmail automatically
- [x] Monthly summary message (Telegram or email)
- [x] Automatic database backups

**Done when:** a new statement in the folder reaches Google Sheets **with no clicks**, and a monthly summary arrives on your phone.

### Phase 7: Nice-to-haves (optional, any order)
- **Privacy mode:** read the PDF on your laptop and remove account numbers before anything is sent to the AI
- **Fast path for your main bank:** a free, non-AI reader, with the AI as backup
- **Budgets per category**, with a warning at 80%
- **Ask questions in plain English:** "How much did I spend on travel in Q3?"
- **Several currencies**
- **Receipt matching:** link a photo of a receipt to its bank transaction

---

## 10. How we'll know it works

| What we measure | Target | How we measure it |
|---|---|---|
| Amount accuracy | **100%** of synced statements match their balances (or you approved them) | Built-in reconciliation |
| Category accuracy | **≥ 95%** | Compare against 150 transactions you labeled by hand |
| Review workload | **≤ 10%** of rows need review after month 2 | Count of flagged rows |
| Duplicates | **0** | Upload the same and overlapping statements on purpose |
| Speed | **≤ 3 minutes** from upload to Sheets for a 6-page statement (not counting your review) | Timed in the app |
| Running cost | **≤ $1 / month** for 2–3 statements | The app's own cost log |
| Ease of use | A non-technical friend succeeds without help | Watch them try it |

---

## 11. Risks and what we'll do about them

| Risk | Likelihood | Impact | What we do |
|---|---|---|---|
| The AI misreads a number | Medium | **High** | The math check catches it and points to the exact row. Nothing reaches the sheets until it's fixed. |
| The AI picks the wrong category | Medium | Medium | Review queue for unsure rows, learned rules, and accuracy measured against your labels |
| The bank changes its statement layout | Low | Low | The AI reads any layout, and the math check catches problems |
| Private data leaks | Low | **High** | Data stays on your laptop, secrets are never committed to git, passwords live in the macOS Keychain, the robot account can see only the 5 sheets, and the app is reachable only from your own computer |
| AI costs creep up | Low | Low | Saved rules make repeat shops free, and every AI call's cost is logged |
| Google API limits or errors | Low | Low | Writes are batched, and a failed sync can simply be run again |
| Locked or scanned PDFs | **High** (very common) | Low | Supported from Phase 1 |
| Losing the database | Low | **High** | Automatic backups. The sheets can be rebuilt from the database, and the database from the PDFs. |
| Scope creep ("let's also add…") | **High** | Medium | Non-goals list and phase plan. New ideas go to Phase 7. |

---

## 12. Decisions made (and why)

| # | Decision | Why |
|---|---|---|
| 1 | **5 separate spreadsheets with monthly tabs** | What you asked for: one place per category, easy to open and share individually |
| 2 | **The AI reads the PDF directly** (no per-bank code) | Works with any bank from day one, even scanned statements |
| 3 | **Nothing syncs unless the math checks out** | Correct numbers are non-negotiable |
| 4 | **The app's database is the master copy; sheets are a mirror** | No conflicting versions, and sheets can be rebuilt anytime |
| 5 | **Saved rules first, AI second** | Cheaper, faster, and consistent ("Fresh Mart" is always Grocery) |
| 6 | **You review rows the AI isn't sure about** | Human judgment where it matters, no busywork elsewhere |
| 7 | **Runs on your laptop** | Privacy and zero hosting cost |
| 8 | **Python + Streamlit** | Python suits AI and data work; Streamlit turns Python into a web app without front-end coding |

Technical reasoning for each: [Architecture → Design decisions](Architecture.md#7-design-decisions-and-why).

---

## 13. Open questions

| Question | Current default | Decide by |
|---|---|---|
| One currency or several? | One (set in the settings file) | Phase 1 |
| Which bank do we start with? | Whichever you have 2–3 statements for | Phase 0 |
| Turn on the 6th "Other" sheet? | Off. Other rows stay visible in the app. | Phase 4 |
| Keep statement PDFs after processing? | Keep them in `data/statements/` so they can be re-processed if needed | Phase 2 |
| Where should alerts and summaries go? | Telegram (easiest), or email | Phase 6 |

---

## 14. Glossary

| Word | Meaning |
|---|---|
| **AI / LLM** | "Large language model": software that reads and writes text (and here, documents) like a person would. We use **Claude**, made by Anthropic. |
| **API** | A way for one program to talk to another over the internet, like a waiter taking an order to the kitchen and bringing back the food. |
| **API key** | A secret password that lets our app use a service (Claude or Google). Never share it. |
| **Categorize** | Decide which bucket a transaction belongs in (Grocery, Travel…). |
| **CLI** | "Command-line interface": typing commands in the terminal instead of clicking buttons. |
| **Config file** (`config.yaml`) | A plain text settings file: which sheets to use, keyword rules, and so on. |
| **Confidence** | How sure the AI is about a category: high, medium or low. Medium and low go to review. |
| **Dashboard** | A screen of charts and key numbers. |
| **Fingerprint (hash)** | A short code calculated from a file or a row. Same content, same fingerprint. That's how we spot duplicates. |
| **Ledger** | The app's master record of every transaction, stored in a database file on your laptop. |
| **Merchant** | The shop or company you paid. |
| **Mirror** | A copy that's kept in sync with the original. Our Google Sheets mirror the ledger. |
| **Phase** | One step of the build plan. |
| **Reconciliation** | Checking that opening balance + money in − money out = closing balance, like counting the till at the end of the day. |
| **Review queue** | The list of rows waiting for your OK. |
| **Rule** | A saved decision, like "FRSHMRT means Fresh Mart, which is Grocery". |
| **Service account** | A robot Google account the app uses to write to your sheets. It can only see sheets you share with it. |
| **SQLite** | A simple database that lives in a single file. No server needed. |
| **Statement** | The monthly PDF from your bank or credit card company. |
| **Streamlit** | A Python tool that turns scripts into simple web apps. |
| **Structured output** | Making the AI fill in a strict form (date, amount…) instead of writing free text, so code can use the answer safely. |
| **Sync** | Copying the latest data from the ledger to Google Sheets. |
| **Token** | The unit AI usage is measured and billed in. Roughly ¾ of a word. |

---

## 15. Cost summary

| Item | Cost | Notes |
|---|---|---|
| Reading a statement (Claude Opus 5.5) | ~10–25¢ per 5-page statement | Priced at $4 per million tokens read and $20 per million written |
| Categorizing | A few cents per statement | Falls toward zero as saved rules build up |
| Google Sheets API | Free | Within normal personal use |
| Hosting | Free | Runs on your laptop |
| **Typical month (2–3 statements)** | **Well under $1** | The app logs the cost of every AI call so you can check |
