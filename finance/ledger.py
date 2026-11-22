"""The ledger: every read and write to the database goes through this file.

In plain English: the database (data/ledger.db) is the app's master notebook.
No other module writes SQL, so all the database rules live in one place.
Tables and columns are explained in DB.md.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from finance.config import NOT_EXPENSE, SET_ASIDE, SPENDING
from finance.costs import AICall
from finance.ids import merchant_key, pretty_merchant

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
REVIEW_MISMATCH = "Statement totals don't match"
REVIEW_UNSURE = "AI wasn't sure"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean(value):
    """pandas uses NaN for empty cells; the database wants None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _in(values) -> str:
    return ",".join("?" * len(values))


# ── Connecting and upgrading ─────────────────────────────────────────────────


def connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row  # rows work like dicts: row["amount"]
    db.execute("PRAGMA foreign_keys = ON")  # enforce the links between tables
    db.execute("PRAGMA journal_mode = WAL")  # safer writes; reading doesn't block writing
    migrate(db, backups_dir=path.parent / "backups")
    return db


def migrate(db: sqlite3.Connection, backups_dir: Path | None = None) -> None:
    """Apply any migration files newer than the database's version number."""
    current = db.execute("PRAGMA user_version").fetchone()[0]
    pending = [f for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if int(f.name.split("_")[0]) > current]
    if pending and current > 0 and backups_dir:
        backup(db, backups_dir)  # safety copy before upgrading an existing database
    for file in pending:
        version = int(file.name.split("_")[0])  # 001_init.sql → 1
        db.executescript(file.read_text())
        db.execute(f"PRAGMA user_version = {version}")
        db.commit()


def backup(db: sqlite3.Connection, backups_dir: Path, keep: int = 10) -> Path:
    """Copy the database to backups_dir (safe while the app is running); keep the newest `keep`."""
    backups_dir = Path(backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)
    target = backups_dir / f"ledger-{datetime.now():%Y-%m-%d-%H%M%S}.db"
    dest = sqlite3.connect(target)
    try:
        db.backup(dest)
    finally:
        dest.close()
    for old in sorted(backups_dir.glob("ledger-*.db"))[:-keep]:
        old.unlink()
    return target


# ── Accounts ─────────────────────────────────────────────────────────────────


def upsert_account(db, kind: str | None, last4: str | None, bank_name: str | None, currency: str) -> int:
    kind, last4 = kind or "bank", last4 or "unknown"
    db.execute(
        """INSERT INTO accounts (kind, account_last4, bank_name, currency) VALUES (?, ?, ?, ?)
           ON CONFLICT(kind, account_last4) DO UPDATE SET
               bank_name = COALESCE(accounts.bank_name, excluded.bank_name)""",
        (kind, last4, bank_name, currency),
    )
    db.commit()
    return db.execute(
        "SELECT id FROM accounts WHERE kind = ? AND account_last4 = ?", (kind, last4)
    ).fetchone()["id"]


# ── Statements ───────────────────────────────────────────────────────────────


def find_statement(db, file_hash: str):
    return db.execute("SELECT * FROM statements WHERE file_hash = ?", (file_hash,)).fetchone()


def get_statement(db, statement_id: int):
    return db.execute("SELECT * FROM statements WHERE id = ?", (statement_id,)).fetchone()


def create_statement(db, file_hash: str, file_name: str, stored_path: Path) -> int:
    cur = db.execute(
        "INSERT INTO statements (file_hash, file_name, stored_path) VALUES (?, ?, ?)",
        (file_hash, file_name, str(stored_path)),
    )
    db.commit()
    return cur.lastrowid


def set_status(
    db, statement_id: int, status: str, issues: list[str] | None = None, error: str | None = None
) -> None:
    finished = status in ("ready", "mismatch", "failed")
    db.execute(
        """UPDATE statements SET status = ?, issues = ?, error = ?,
               processed_at = CASE WHEN ? THEN ? ELSE processed_at END
           WHERE id = ?""",
        (status, json.dumps(issues) if issues else None, error, int(finished), now(), statement_id),
    )
    db.commit()


