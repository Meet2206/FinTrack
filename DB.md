# 🗄️ Database (DB)

[README](README.md) · [Automation](AUTOMATION.md) · [Architecture](Architecture.md) · [Backend](Backend.md) · **DB** · [Testing](TESTING.md)

| | |
|---|---|
| **What this document is** | Everything about where the app keeps its records: each table, what every column means, how duplicates are prevented, how the Google Sheets stay in sync, backups and privacy. |
| **Who it's for** | Everyone. Each section starts with a 💡 plain-English summary, followed by the details. |
| **The actual files** | `finance/migrations/001_init.sql` + `002_synced_month.sql` (both in full in [§13](#13-the-full-schema)). Current version: 2. |

---

## 1. The big idea

> 💡 **In plain English:** the database is the app's **master notebook**. It's a single file on your laptop (`data/ledger.db`) that holds every statement you've uploaded, every transaction, every category, and every rule the app has learned.
>
> Your **Google Sheets are a copy** of this notebook, laid out the way you like to read it. If the sheets ever get messed up, they can be rebuilt perfectly from the notebook. The reverse isn't true, so the notebook is what we protect and back up.

```
            ┌───────────────────────────────┐
  PDFs ───▶ │   data/ledger.db  (MASTER)    │ ───sync──▶  5 Google Sheets (MIRROR)
            │   statements, transactions,   │
            │   rules, alerts, costs…       │ ───────▶  Dashboard in the app
            └───────────────────────────────┘
```

---

## 2. Why SQLite?

> 💡 SQLite is a database that lives in **one ordinary file**. There's no server to install or keep running. Python has it built in.

| Need | SQLite fits because… |
|---|---|
| One person, one laptop | No server, no passwords, no setup |
| Small data (a few MB per decade) | It easily handles gigabytes |
| Easy backups | Copying one file is a backup |
| Privacy | The file never leaves your laptop |
| Reliable | Used in every phone and browser. Writes are all-or-nothing, so a crash can't leave half a transaction. |

**When we'd switch to PostgreSQL:** only if several people need to use it at the same time from different devices. Since all SQL lives in `finance/ledger.py`, the switch would touch just that file.

---

## 3. Map of the tables

> 💡 Seven tables, like seven tabs in a notebook. The lines show which table points to which. For example, every transaction points to the statement it came from.

```
┌──────────────┐ 1      many ┌──────────────────┐ 1      many ┌────────────────────┐
│   accounts   │◀────────────│    statements    │◀────────────│    transactions    │
│──────────────│             │──────────────────│             │────────────────────│
│ id           │             │ id               │             │ id  (fingerprint)  │
│ kind         │             │ file_hash        │             │ statement_id  ─────┘
│ account_last4│◀──────┐     │ account_id ──────┘             │ account_id ───┐
│ bank_name    │       │     │ period_start/end │             │ txn_date, month│
│ currency     │       │     │ opening/closing  │             │ description    │
└──────────────┘       │     │ status           │             │ merchant       │
                       │     │ issues           │             │ amount         │
                       └─────┼──────────────────┼─────────────┤ category       │
                             └──────────────────┘             │ needs_review   │
                                      ▲                       │ synced_at      │
                                      │ (optional)            └───────▲────────┘
┌──────────────┐               ┌──────┴───────┐                       │
│   ai_calls   │───────────────┘              │               ┌───────┴────────┐
│──────────────│  which statement it was for  │               │     alerts     │
│ tokens, cost │                              │               │────────────────│
└──────────────┘                                              │ transaction_id │
                                                              │ kind, message  │
┌──────────────────┐        ┌──────────────┐                  └────────────────┘
│  merchant_rules  │        │  sync_runs   │
│──────────────────│        │──────────────│
│ merchant_key     │        │ when, which  │      (these two stand alone)
│ merchant         │        │ tabs, result │
│ category, source │        └──────────────┘
└──────────────────┘
```

| Table | 💡 In one sentence |
|---|---|
| `accounts` | Your bank accounts and credit cards (only the last 4 digits) |
| `statements` | Every PDF you've uploaded and where it's up to |
| `transactions` | Every row from every statement: the heart of the app |
| `merchant_rules` | What the app has learned: "this shop = this category" |
| `alerts` | Warnings like "double charge?" or "price went up" |
| `sync_runs` | A log of every Google Sheets update |
| `ai_calls` | A log of every Claude request and what it cost |

---

## 4. Conventions (rules used everywhere)

| Rule | Example | Why |
|---|---|---|
| **Amount: positive = money out, negative = money in** | Groceries `54.20`, salary `-3000.00`, refund `-8.99` | Summing a category gives what you actually spent, with refunds netted out |
| **Dates are text `YYYY-MM-DD`** | `2026-11-02` | Sorts correctly as text and can't be misread (no 03/04 confusion) |
| **Months are text `YYYY-MM`** | `2026-11` | Same as the Google Sheets tab names |
| **Timestamps are local time `YYYY-MM-DD HH:MM:SS`** | `2026-11-22 14:05:31` | Readable, and sorts correctly |
| **Yes/no is stored as `1`/`0`** | `needs_review = 1` | SQLite has no separate true/false type |
| **Lists are stored as JSON text** | `["Row 37: expected…"]` | Simple, and readable by any tool |
| **Only the last 4 digits of account numbers** | `1234` | The full number is never stored |
| **Money is rounded to 2 decimals when saved** | `54.2` → `54.20` | Avoids tiny floating-point leftovers like `54.19999` |

---

## 5. The tables, one by one

### 5.1 `accounts`: your bank accounts and cards

> 💡 One row per bank account or credit card. Created automatically the first time a statement from it is processed.

| Column | Type | Meaning | Example |
|---|---|---|---|
| `id` | number | Internal number | `1` |
| `kind` | text | `bank` or `card` | `bank` |
| `account_last4` | text | Last 4 digits only (`unknown` if not printed) | `1234` |
| `bank_name` | text | As printed on the statement | `Example Bank` |
| `currency` | text | Currency code | `USD` |
| `nickname` | text | Optional friendly name you can set | `Salary account` |
| `created_at` | text | When it was first seen | `2026-11-22 14:05:31` |

An account is identified by **type + last 4 digits**. Bank names aren't used, because the AI might read "EXAMPLE BANK N.A." one month and "Example Bank" the next.

### 5.2 `statements`: every PDF you've uploaded

> 💡 One row per uploaded file. Its **status** tells you where it's up to, like a parcel tracker.

| Column | Type | Meaning | Example |
|---|---|---|---|
| `id` | number | Internal number | `7` |
| `file_hash` | text | **Fingerprint** of the file (SHA-256). Same file → same fingerprint. **Unique**, so a file can't be added twice. | `9a3f…e21c` (64 characters) |
| `file_name` | text | Original file name | `bank_nov_2026.pdf` |
| `stored_path` | text | Where our copy is kept | `data/statements/9a3f…e21c.pdf` |
| `account_id` | number → `accounts` | Which account it belongs to | `1` |
| `period_start`, `period_end` | text | Statement period | `2026-10-15`, `2026-11-14` |
| `opening_balance`, `closing_balance` | number | As printed | `1000.00`, `3881.80` |
| `page_count` | number | Pages in the PDF | `6` |
| `status` | text | See [§6](#6-statuses-and-flags) | `ready` |
| `issues` | JSON text | Math problems found, if any | `["Row 3 (2026-11-05…): expected 3,899.80…"]` |
| `approved_by_user` | 0/1 | You accepted it despite a mismatch | `0` |
| `error` | text | Why it failed, in plain English | `This PDF is locked…` |
| `uploaded_at`, `processed_at` | text | Timestamps | |

### 5.3 `transactions`: the heart of the app

> 💡 One row per line on your statements. This is what ends up in Google Sheets.

| Column | Type | Meaning | Example |
|---|---|---|---|
| `id` | text | **Fingerprint** of the transaction (16 characters). See [§7](#7-how-duplicates-are-prevented). | `9f2c41d0a7b3e815` |
| `statement_id` | number → `statements` | The statement it was first found in | `7` |
| `account_id` | number → `accounts` | Which account | `1` |
| `row_number` | number | Position on the statement (keeps the original order) | `12` |
| `txn_date` | text | Transaction date | `2026-11-02` |
| `month` | text, *calculated* | First 7 characters of `txn_date`. Always correct, never stored separately. | `2026-11` |
| `description` | text | Exactly as printed | `POS 4471 FRSHMRT*CTY` |
| `merchant` | text | Clean shop name | `Fresh Mart` |
| `amount` | number | **+ money out, − money in** | `54.20` |
| `balance_after` | number | Bank's running balance after this row | `945.80` |
| `currency` | text | | `USD` |
| `category` | text | One of the 7 categories (empty until categorized) | `Grocery` |
| `confidence` | text | `high` / `medium` / `low` | `high` |
| `category_source` | text | Who decided: `user`, `rule`, `keyword` or `ai` | `rule` |
| `needs_review` | 0/1 | Waiting for your OK | `0` |
| `review_reason` | text | Why it's waiting | `AI wasn't sure` |
| `synced_category` | text | The category it had at the last sync (which sheet it's in) | `Grocery` |
| `synced_month` | text | The month tab it was last written to (added in upgrade 002) | `2026-11` |
| `synced_at` | text | When Sheets last matched this row. **Empty = Sheets needs updating.** | `2026-11-22 14:10:02` |
| `created_at`, `updated_at` | text | Timestamps | |

**Allowed categories** (enforced by the database itself):
`Grocery`, `Travel`, `Subscriptions`, `Investments`, `Savings`, `Other`, `Not an expense`.

### 5.4 `merchant_rules`: what the app has learned

> 💡 "When I see a description that simplifies to `frshmrt cty`, that's **Fresh Mart**, which is **Grocery**." Rules make repeat shops instant and free.

| Column | Type | Meaning | Example |
|---|---|---|---|
| `merchant_key` | text | Simplified description: letters only, first 3 words. **Unique.** | `pos frshmrt cty` |
| `merchant` | text | Clean name | `Fresh Mart` |
| `category` | text | The category to use | `Grocery` |
| `source` | text | `user` (you fixed it) or `ai` (a confident AI answer) | `user` |
| `times_used` | number | How often it has saved an AI call | `14` |
| `created_at`, `updated_at` | text | | |

**Your rules always win.** An `ai` rule never overwrites a `user` rule, while your fix always overwrites an `ai` rule.

### 5.5 `alerts`: things worth a second look

| Column | Type | Meaning | Example |
|---|---|---|---|
| `id` | number | | `3` |
| `transaction_id` | text → `transactions` | The row that triggered it (empty for whole-month alerts) | `c0e5a8f1937b2d46` |
| `kind` | text | `new_merchant`, `big_charge`, `double_charge`, `new_subscription`, `price_increase`, `trial_converted`, `category_spike` | `double_charge` |
| `message` | text | Plain-English text shown to you | `City Cabs charged 64.00 twice within 2 days` |
| `dedupe_key` | text | **Unique**, so the same alert is never stored twice | `double_charge:c0e5a8f1937b2d46` |
| `created_at` | text | | |
| `dismissed_at` | text | When you clicked "dismiss" (empty = still showing) | |

### 5.6 `sync_runs`: Google Sheets update log

| Column | Meaning | Example |
|---|---|---|
| `id` | | `12` |
| `started_at`, `finished_at` | When it ran | |
| `status` | `running`, `ok` or `failed` | `ok` |
| `tabs_rebuilt` | JSON list of rebuilt tabs | `["Grocery/2026-11", "Travel/2026-11"]` |
| `rows_synced` | How many changed rows were handled | `142` |
| `error` | What went wrong, if anything | |

### 5.7 `ai_calls`: Claude cost log

| Column | Meaning | Example |
|---|---|---|
| `id` | | `40` |
| `statement_id` | Which statement (kept empty if the statement is later deleted, so your cost history survives) | `7` |
| `purpose` | `extract` (reading pages) or `categorize` | `extract` |
| `model` | Model used | `claude-opus-5-5` |
| `input_tokens`, `output_tokens` | Tokens read and written | `9120`, `2875` |
| `cost_usd` | Calculated from the prices in `config.yaml` | `0.094` |
| `duration_ms` | How long it took | `21450` |
| `stop_reason` | Why the answer ended (`end_turn` = normally) | `end_turn` |
| `created_at` | | |

---

## 6. Statuses and flags

### Statement `status`

| Value | 💡 Meaning | Next step |
|---|---|---|
| `uploaded` | Received, not started | Processing starts automatically |
| `processing` | Being read and sorted | Wait |
| `mismatch` | The numbers don't add up; every row is held | Fix the rows, or approve the statement after checking it |
| `ready` | Verified and sorted | Review any unsure rows, then sync |
| `synced` | Every row is in Google Sheets | Nothing to do |
| `failed` | Couldn't be processed (`error` says why) | Fix the cause, then process again (always safe) |

### Transaction `review_reason`

| Value | Set when | Cleared when |
|---|---|---|
| `Statement totals don't match` | The statement failed the math check | You fix and approve the row, or approve the whole statement |
| `AI wasn't sure` | AI confidence was `medium` or `low` (configurable) | You approve or change the category |

### Transaction `category_source`

| Value | Means | Confidence |
|---|---|---|
| `user` | You chose it | always `high` |
| `rule` | A saved merchant rule matched | `high` |
| `keyword` | A keyword from `config.yaml` matched | `high` |
| `ai` | Claude decided | `high`, `medium` or `low` |

---

## 7. How duplicates are prevented

> 💡 Two locks on the door: one for **files**, one for **rows**.

**Lock 1: the file fingerprint** (`statements.file_hash`, unique)
The same PDF always gives the same fingerprint, even if renamed, so uploading it again is stopped instantly at no cost.

**Lock 2: the transaction fingerprint** (`transactions.id`, primary key)
Built from: account type + last 4 digits, date, money out, money in, and the description (lowercased, letters and digits only), plus a counter.

```
"bank:1234 | 2026-11-02 | 54.2 | None | pos4471frshmrtcty | 1"  →  SHA-256  →  9f2c41d0a7b3e815
```

- **Overlapping statements** (e.g. Oct 15 – Nov 14, then Nov 1 – Nov 30) produce the **same fingerprints** for the shared rows, and the database ignores the second copy (`INSERT OR IGNORE`).
- **Two identical coffees on the same day** get counters `|1` and `|2`, so both are kept, because both really happened.
- **Spacing and punctuation differences** (`POS 4471  FRSHMRT*CTY` vs `POS 4471 FRSHMRT CTY`) are ignored by the fingerprint.

---

## 8. How the Google Sheets stay in sync

> 💡 Every transaction carries little notes: **"which sheet and month tab am I in?"** (`synced_category`, `synced_month`) and **"is the sheet up to date with me?"** (`synced_at`). When anything about a row changes, we erase `synced_at`. The next sync finds every row with an empty `synced_at` and rebuilds the month tabs they belong to, *and* the tab they used to belong to.

### Worked example

| Step | What happens | `category` | `synced_category` | `synced_at` | Sheets |
|---|---|---|---|---|---|
| 1 | Row is read and categorized | `Grocery` | — | — | not there yet |
| 2 | **Sync** → rebuilds Grocery / 2026-11 | `Grocery` | `Grocery` | `14:10` | in **Grocery** |
| 3 | You change it to Travel in the app | `Travel` | `Grocery` | — *(erased)* | still in Grocery (out of date) |
| 4 | **Sync** → rebuilds Travel / 2026-11 **and** Grocery / 2026-11 | `Travel` | `Travel` | `14:32` | in **Travel**, gone from Grocery ✅ |

### The rules
1. A row is **eligible for Sheets** when `needs_review = 0` and it has a category.
2. A row **needs syncing** when `synced_at` is empty.
3. Sync rebuilds tabs `(category, month)` and `(synced_category, synced_month)` for every row that needs syncing, but only for categories that have a sheet. (So fixing a misread **date** also cleans the old month's tab.)
4. Afterwards: `synced_at = now`, `synced_category = category`, `synced_month = month`.
5. Rows in categories without a sheet (e.g. `Not an expense`) are simply marked as synced.
6. A statement becomes `synced` once none of its rows need syncing.

---

## 9. Common queries

> 💡 These are the questions the app asks the database. You can run them yourself with any SQLite viewer (e.g. the free "DB Browser for SQLite") **read-only**, just to look.

**Monthly totals per category** (what the Summary tabs show):
```sql
SELECT month, category, total, transactions
FROM monthly_totals
WHERE category != 'Not an expense'
ORDER BY month DESC, category;
```

**Spending vs. set aside vs. savings rate, per month:**
```sql
SELECT month,
       ROUND(SUM(CASE WHEN category IN ('Grocery','Travel','Subscriptions','Other') THEN amount END), 2) AS spending,
       ROUND(SUM(CASE WHEN category IN ('Investments','Savings') THEN amount END), 2)                    AS set_aside,
       ROUND(-SUM(CASE WHEN category = 'Not an expense' AND amount < 0 THEN amount END), 2)               AS money_in,
       ROUND(100.0 * SUM(CASE WHEN category IN ('Investments','Savings') THEN amount END)
             / NULLIF(-SUM(CASE WHEN category = 'Not an expense' AND amount < 0 THEN amount END), 0), 1) AS savings_rate_pct
FROM transactions
WHERE needs_review = 0
GROUP BY month
ORDER BY month DESC;
```

**The review queue:**
```sql
SELECT id, txn_date, description, merchant, amount, category, confidence, review_reason
FROM transactions
WHERE needs_review = 1
ORDER BY txn_date;
```

**What needs syncing:**
```sql
SELECT id, month, category, synced_category
FROM transactions
WHERE synced_at IS NULL AND needs_review = 0 AND category IS NOT NULL;
```

**Exactly what one month tab should contain:**
```sql
SELECT t.txn_date, COALESCE(t.merchant, ''), t.description, t.amount, t.currency,
       COALESCE(a.bank_name, 'Account') || ' ••' || COALESCE(a.account_last4, '????'), t.id
FROM transactions t
LEFT JOIN accounts a ON a.id = t.account_id
WHERE t.category = 'Grocery' AND t.month = '2026-11' AND t.needs_review = 0
ORDER BY t.txn_date, t.row_number;
```

**Top 10 shops this month:**
```sql
SELECT COALESCE(merchant, description) AS shop, ROUND(SUM(amount), 2) AS total, COUNT(*) AS visits
FROM transactions
WHERE month = '2026-11' AND amount > 0 AND category != 'Not an expense'
GROUP BY shop
ORDER BY total DESC
LIMIT 10;
```

**AI cost this month:**
```sql
SELECT purpose, COUNT(*) AS calls, SUM(input_tokens) AS tokens_in,
       SUM(output_tokens) AS tokens_out, ROUND(SUM(cost_usd), 4) AS usd
FROM ai_calls
WHERE created_at LIKE '2026-11%'
GROUP BY purpose;
```

**Open alerts:**
```sql
SELECT kind, message, created_at FROM alerts WHERE dismissed_at IS NULL ORDER BY created_at DESC;
```

---

## 10. Migrations: changing the database safely

> 💡 When a future version needs a new column or table, we don't edit the database by hand. We add a numbered "upgrade script", and the app applies any it hasn't applied yet, in order, when it starts.

- Upgrade scripts live in `finance/migrations/`: `001_init.sql` (the tables below) and `002_synced_month.sql` (adds `transactions.synced_month`, so a row moved to another month leaves no stale copy in the old tab). The current version is **2**.
- The database remembers its version number (SQLite's built-in `PRAGMA user_version`).
- On start, `ledger.migrate()` runs every script with a number higher than the stored version, then updates the version.
- **Never edit a script that has already run.** Add a new one instead.
- `ledger.migrate()` makes a backup before applying any upgrade.

---

## 11. Backups and restore

> 💡 The database is one file, so a backup is just a safe copy of it.

| When | How |
|---|---|
| Automatically before every sync and every upgrade | `ledger.backup()` → `data/backups/ledger-2026-11-22-141002.db`, keeping the newest 10 |
| Whenever you like | `python cli.py backup` |
| Restore | Quit the app, copy a backup over `data/ledger.db`, start the app again, then run `python cli.py rebuild --all` to refresh the sheets |

Backups use SQLite's own backup feature, so they're safe even while the app is running.

💡 **Extra safety:** also copy `data/backups/` to an encrypted external drive once in a while. Your Google Sheets are not a backup of the database: they hold only the 5 categories and none of the rules.

---

## 12. Privacy: what's stored, and how to delete it

| Stored | Not stored |
|---|---|
| Transaction dates, descriptions, amounts, balances | Full account or card numbers |
| Account type, bank name, last 4 digits | Your PDF passwords (they're in the macOS Keychain) |
| Your rules and corrections | API keys (they're in `.env`) |
| Copies of your statement PDFs (`data/statements/`) | |

**Delete one statement:** `python cli.py forget <statement-id>` removes the statement, its transactions and its stored PDF, then refreshes the affected sheets.
**Delete everything:** quit the app and delete the `data/` folder. Then empty or delete the 5 Google Sheets, and remove the saved passwords with `python cli.py password remove <name>`.

Note: if a transaction appeared in two overlapping statements, it belongs to the statement that recorded it **first**. Forgetting that statement removes the row too. Re-process the other statement to bring it back.

---

## 13. The full schema

Upgrade 002 then adds one column:

```sql
-- finance/migrations/002_synced_month.sql
ALTER TABLE transactions ADD COLUMN synced_month TEXT;
UPDATE transactions SET synced_month = month WHERE synced_category IS NOT NULL;
```

The original tables (version 1):

```sql
-- finance/migrations/001_init.sql
-- Where Did My Money Go? database, version 1.
-- Amounts: positive = money out, negative = money in. Dates: 'YYYY-MM-DD' text.

CREATE TABLE accounts (
    id             INTEGER PRIMARY KEY,
    kind           TEXT    NOT NULL DEFAULT 'bank' CHECK (kind IN ('bank', 'card')),
    account_last4  TEXT    NOT NULL DEFAULT 'unknown',
    bank_name      TEXT,
    currency       TEXT    NOT NULL,
    nickname       TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (kind, account_last4)
);

CREATE TABLE statements (
    id                INTEGER PRIMARY KEY,
    file_hash         TEXT    NOT NULL UNIQUE,
    file_name         TEXT    NOT NULL,
    stored_path       TEXT,
    account_id        INTEGER REFERENCES accounts(id),
    period_start      TEXT,
    period_end        TEXT,
    opening_balance   REAL,
    closing_balance   REAL,
    page_count        INTEGER,
    status            TEXT    NOT NULL DEFAULT 'uploaded'
                      CHECK (status IN ('uploaded', 'processing', 'mismatch', 'ready', 'synced', 'failed')),
    issues            TEXT,
    approved_by_user  INTEGER NOT NULL DEFAULT 0 CHECK (approved_by_user IN (0, 1)),
    error             TEXT,
    uploaded_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    processed_at      TEXT
);

CREATE TABLE transactions (
    id               TEXT    PRIMARY KEY,
    statement_id     INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    account_id       INTEGER REFERENCES accounts(id),
    row_number       INTEGER NOT NULL,
    txn_date         TEXT    NOT NULL,
    month            TEXT    GENERATED ALWAYS AS (substr(txn_date, 1, 7)) VIRTUAL,
    description      TEXT    NOT NULL,
    merchant         TEXT,
    amount           REAL    NOT NULL,
    balance_after    REAL,
    currency         TEXT    NOT NULL,
    category         TEXT    CHECK (category IN ('Grocery', 'Travel', 'Subscriptions', 'Investments',
                                                 'Savings', 'Other', 'Not an expense')),
    confidence       TEXT    CHECK (confidence IN ('high', 'medium', 'low')),
    category_source  TEXT    CHECK (category_source IN ('user', 'rule', 'keyword', 'ai')),
    needs_review     INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    review_reason    TEXT,
    synced_category  TEXT,
    synced_at        TEXT,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE merchant_rules (
    merchant_key  TEXT    PRIMARY KEY,
    merchant      TEXT    NOT NULL,
    category      TEXT    NOT NULL CHECK (category IN ('Grocery', 'Travel', 'Subscriptions', 'Investments',
                                                       'Savings', 'Other', 'Not an expense')),
    source        TEXT    NOT NULL CHECK (source IN ('user', 'ai')),
    times_used    INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE alerts (
    id              INTEGER PRIMARY KEY,
    transaction_id  TEXT    REFERENCES transactions(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN ('new_merchant', 'big_charge', 'double_charge',
                                                     'new_subscription', 'price_increase',
                                                     'trial_converted', 'category_spike')),
    message         TEXT    NOT NULL,
    dedupe_key      TEXT    NOT NULL UNIQUE,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    dismissed_at    TEXT
);

CREATE TABLE sync_runs (
    id            INTEGER PRIMARY KEY,
    started_at    TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    finished_at   TEXT,
    status        TEXT    NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed')),
    tabs_rebuilt  TEXT,
    rows_synced   INTEGER,
    error         TEXT
);

CREATE TABLE ai_calls (
    id             INTEGER PRIMARY KEY,
    statement_id   INTEGER REFERENCES statements(id) ON DELETE SET NULL,
    purpose        TEXT    NOT NULL CHECK (purpose IN ('extract', 'categorize')),
    model          TEXT    NOT NULL,
    input_tokens   INTEGER NOT NULL,
    output_tokens  INTEGER NOT NULL,
    cost_usd       REAL    NOT NULL,
    duration_ms    INTEGER NOT NULL,
    stop_reason    TEXT,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX idx_transactions_statement     ON transactions (statement_id);
CREATE INDEX idx_transactions_category_date ON transactions (category, txn_date);
CREATE INDEX idx_transactions_merchant_date ON transactions (merchant, txn_date);
CREATE INDEX idx_transactions_unsynced      ON transactions (synced_at) WHERE synced_at IS NULL;
CREATE INDEX idx_transactions_review        ON transactions (needs_review) WHERE needs_review = 1;
CREATE INDEX idx_ai_calls_created           ON ai_calls (created_at);

CREATE VIEW monthly_totals AS
SELECT month, category, ROUND(SUM(amount), 2) AS total, COUNT(*) AS transactions
FROM transactions
WHERE category IS NOT NULL AND needs_review = 0
GROUP BY month, category;
```

**Why these indexes?** 💡 An index is like the index at the back of a book: it lets the database jump straight to the right rows instead of reading every page.

| Index | Speeds up |
|---|---|
| `statement` | "All rows from statement 7" (review, forget) |
| `category_date` | Building a month tab, monthly totals |
| `merchant_date` | Alerts ("this shop's earlier charges") |
| `unsynced` (partial) | "What needs syncing?" (indexes only the few unsynced rows) |
| `review` (partial) | The review queue |
| `ai_calls created` | Cost per month |
