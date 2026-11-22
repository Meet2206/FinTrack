"""The manager: runs every step for one statement, in order.

In plain English: fingerprint → unlock → read (Claude) → check the math → save →
categorize → alerts. If anything fails, it records a plain-English reason on the
statement and stops safely. Nothing half-finished ever reaches Google Sheets.
Re-running is always safe: rows already saved are skipped.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from finance import alerts, categorize, costs, extract, ids, ledger, pdf_tools, reconcile
from finance.config import Settings
from finance.extract import StatementChunk, Txn

log = logging.getLogger(__name__)


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
    sorted_by: dict[str, int] = field(default_factory=dict)


def read_statement(
    path: Path, settings: Settings, password: str | None = None, on_call=lambda call: None
) -> tuple[StatementChunk, list[str], int]:
    """Unlock, read and check one PDF without saving anything. Returns (statement, issues, pages)."""
    reader = pdf_tools.open_pdf(path, password)
    stmt = extract.extract_statement(reader, settings, on_call=on_call)
    if not stmt.looks_like_statement or not stmt.transactions:
        raise NotAStatement()
    issues = reconcile.check(
        stmt.opening_balance, stmt.closing_balance, stmt.transactions, is_card=(stmt.kind == "card")
    )
    return stmt, issues, len(reader.pages)


def process_statement(path: Path, settings: Settings, db, password: str | None = None) -> Result:
    path = Path(path)
    file_hash = pdf_tools.fingerprint(path)
    existing = ledger.find_statement(db, file_hash)
    if existing and existing["status"] not in ("failed", "uploaded", "processing"):
        return Result(
            existing["id"],
            existing["status"],
            f"Already processed on {existing['uploaded_at'][:10]}. Nothing to do.",
        )

    stored = settings.statements_dir / f"{file_hash[:16]}.pdf"  # keep our own copy
    stored.parent.mkdir(parents=True, exist_ok=True)
    if path.resolve() != stored.resolve():
        shutil.copyfile(path, stored)
    sid = existing["id"] if existing else ledger.create_statement(db, file_hash, path.name, stored)
    ledger.set_status(db, sid, "processing")

    def log_call(call: costs.AICall) -> None:
        ledger.record_ai_call(db, sid, call, costs.cost_usd(call, settings))

    try:
        stmt, issues, pages = read_statement(stored, settings, password, on_call=log_call)
        account_id = ledger.upsert_account(
            db, stmt.kind, stmt.account_last4, stmt.bank_name, stmt.currency or settings.currency
        )
        txn_ids = ids.transaction_ids(ids.account_ref(stmt.kind, stmt.account_last4), stmt.transactions)
        new_rows = ledger.save_transactions(
            db, sid, account_id, stmt, txn_ids, settings.currency, hold_for_review=bool(issues)
        )
        ledger.save_statement_details(db, sid, stmt, account_id, page_count=pages)

        sorted_by = categorize.categorize_statement(db, settings, sid, on_call=log_call)
        alerts.scan(db, sid, settings)

        status = "mismatch" if issues else "ready"
        ledger.set_status(db, sid, status, issues=issues)
        ledger.refresh_statement_statuses(db)
        to_review = ledger.count_review(db, sid) if not issues else 0
        skipped = len(stmt.transactions) - new_rows
        message = f"Read {len(stmt.transactions)} transactions"
        message += f" ({skipped} already known from another statement)." if skipped else "."
        if issues:
            message += " ⚠️ The numbers don't match the statement, so every row is on hold until you check it."
        else:
            message += f" ✅ Balances match to the cent. {to_review} row(s) need your review."
        log.info(
            "statement %s processed: %s rows, %s new, status %s",
            sid,
            len(stmt.transactions),
            new_rows,
            status,
        )
        return Result(sid, status, message, new_rows, to_review, issues, sorted_by)

    except pdf_tools.WrongPassword:
        return _fail(
            db,
            sid,
            "This PDF is locked. Enter its password (and tick 'remember'), or save it "
            "with: python cli.py password add <name>",
        )
    except pdf_tools.BadPdf:
        return _fail(db, sid, "This file isn't a readable PDF.")
    except NotAStatement:
        return _fail(db, sid, "This doesn't look like a bank or card statement (no transactions found).")
    except extract.ChunkTooLong:
        return _fail(db, sid, "A single page has too many rows for the AI to read in one go.")
    except extract.AIDeclined:
        return _fail(db, sid, "The AI declined to process this statement.")
    except extract.MissingAPIKey:
        return _fail(
            db,
            sid,
            "No Claude API key found. Add ANTHROPIC_API_KEY=sk-ant-… to the .env file "
            "(copy .env.example to .env first), then try again.",
        )
    except anthropic.AuthenticationError:
        return _fail(db, sid, "Claude API key is missing or wrong. Check ANTHROPIC_API_KEY in .env.")
    except anthropic.RateLimitError:
        return _fail(db, sid, "Claude is busy right now. Try again in a minute.")
    except anthropic.APIConnectionError:
        return _fail(db, sid, "Couldn't reach Claude. Check your internet connection.")
    except anthropic.APIStatusError as e:
        return _fail(db, sid, f"Claude API error ({e.status_code}). Try again later.")
    except anthropic.AnthropicError as e:
        return _fail(db, sid, f"Couldn't use Claude: {e}. Is ANTHROPIC_API_KEY set in .env?")
    except Exception as e:
        log.exception("statement %s failed unexpectedly", sid)
        return _fail(
            db,
            sid,
            f"Something unexpected went wrong ({type(e).__name__}). Details are in "
            "data/logs/app.log. It's safe to try again.",
        )


def _fail(db, sid: int, message: str) -> Result:
    ledger.set_status(db, sid, "failed", error=message)
    return Result(sid, "failed", message)


def recheck_statement(db, settings: Settings, statement_id: int) -> list[str]:
    """Re-run the math check from the saved rows (after you fixed an amount)."""
    s = ledger.get_statement(db, statement_id)
    rows = ledger.statement_rows(db, statement_id)
    txns = [
        Txn(
            date=r["txn_date"],
            description=r["description"],
            debit=r["amount"] if r["amount"] > 0 else None,
            credit=-r["amount"] if r["amount"] < 0 else None,
            balance=r["balance_after"],
        )
        for r in rows
    ]
    issues = reconcile.check(
        s["opening_balance"],
        s["closing_balance"],
        txns,
        is_card=ledger.statement_kind(db, statement_id) == "card",
    )
    if s["status"] == "mismatch":
        if issues:
            ledger.set_status(db, statement_id, "mismatch", issues=issues)
        else:
            ledger.approve_statement(db, statement_id, settings.review.review_if_confidence, by_user=False)
    return issues