def save_statement_details(db, statement_id: int, stmt, account_id: int, page_count: int) -> None:
    db.execute(
        """UPDATE statements SET account_id = ?, period_start = ?, period_end = ?,
               opening_balance = ?, closing_balance = ?, page_count = ?
           WHERE id = ?""",
        (
            account_id,
            stmt.period_start,
            stmt.period_end,
            stmt.opening_balance,
            stmt.closing_balance,
            page_count,
            statement_id,
        ),
    )
    db.commit()


def list_statements(db) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT s.id, s.file_name, s.period_start, s.period_end, s.status, s.issues, s.error,
                  s.uploaded_at, s.stored_path, s.approved_by_user,
                  COALESCE(a.bank_name, '') || CASE WHEN a.id IS NULL THEN '' ELSE ' ••' || a.account_last4 END
                      AS account,
                  COUNT(t.id) AS rows,
                  COALESCE(SUM(t.needs_review), 0) AS to_review,
                  COALESCE(SUM(CASE WHEN t.synced_at IS NULL THEN 1 ELSE 0 END), 0) AS unsynced
           FROM statements s
           LEFT JOIN accounts a ON a.id = s.account_id
           LEFT JOIN transactions t ON t.statement_id = s.id
           GROUP BY s.id
           ORDER BY s.uploaded_at DESC, s.id DESC""",
        db,
    )


def statement_kind(db, statement_id: int) -> str:
    row = db.execute(
        """SELECT a.kind FROM statements s LEFT JOIN accounts a ON a.id = s.account_id
                        WHERE s.id = ?""",
        (statement_id,),
    ).fetchone()
    return row["kind"] if row and row["kind"] else "bank"


def count_review(db, statement_id: int) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM transactions WHERE statement_id = ? AND needs_review = 1", (statement_id,)
    ).fetchone()[0]


def approve_statement(db, statement_id: int, review_if: list[str], by_user: bool = True) -> None:
    """Accept a statement whose math didn't match (or now matches). Rows the AI was unsure about stay in review."""
    unsure = f"(category IS NULL OR (category_source = 'ai' AND confidence IN ({_in(review_if)})))"
    db.execute(
        f"""UPDATE transactions SET
                needs_review = CASE WHEN {unsure} THEN 1 ELSE 0 END,
                review_reason = CASE WHEN {unsure} THEN ? ELSE NULL END,
                synced_at = NULL, updated_at = ?
            WHERE statement_id = ? AND review_reason = ?""",
        (*review_if, *review_if, REVIEW_UNSURE, now(), statement_id, REVIEW_MISMATCH),
    )
    db.execute(
        """UPDATE statements SET approved_by_user = ?, status = 'ready', issues = CASE WHEN ? THEN issues END
                  WHERE id = ? AND status = 'mismatch'""",
        (int(by_user), int(by_user), statement_id),
    )
    db.commit()


def forget_statement(db, statement_id: int) -> tuple[set[tuple[str, str]], str | None]:
    """Delete a statement and its rows. Returns the sheet tabs that need rebuilding and the stored PDF path."""
    tabs = {
        (r["synced_category"], r["month"])
        for r in db.execute(
            "SELECT DISTINCT synced_category, COALESCE(synced_month, month) AS month FROM transactions WHERE statement_id = ? AND synced_category IS NOT NULL",
            (statement_id,),
        )
    }
    row = get_statement(db, statement_id)
    db.execute("DELETE FROM statements WHERE id = ?", (statement_id,))
    db.commit()
    return tabs, (row["stored_path"] if row else None)


def refresh_statement_statuses(db) -> None:
    """Keep statement statuses in step with their rows."""
    db.execute(
        """UPDATE statements SET status = 'ready', approved_by_user = 1
           WHERE status = 'mismatch' AND NOT EXISTS (
               SELECT 1 FROM transactions t WHERE t.statement_id = statements.id AND t.review_reason = ?)""",
        (REVIEW_MISMATCH,),
    )
    db.execute(
        """UPDATE statements SET status = 'synced'
           WHERE status = 'ready' AND NOT EXISTS (
               SELECT 1 FROM transactions t WHERE t.statement_id = statements.id AND t.synced_at IS NULL)"""
    )
    db.execute(
        """UPDATE statements SET status = 'ready'
           WHERE status = 'synced' AND EXISTS (
               SELECT 1 FROM transactions t WHERE t.statement_id = statements.id AND t.synced_at IS NULL)"""
    )
    db.commit()


