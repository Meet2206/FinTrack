"""Google Sheets: the REAL SheetsMirror + sync code, talking to an in-memory imitation of Google."""

from __future__ import annotations

import json
import sqlite3

import pytest

from finance import ledger, pipeline, sheets
from finance.demo import build_statement, fake_claude, write_pdf
from finance.sync import SyncError, sync
from tests.fake_gspread import FakeClient

SHEET_IDS = {
    "Grocery": "id-g",
    "Travel": "id-t",
    "Subscriptions": "id-s",
    "Investments": "id-i",
    "Savings": "id-v",
}


@pytest.fixture
def google(monkeypatch, settings):
    """Pretend Google: a fake client, plus a service account file the mirror can find."""
    client = FakeClient()
    settings.service_account_file.write_text(
        json.dumps({"client_email": "robot@money.iam.gserviceaccount.com"})
    )
    monkeypatch.setattr(sheets.gspread, "service_account", lambda filename, http_client=None: client)
    return client


@pytest.fixture
def load(settings, db, tmp_path):
    """Process a fake statement (pretend Claude) and approve its review queue."""
    counter = iter(range(1, 100))

    def _load(month="2026-11", approve=True, **build):
        stmt = build_statement(month, **build)
        number = f"G-{next(counter)}"
        with fake_claude({number: stmt}):
            result = pipeline.process_statement(
                write_pdf(stmt, tmp_path / f"{number}.pdf", number), settings, db
            )
        if approve:
            ledger.apply_user_review(db, ledger.review_queue(db), remember=False)
        return result, stmt

    return _load


def book(google, category):
    return google.books[SHEET_IDS[category]]


def ledger_total(db, category, month):
    return round(
        db.execute(
            "SELECT SUM(amount) FROM transactions WHERE category = ? AND month = ? AND needs_review = 0",
            (category, month),
        ).fetchone()[0]
        or 0,
        2,
    )


