"""End-to-end tests: fake PDF → real pipeline (pretend Claude) → database → fake Google Sheets."""

from __future__ import annotations

import pandas as pd
import pytest

from finance import ledger, pipeline
from finance.demo import build_statement, month_rows
from finance.sync import SyncError, sync


def count(db, sql="SELECT COUNT(*) FROM transactions", *params) -> int:
    return db.execute(sql, params).fetchone()[0]


def approve_all_reviews(db):
    queue = ledger.review_queue(db)
    ledger.apply_user_review(db, queue, remember=False)


# ── Processing ───────────────────────────────────────────────────────────────


def test_statement_is_read_checked_and_categorized(run_statement, db):
    result, _, stmt = run_statement("2026-11")
    assert result.status == "ready", result.message
    assert result.new_rows == len(stmt.transactions)
    assert count(db, "SELECT COUNT(*) FROM transactions WHERE category IS NULL") == 0
    salary = db.execute(
        "SELECT category, amount FROM transactions WHERE description LIKE 'SALARY%'"
    ).fetchone()
    assert salary["category"] == "Not an expense" and salary["amount"] < 0
    refund = db.execute(
        "SELECT category, amount FROM transactions WHERE description LIKE 'REFUND%'"
    ).fetchone()
    assert refund["category"] == "Grocery" and refund["amount"] == -8.99
    assert result.sorted_by["keyword"] > 0 and result.sorted_by["ai"] > 0
    assert result.to_review >= 1  # CloudBox and ATM are 'medium' in the pretend Claude


def test_second_statement_uses_learned_rules(run_statement):
    run_statement("2026-10")
    result, _, _ = run_statement("2026-11", opening=3000.0)
    assert result.sorted_by["rule"] > result.sorted_by["ai"]


def test_same_file_twice_is_ignored(run_statement, settings, db):
    _, path, _ = run_statement("2026-11")
    before = count(db)
    again = pipeline.process_statement(path, settings, db)
    assert "Already processed" in again.message and count(db) == before


def test_overlapping_statements_create_no_duplicates(run_statement, db):
    rows = month_rows("2026-11")
    first = build_statement("2026-11", rows=rows[:20])
    balance_after_10 = first.transactions[9].balance
    extra = [(29, "NEW SHOP 1", 10.0, None), (30, "NEW SHOP 2", 20.0, None)]
    second = build_statement("2026-11", opening=balance_after_10, rows=rows[10:20] + extra)
    run_statement(stmt=first)
    result, _, _ = run_statement(stmt=second)
    assert result.status == "ready"
    assert result.new_rows == 2
    assert count(db) == 22


def test_misread_amount_holds_the_whole_statement(run_statement, db, settings):
    truth = build_statement("2026-11")
    misread = truth.model_copy(deep=True)
    assert truth.transactions[3].description == "CITY CABS 0091"
    misread.transactions[3].debit = 18.04  # the AI "misread" the cab fare
    result, _, _ = run_statement(stmt=truth, truth=misread)
    assert result.status == "mismatch"
    assert result.issues and result.issues[0].startswith("Row 4")
    assert ledger.rows_needing_sync(db) == []  # nothing can reach Sheets
    assert ledger.review_queue(db).empty  # handled on the Statements page instead

    # Fix the amount (like on the Transactions page) → re-check → statement is fine again
    sid = result.statement_id
    before = ledger.transactions_frame(db, statement_id=sid)
    after = before.copy()
    after.loc[after.row_number == 4, "amount"] = truth.transactions[3].debit
    changed, statements = ledger.apply_user_edits(db, before, after, remember=False)
    assert changed == 1 and statements == {sid}
    assert pipeline.recheck_statement(db, settings, sid) == []
    assert ledger.get_statement(db, sid)["status"] == "ready"
    assert len(ledger.rows_needing_sync(db)) > 0


def test_user_can_approve_a_mismatched_statement(run_statement, db, settings):
    truth = build_statement("2026-11")
    misread = truth.model_copy(deep=True)
    misread.transactions[0].credit = 4100.00
    result, _, _ = run_statement(stmt=truth, truth=misread)
    ledger.approve_statement(db, result.statement_id, settings.review.review_if_confidence)
    s = ledger.get_statement(db, result.statement_id)
    assert s["status"] == "ready" and s["approved_by_user"] == 1
    assert not ledger.review_queue(db).empty  # unsure AI rows still wait for review


def test_locked_pdf_fails_then_succeeds_with_password(run_statement, settings, db):
    result, path, _ = run_statement("2026-11", password="pw-123")
    assert result.status == "failed" and "locked" in result.message
    stmt = build_statement("2026-11")
    from finance.demo import fake_claude

    number = path.stem
    with fake_claude({number: stmt}):
        retry = pipeline.process_statement(path, settings, db, "pw-123")
    assert retry.status == "ready" and retry.statement_id == result.statement_id