# ── Transactions ─────────────────────────────────────────────────────────────


def save_transactions(
    db, statement_id: int, account_id: int, stmt, txn_ids: list[str], currency: str, hold_for_review: bool
) -> int:
    """Insert new rows and silently skip ones we already have. Returns how many were new."""
    reason = REVIEW_MISMATCH if hold_for_review else None
    rows = [
        {
            "id": txn_id,
            "statement_id": statement_id,
            "account_id": account_id,
            "row_number": n,
            "txn_date": t.date,
            "description": t.description.strip(),
            "amount": round((t.debit or 0) - (t.credit or 0), 2),  # + money out, − money in
            "balance_after": t.balance,
            "currency": (stmt.currency or currency).upper(),
            "needs_review": int(hold_for_review),
            "review_reason": reason,
        }
        for n, (t, txn_id) in enumerate(zip(stmt.transactions, txn_ids, strict=True), start=1)
    ]
    before = db.total_changes
    db.executemany(
        """INSERT OR IGNORE INTO transactions
               (id, statement_id, account_id, row_number, txn_date, description, amount,
                balance_after, currency, needs_review, review_reason)
           VALUES
               (:id, :statement_id, :account_id, :row_number, :txn_date, :description, :amount,
                :balance_after, :currency, :needs_review, :review_reason)""",
        rows,
    )
    db.commit()
    return db.total_changes - before


def statement_rows(db, statement_id: int) -> list[sqlite3.Row]:
    return db.execute(
        "SELECT * FROM transactions WHERE statement_id = ? ORDER BY row_number", (statement_id,)
    ).fetchall()


def uncategorized(db) -> list[sqlite3.Row]:
    """Every row still waiting for a category, whichever upload it came from. (If an earlier
    attempt failed half-way and you re-upload a freshly downloaded copy, the rows already saved
    by the first attempt belong to that attempt, but they still need sorting.)"""
    return db.execute(
        """SELECT id, txn_date, description, amount FROM transactions
           WHERE category IS NULL ORDER BY statement_id, row_number"""
    ).fetchall()


def apply_categories(db, updates: list[dict], review_if: list[str]) -> None:
    """Save categories; AI answers below the confidence bar go to the review queue."""
    stamp = now()
    for u in updates:
        unsure = int(u["source"] == "ai" and u["confidence"] in review_if)
        db.execute(
            """UPDATE transactions SET
                   merchant = COALESCE(?, merchant), category = ?, confidence = ?, category_source = ?,
                   needs_review = CASE WHEN needs_review = 1 OR ? THEN 1 ELSE 0 END,
                   review_reason = CASE WHEN review_reason IS NOT NULL THEN review_reason
                                        WHEN ? THEN ? ELSE NULL END,
                   synced_at = NULL, updated_at = ?
               WHERE id = ?""",
            (
                u["merchant"],
                u["category"],
                u["confidence"],
                u["source"],
                unsure,
                unsure,
                REVIEW_UNSURE,
                stamp,
                u["id"],
            ),
        )
    db.commit()


def review_queue(db) -> pd.DataFrame:
    """Rows the AI wasn't sure about. Rows held by a statement mismatch are handled on the Statements page."""
    return pd.read_sql_query(
        """SELECT id, txn_date, description, merchant, amount, category, confidence, review_reason
           FROM transactions WHERE needs_review = 1 AND COALESCE(review_reason, '') != ?
           ORDER BY txn_date, row_number""",
        db,
        params=(REVIEW_MISMATCH,),
    )


def apply_user_review(db, edited: pd.DataFrame, remember: bool) -> int:
    """Approve reviewed rows with your chosen category; optionally remember the shop."""
    stamp = now()
    for row in edited.itertuples(index=False):
        category = _clean(row.category)
        if not category:
            continue
        merchant = _clean(row.merchant) or pretty_merchant(row.description)
        db.execute(
            """UPDATE transactions SET category = ?, merchant = ?, confidence = 'high', category_source = 'user',
                   needs_review = 0, review_reason = NULL, synced_at = NULL, updated_at = ?
               WHERE id = ?""",
            (category, merchant, stamp, row.id),
        )
        if remember:
            save_rule(db, merchant_key(row.description), merchant, category, "user", commit=False)
    db.commit()
    refresh_statement_statuses(db)
    return len(edited)


