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