def test_first_sync_builds_month_tabs_and_summary(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    grocery = book(google, "Grocery")
    assert grocery.titles == ["Summary", "2026-11"]
    tab = grocery.worksheet("2026-11")
    assert tab.header == sheets.HEADERS and tab.frozen_rows == 1
    assert [r[0] for r in tab.rows] == sorted(r[0] for r in tab.rows), "rows in date order"
    first = tab.rows[0]
    assert isinstance(first[3], float) and first[4] == "USD" and first[5] == "EXAMPLE BANK ••1234"
    assert len(first[6]) == 16, "the transaction fingerprint is the last column"
    for category in SHEET_IDS:
        assert book(google, category).summary()["2026-11"][0] == ledger_total(db, category, "2026-11")


def test_summary_counts_match_the_tabs(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    total, count = book(google, "Travel").summary()["2026-11"]
    assert count == len(book(google, "Travel").worksheet("2026-11").rows)


def test_salary_and_transfers_never_reach_any_sheet(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    every_row = [
        r for b in google.books.values() for ws in b.worksheets() if ws.title != "Summary" for r in ws.rows
    ]
    assert every_row and not any("SALARY" in r[2] or "CREDIT CARD PAYMENT" in r[2] for r in every_row)


def test_other_sheet_is_written_only_when_enabled(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    assert "id-o" not in google.books
    settings.sheets["Other"] = "id-o"
    ledger.mark_for_resync(db)
    sync(db, settings)
    assert google.books["id-o"].worksheet("2026-11").rows


def test_missing_summary_tab_is_created_first(google, load, db, settings):
    google.without_summary.add("id-g")
    load("2026-11")
    sync(db, settings)
    assert book(google, "Grocery").titles[0] == "Summary"


def test_nothing_changed_means_no_writes_at_all(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    google.calls.clear()
    sync(db, settings)
    assert google.writes() == []


def test_recategorized_row_moves_to_the_other_sheet(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    before = ledger.transactions_frame(db, search="GREEN GROCER")
    after = before.copy()
    after["category"] = "Travel"
    ledger.apply_user_edits(db, before, after, remember=False)
    sync(db, settings)
    grocery_desc = [r[2] for r in book(google, "Grocery").worksheet("2026-11").rows]
    travel_desc = [r[2] for r in book(google, "Travel").worksheet("2026-11").rows]
    assert "GREEN GROCER CO" not in grocery_desc and "GREEN GROCER CO" in travel_desc
    assert book(google, "Grocery").summary()["2026-11"][0] == ledger_total(db, "Grocery", "2026-11")


def test_fixed_date_moves_row_to_another_month_and_cleans_the_old_tab(google, load, db, settings):
    load("2026-11", rows=[(5, "POS 4471 FRSHMRT*CTY", 50.0, None), (9, "GREEN GROCER CO", 20.0, None)])
    sync(db, settings)
    before = ledger.transactions_frame(db, search="GREEN GROCER")
    after = before.copy()
    after["txn_date"] = "2026-10-30"  # the user corrects a misread date
    ledger.apply_user_edits(db, before, after, remember=False)
    sync(db, settings)
    grocery = book(google, "Grocery")
    assert [r[2] for r in grocery.worksheet("2026-11").rows] == ["POS 4471 FRSHMRT*CTY"]
    assert [r[2] for r in grocery.worksheet("2026-10").rows] == ["GREEN GROCER CO"]
    assert grocery.titles == ["Summary", "2026-11", "2026-10"]


def test_tab_left_empty_is_deleted(google, load, db, settings):
    load("2026-11", rows=[(5, "GREEN GROCER CO", 20.0, None)])
    sync(db, settings)
    before = ledger.transactions_frame(db)
    after = before.copy()
    after["category"] = "Other"
    ledger.apply_user_edits(db, before, after, remember=False)
    sync(db, settings)
    assert book(google, "Grocery").titles == ["Summary"]
    assert book(google, "Grocery").worksheet("Summary").rows == []


def test_older_statement_later_keeps_newest_month_first(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    load("2026-09")
    load("2026-10")
    sync(db, settings)
    assert book(google, "Grocery").titles == ["Summary", "2026-11", "2026-10", "2026-09"]
    assert list(book(google, "Grocery").summary()) == ["2026-11", "2026-10", "2026-09"]


def test_huge_month_grows_the_tab_instead_of_overflowing(google, load, db, settings):
    rows = [(1 + i % 28, f"POS 4471 FRSHMRT*CTY {i:04d}", 10.0, None) for i in range(1200)]
    load("2026-11", rows=rows)
    sync(db, settings)
    assert len(book(google, "Grocery").worksheet("2026-11").rows) == 1200


def test_unshared_spreadsheet_stops_sync_and_names_the_robot(google, load, db, settings):
    load("2026-11")
    google.unshared.add("id-t")
    with pytest.raises(SyncError, match="robot@money.iam.gserviceaccount.com"):
        sync(db, settings)
    assert ledger.rows_needing_sync(db), "nothing is marked as synced after a failed sync"
    assert ledger.last_sync(db)["status"] == "failed"
    google.unshared.clear()
    sync(db, settings)
    assert ledger.rows_needing_sync(db) == []


def test_missing_robot_key_file_is_explained(load, db, settings):
    load("2026-11")
    with pytest.raises(SyncError, match="service_account.json"):
        sync(db, settings)


def test_rebuild_all_rewrites_every_tab(google, load, db, settings):
    load("2026-11")
    sync(db, settings)
    book(google, "Grocery").worksheet("2026-11").values = [["someone typed here by hand"]]
    ledger.mark_for_resync(db)
    sync(db, settings)
    assert book(google, "Grocery").worksheet("2026-11").header == sheets.HEADERS


def test_forgetting_a_statement_removes_its_rows_from_the_sheets(google, load, db, settings):
    result, _ = load("2026-11")
    sync(db, settings)
    tabs, _ = ledger.forget_statement(db, result.statement_id)
    sync(db, settings, extra_tabs=tabs)
    assert all(b.titles == ["Summary"] for b in google.books.values())


def test_check_access_reports_each_spreadsheet(google, settings):
    google.unshared.add("id-v")
    google.without_summary.add("id-i")
    results = dict((msg.split(" ")[0], ok) for ok, msg in sheets.check_access(settings))
    assert results["Grocery"] is True and results["Investments"] is True
    assert any(not ok and "Savings" in msg for ok, msg in sheets.check_access(settings))


# ── Database upgrade (migration 001 → 002) ────────────────────────────────────


def test_old_database_is_upgraded_with_a_backup_first(tmp_path):
    path = tmp_path / "data" / "ledger.db"
    path.parent.mkdir(parents=True)
    old = sqlite3.connect(path)
    old.executescript((ledger.MIGRATIONS_DIR / "001_init.sql").read_text())
    old.execute("PRAGMA user_version = 1")
    old.execute("INSERT INTO statements (file_hash, file_name) VALUES ('h', 'f.pdf')")
    old.execute("""INSERT INTO transactions (id, statement_id, row_number, txn_date, description, amount, currency,
                   category, synced_category, synced_at) VALUES ('t1', 1, 1, '2026-11-02', 'X', 5, 'USD',
                   'Grocery', 'Grocery', '2026-11-03 10:00:00')""")
    old.commit()
    old.close()

    db = ledger.connect(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert db.execute("SELECT synced_month FROM transactions").fetchone()[0] == "2026-11"
    assert list((tmp_path / "data" / "backups").glob("ledger-*.db")), "a backup is taken before upgrading"


def test_new_database_starts_at_the_latest_version(db):
    assert db.execute("PRAGMA user_version").fetchone()[0] == 2