def transactions_frame(
    db,
    month: str | None = None,
    category: str | None = None,
    search: str | None = None,
    statement_id: int | None = None,
) -> pd.DataFrame:
    where, params = ["1 = 1"], []
    if month:
        where.append("month = ?")
        params.append(month)
    if category:
        where.append("category = ?")
        params.append(category)
    if search:
        where.append("(description LIKE ? OR merchant LIKE ?)")
        params += [f"%{search}%", f"%{search}%"]
    if statement_id:
        where.append("statement_id = ?")
        params.append(statement_id)
    return pd.read_sql_query(
        f"""SELECT id, statement_id, row_number, txn_date, description, merchant, amount, category,
                   confidence, category_source, needs_review, review_reason, synced_at
            FROM transactions WHERE {" AND ".join(where)}
            ORDER BY txn_date DESC, row_number DESC""",
        db,
        params=params,
    )


class EditError(ValueError):
    """An edit that can't be saved (e.g. a date that isn't YYYY-MM-DD)."""


def _valid_date(value: str) -> str:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError as e:
        raise EditError(f"'{value}' isn't a date like 2026-11-05") from e


def apply_user_edits(db, before: pd.DataFrame, after: pd.DataFrame, remember: bool) -> tuple[int, set[int]]:
    """Save edits from the Transactions page (shop, category, amount, date).
    Returns (rows changed, statements whose amounts or dates changed, so they can be re-checked)."""
    old = before.set_index("id")
    changed, recheck = 0, set()
    stamp = now()
    for row in after.itertuples(index=False):
        prev = old.loc[row.id]
        category, merchant = _clean(row.category), _clean(row.merchant)
        amount = float(row.amount) if _clean(row.amount) is not None else float(prev.amount)
        txn_date = _valid_date(row.txn_date) if _clean(row.txn_date) else prev.txn_date
        cat_changed = category != _clean(prev.category)
        amount_changed = abs(amount - float(prev.amount)) > 0.001
        date_changed = txn_date != prev.txn_date
        if not (cat_changed or amount_changed or date_changed or merchant != _clean(prev.merchant)):
            continue
        changed += 1
        if amount_changed or date_changed:
            recheck.add(int(prev.statement_id))
        db.execute(
            f"""UPDATE transactions SET category = ?, merchant = ?, amount = ?, txn_date = ?,
                    {"category_source = 'user', confidence = 'high', needs_review = 0, review_reason = NULL," if cat_changed else ""}
                    synced_at = NULL, updated_at = ?
                WHERE id = ?""",
            (category, merchant, round(amount, 2), txn_date, stamp, row.id),
        )
        if remember and cat_changed and category:
            save_rule(
                db,
                merchant_key(row.description),
                merchant or pretty_merchant(row.description),
                category,
                "user",
                commit=False,
            )
    db.commit()
    refresh_statement_statuses(db)
    return changed, recheck


def recent_corrections(db, limit: int = 40) -> list[str]:
    rows = db.execute(
        """SELECT description, category FROM transactions WHERE category_source = 'user'
           ORDER BY updated_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [f'"{r["description"]}" → {r["category"]}' for r in rows]


def months(db) -> list[str]:
    return [r[0] for r in db.execute("SELECT DISTINCT month FROM transactions ORDER BY month DESC")]


# ── Merchant rules ───────────────────────────────────────────────────────────


def merchant_rules(db) -> dict[str, tuple[str, str]]:
    return {
        r["merchant_key"]: (r["merchant"], r["category"])
        for r in db.execute("SELECT merchant_key, merchant, category FROM merchant_rules")
    }


def save_rule(db, key: str, merchant: str, category: str, source: str, commit: bool = True) -> None:
    """Remember a shop. Your own rules (source 'user') are never overwritten by the AI."""
    if not key:
        return
    db.execute(
        """INSERT INTO merchant_rules (merchant_key, merchant, category, source) VALUES (?, ?, ?, ?)
           ON CONFLICT(merchant_key) DO UPDATE SET
               merchant = excluded.merchant, category = excluded.category, source = excluded.source,
               updated_at = datetime('now', 'localtime')
           WHERE merchant_rules.source = 'ai' OR excluded.source = 'user'""",
        (key, merchant, category, source),
    )
    if commit:
        db.commit()


def bump_rules(db, keys: list[str]) -> None:
    db.executemany(
        "UPDATE merchant_rules SET times_used = times_used + 1 WHERE merchant_key = ?", [(k,) for k in keys]
    )
    db.commit()


def list_rules(db) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT merchant_key, merchant, category, source, times_used, updated_at
           FROM merchant_rules ORDER BY times_used DESC, merchant""",
        db,
    )