def test_random_pdf_is_politely_rejected(settings, db, tmp_path):
    from reportlab.pdfgen import canvas

    from finance.demo import fake_claude

    path = tmp_path / "menu.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(100, 700, "Pizza menu: Margherita 9.50")
    c.save()
    with fake_claude({}):
        result = pipeline.process_statement(path, settings, db)
    assert result.status == "failed" and "doesn't look like" in result.message


# ── Review & rules ───────────────────────────────────────────────────────────


def test_review_with_remember_creates_user_rule_that_ai_cannot_overwrite(run_statement, db):
    run_statement("2026-11")
    queue = ledger.review_queue(db)
    cloud = queue[queue.description.str.contains("CLOUDBOX")].copy()
    cloud["category"] = "Other"
    ledger.apply_user_review(db, cloud, remember=True)
    ledger.save_rule(db, "cloudbox storage", "CloudBox", "Subscriptions", "ai")
    assert ledger.merchant_rules(db)["cloudbox storage"] == ("CloudBox", "Other")
    assert any("CLOUDBOX" in c for c in ledger.recent_corrections(db))


# ── Sync ─────────────────────────────────────────────────────────────────────


def test_sync_fills_category_month_tabs(run_statement, db, settings, sheets):
    run_statement("2026-11")
    approve_all_reviews(db)
    result = sync(db, settings, mirror_factory=sheets)
    assert ("Grocery", "2026-11") in sheets.tabs and ("Travel", "2026-11") in sheets.tabs
    assert all(cat in settings.sheets for cat, _ in sheets.tabs)  # no 'Other'/'Not an expense' tabs
    assert not any("SALARY" in d for tab in sheets.tabs for d in sheets.descriptions(*tab))
    assert sheets.summaries["Grocery"] == ["2026-11"]
    grocery_total = sum(r[3] for r in sheets.tabs[("Grocery", "2026-11")])
    db_total = db.execute("SELECT SUM(amount) FROM transactions WHERE category='Grocery'").fetchone()[0]
    assert round(grocery_total, 2) == round(db_total, 2)
    assert result.rows > 0 and ledger.rows_needing_sync(db) == []
    assert ledger.list_statements(db).status.tolist() == ["synced"]


def test_second_sync_changes_nothing(run_statement, db, settings, sheets):
    run_statement("2026-11")
    approve_all_reviews(db)
    sync(db, settings, mirror_factory=sheets)
    sheets.rebuilt.clear()
    assert sync(db, settings, mirror_factory=sheets).message == "Google Sheets are already up to date."
    assert sheets.rebuilt == []


def test_recategorized_row_moves_between_sheets(run_statement, db, settings, sheets):
    run_statement("2026-11")
    approve_all_reviews(db)
    sync(db, settings, mirror_factory=sheets)
    before = ledger.transactions_frame(db, search="GREEN GROCER")
    after = before.copy()
    after["category"] = "Travel"
    ledger.apply_user_edits(db, before, after, remember=False)
    sync(db, settings, mirror_factory=sheets)
    assert not any("GREEN GROCER" in d for d in sheets.descriptions("Grocery", "2026-11"))
    assert any("GREEN GROCER" in d for d in sheets.descriptions("Travel", "2026-11"))


def test_statement_spanning_two_months_fills_both_tabs(run_statement, db, settings, sheets):
    rows = [(20, "POS 4471 FRSHMRT*CTY", 50.0, None)]
    oct_part = build_statement("2026-10", rows=rows)
    nov_part = build_statement("2026-11", opening=oct_part.closing_balance, rows=rows)
    stmt = oct_part.model_copy(
        update={
            "transactions": oct_part.transactions + nov_part.transactions,
            "closing_balance": nov_part.closing_balance,
            "period_end": nov_part.period_end,  # the statement really covers Oct 1 – Nov 30
        }
    )
    run_statement(stmt=stmt)
    approve_all_reviews(db)
    sync(db, settings, mirror_factory=sheets)
    assert ("Grocery", "2026-10") in sheets.tabs and ("Grocery", "2026-11") in sheets.tabs


def test_rows_waiting_for_review_are_not_synced(run_statement, db, settings, sheets):
    run_statement("2026-11")
    sync(db, settings, mirror_factory=sheets)
    assert not any("CLOUDBOX" in d for d in sheets.descriptions("Subscriptions", "2026-11"))
    approve_all_reviews(db)
    sync(db, settings, mirror_factory=sheets)
    assert any("CLOUDBOX" in d for d in sheets.descriptions("Subscriptions", "2026-11"))