def delete_rule(db, key: str) -> None:
    db.execute("DELETE FROM merchant_rules WHERE merchant_key = ?", (key,))
    db.commit()


# ── Sync bookkeeping ─────────────────────────────────────────────────────────


def rows_needing_sync(db) -> list[sqlite3.Row]:
    return db.execute(
        """SELECT id, month, category, synced_category, synced_month FROM transactions
           WHERE synced_at IS NULL AND needs_review = 0 AND category IS NOT NULL"""
    ).fetchall()


def rows_for_tab(db, category: str, month: str) -> list[list]:
    """Exactly what one month tab should contain."""
    rows = db.execute(
        """SELECT t.txn_date, COALESCE(t.merchant, ''), t.description, t.amount, t.currency,
                  COALESCE(a.bank_name, 'Account') || ' ••' || COALESCE(a.account_last4, '????'), t.id
           FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id
           WHERE t.category = ? AND t.month = ? AND t.needs_review = 0
           ORDER BY t.txn_date, t.row_number""",
        (category, month),
    ).fetchall()
    return [list(r) for r in rows]


def months_for(db, category: str) -> list[str]:
    return [
        r[0]
        for r in db.execute(
            "SELECT DISTINCT month FROM transactions WHERE category = ? AND needs_review = 0", (category,)
        )
    ]


def mark_synced(db, ids: list[str]) -> None:
    """Remember that Google Sheets now matches these rows."""
    stamp = now()
    db.executemany(
        "UPDATE transactions SET synced_at = ?, synced_category = category, synced_month = month WHERE id = ?",
        [(stamp, i) for i in ids],
    )
    db.commit()


def mark_for_resync(db, month: str | None = None) -> int:
    """Make the next sync rebuild a month (or everything if month is None)."""
    if month:
        cur = db.execute("UPDATE transactions SET synced_at = NULL WHERE month = ?", (month,))
    else:
        cur = db.execute("UPDATE transactions SET synced_at = NULL")
    db.commit()
    return cur.rowcount


def start_sync_run(db) -> int:
    cur = db.execute("INSERT INTO sync_runs (status) VALUES ('running')")
    db.commit()
    return cur.lastrowid


def finish_sync_run(
    db, run_id: int, status: str, tabs: list | None = None, rows: int | None = None, error: str | None = None
) -> None:
    db.execute(
        """UPDATE sync_runs SET finished_at = ?, status = ?, tabs_rebuilt = ?, rows_synced = ?, error = ?
           WHERE id = ?""",
        (now(), status, json.dumps([f"{c}/{m}" for c, m in tabs]) if tabs else None, rows, error, run_id),
    )
    db.commit()


def last_sync(db):
    return db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1").fetchone()


# ── AI cost log ──────────────────────────────────────────────────────────────