def test_forgetting_a_statement_removes_its_rows_from_sheets(run_statement, db, settings, sheets):
    result, _, _ = run_statement("2026-11")
    approve_all_reviews(db)
    sync(db, settings, mirror_factory=sheets)
    tabs, _ = ledger.forget_statement(db, result.statement_id)
    sync(db, settings, mirror_factory=sheets, extra_tabs=tabs)
    assert sheets.tabs == {} and count(db) == 0


def test_sync_without_sheets_configured_explains_what_to_do(run_statement, db, settings):
    run_statement("2026-11")
    settings.sheets = {}
    with pytest.raises(SyncError, match="config.yaml"):
        sync(db, settings)


def test_sync_failure_is_recorded_and_safe_to_retry(run_statement, db, settings, sheets):
    run_statement("2026-11")
    approve_all_reviews(db)

    def broken(settings):
        raise ConnectionError("network down")

    with pytest.raises(SyncError, match="safe to run sync again"):
        sync(db, settings, mirror_factory=broken)
    assert ledger.last_sync(db)["status"] == "failed"
    assert len(ledger.rows_needing_sync(db)) > 0  # nothing was marked as synced
    sync(db, settings, mirror_factory=sheets)
    assert ledger.rows_needing_sync(db) == []


# ── Alerts, reports, costs ───────────────────────────────────────────────────


def test_alerts_across_three_months(run_statement, db):
    opening = 2500.0
    for month in ("2026-09", "2026-10", "2026-11"):
        _, _, stmt = run_statement(month, opening=opening)
        opening = stmt.closing_balance
    kinds = set(ledger.open_alerts(db).kind)
    assert {"double_charge", "price_increase", "trial_converted", "big_charge", "new_subscription"} <= kinds
    alerts_df = ledger.open_alerts(db)
    messages = " ".join(alerts_df.message)
    assert "12.99 to 15.99" in messages
    subs = " ".join(alerts_df[alerts_df.kind == "new_subscription"].message)
    assert "GymCo" in subs  # the forgotten subscription is caught…
    for noise in ("Rent", "Fuel", "Savings", "Brightvest", "StreamFlix", "Cash"):
        assert noise not in subs  # …without crying wolf about rent, fuel, transfers or known subscriptions
    assert (alerts_df.kind == "big_charge").sum() == 2  # Fresh Mart 412 + the cab day (once, not twice)


def test_recurring_needs_a_steady_monthly_amount():
    import pandas as pd

    from finance.alerts import recurring

    def charges(shop, amounts, category="Other"):
        dates = pd.to_datetime(["2026-09-05", "2026-10-05", "2026-11-05"])
        return pd.DataFrame(
            {
                "id": [f"{shop}{i}" for i in range(3)],
                "statement_id": 1,
                "txn_date": dates,
                "shop": shop,
                "category": category,
                "amount": amounts,
            }
        )

    df = pd.concat(
        [
            charges("GymCo", [29.99, 29.99, 29.99]),
            charges("Fuel", [41.0, 58.0, 47.0], "Travel"),  # varies → not a subscription
            charges("Savings", [500.0, 500.0, 500.0], "Savings"),  # not spending → ignored
            charges("StreamFlix", [12.99, 12.99, 15.99], "Subscriptions"),  # price rise still counts
        ]
    )
    assert set(recurring(df).shop) == {"GymCo", "StreamFlix"}


def test_monthly_overview_and_summary(run_statement, db):
    run_statement("2026-11")
    approve_all_reviews(db)
    overview = ledger.monthly_overview(db).set_index("month").loc["2026-11"]
    assert overview.money_in == pytest.approx(4200.00 + 3.12)
    assert overview.set_aside == pytest.approx(500 + 300 + 250)
    from finance.summary import monthly_summary

    text = monthly_summary(db, "2026-11")
    assert "November 2026" in text and "Spent" in text and "Savings rate" in text


def test_ai_calls_are_logged(run_statement, db):
    run_statement("2026-11")
    df = ledger.costs_summary(db)
    assert set(df.purpose) == {"extract", "categorize"}


def test_backup_keeps_the_newest_copies(db, settings):
    for _ in range(3):
        ledger.backup(db, settings.backups_dir, keep=2)
    assert len(list(settings.backups_dir.glob("ledger-*.db"))) <= 2


def test_inbox_processing_moves_files(run_statement, db, settings):
    from finance import watcher
    from finance.demo import build_statement, fake_claude, write_pdf

    stmt = build_statement("2026-11")
    write_pdf(stmt, settings.inbox_dir / "nov.pdf", "INBOX-1")
    messages = []
    with fake_claude({"INBOX-1": stmt}):
        assert watcher.process_inbox(settings, db, report=messages.append) == 1
    assert (settings.inbox_dir / "done" / "nov.pdf").exists()
    assert "Balances match" in messages[0]
    assert isinstance(ledger.list_statements(db), pd.DataFrame)