def record_ai_call(db, statement_id: int | None, call: AICall, cost: float) -> None:
    db.execute(
        """INSERT INTO ai_calls (statement_id, purpose, model, input_tokens, output_tokens, cost_usd,
                                 duration_ms, stop_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            statement_id,
            call.purpose,
            call.model,
            call.input_tokens,
            call.output_tokens,
            cost,
            call.duration_ms,
            call.stop_reason,
        ),
    )
    db.commit()


def costs_summary(db, month: str | None = None) -> pd.DataFrame:
    where, params = ("WHERE created_at LIKE ?", (f"{month}%",)) if month else ("", ())
    return pd.read_sql_query(
        f"""SELECT purpose, COUNT(*) AS calls, SUM(input_tokens) AS tokens_in,
                   SUM(output_tokens) AS tokens_out, ROUND(SUM(cost_usd), 4) AS usd
            FROM ai_calls {where} GROUP BY purpose ORDER BY purpose""",
        db,
        params=params,
    )


# ── Alerts ───────────────────────────────────────────────────────────────────


def save_alerts(db, alerts: list[tuple[str | None, str, str, str]]) -> int:
    """alerts: (transaction_id, kind, message, dedupe_key). Each alert is stored only once."""
    before = db.total_changes
    db.executemany(
        "INSERT OR IGNORE INTO alerts (transaction_id, kind, message, dedupe_key) VALUES (?, ?, ?, ?)", alerts
    )
    db.commit()
    return db.total_changes - before


def open_alerts(db) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT id, kind, message, created_at FROM alerts WHERE dismissed_at IS NULL ORDER BY id DESC", db
    )


def dismiss_alert(db, alert_id: int) -> None:
    db.execute("UPDATE alerts SET dismissed_at = ? WHERE id = ?", (now(), alert_id))
    db.commit()


# ── Reporting ────────────────────────────────────────────────────────────────


def category_totals(db) -> pd.DataFrame:
    return pd.read_sql_query("SELECT month, category, total, transactions FROM monthly_totals", db)


def monthly_overview(db) -> pd.DataFrame:
    """Per month: spending, set aside, money in and savings rate."""
    return pd.read_sql_query(
        f"""SELECT month,
               ROUND(COALESCE(SUM(CASE WHEN category IN ({_in(SPENDING)}) THEN amount END), 0), 2) AS spending,
               ROUND(COALESCE(SUM(CASE WHEN category IN ({_in(SET_ASIDE)}) THEN amount END), 0), 2) AS set_aside,
               ROUND(COALESCE(-SUM(CASE WHEN category = ? AND amount < 0 THEN amount END), 0), 2) AS money_in
            FROM transactions WHERE needs_review = 0 AND category IS NOT NULL
            GROUP BY month ORDER BY month""",
        db,
        params=(*SPENDING, *SET_ASIDE, NOT_EXPENSE),
    )


def top_shops(db, month: str, limit: int = 10) -> pd.DataFrame:
    return pd.read_sql_query(
        f"""SELECT COALESCE(merchant, description) AS shop, category, ROUND(SUM(amount), 2) AS total,
                  COUNT(*) AS visits
           FROM transactions
           WHERE month = ? AND amount > 0 AND category IN ({_in(SPENDING)})
           GROUP BY shop ORDER BY total DESC LIMIT ?""",
        db,
        params=(month, *SPENDING, limit),
    )


def spending_frame(db) -> pd.DataFrame:
    """All categorized money-out rows (for alerts and subscription detection).
    Rows whose date can't be read (e.g. a misread '2026-02-30' held for review) are left out."""
    df = pd.read_sql_query(
        """SELECT id, statement_id, txn_date, COALESCE(merchant, description) AS shop, category, amount
           FROM transactions
           WHERE amount > 0 AND category IS NOT NULL AND category != ?""",
        db,
        params=(NOT_EXPENSE,),
    )
    df["txn_date"] = pd.to_datetime(df.txn_date, format="%Y-%m-%d", errors="coerce")
    return df.dropna(subset=["txn_date"])


def counts(db) -> dict[str, int]:
    """Numbers for the sidebar."""
    q = db.execute(
        """SELECT
               (SELECT COUNT(*) FROM transactions WHERE needs_review = 1 AND COALESCE(review_reason, '') != ?) AS to_review,
               (SELECT COUNT(*) FROM transactions WHERE synced_at IS NULL AND needs_review = 0
                                                   AND category IS NOT NULL) AS unsynced,
               (SELECT COUNT(*) FROM statements WHERE status = 'mismatch') AS mismatches,
               (SELECT COUNT(*) FROM alerts WHERE dismissed_at IS NULL) AS alerts""",
        (REVIEW_MISMATCH,),
    ).fetchone()
    return dict(q)
