"""Statement scenarios: one test per real-life situation (see tests/scenarios.py and TESTING.md).

Every scenario also checks the app's safety rules:
  • a statement that isn't fully verified can never reach Google Sheets
  • a failed statement saves no transactions and records a plain-English reason
"""

from __future__ import annotations

import shutil

import pytest

from finance import ledger, pdf_tools, pipeline
from finance.demo import build_statement, fake_claude, write_pdf
from tests.scenarios import SCENARIOS, SMALL, ai_for, reading_claude, write_scenario_file


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_statement_scenario(scenario, settings, db, tmp_path):
    if scenario.saved_password:
        pdf_tools.save_password("mybank", scenario.saved_password)
    path = write_scenario_file(scenario, tmp_path)
    truth = scenario.build() if scenario.build else None

    with ai_for(scenario, truth):
        result = pipeline.process_statement(path, settings, db, scenario.typed_password)

    assert result.status == scenario.status, result.message
    if scenario.message:
        assert scenario.message in result.message, result.message
    if scenario.issue:
        assert result.issues and scenario.issue in result.issues[0], result.issues
    if scenario.check:
        scenario.check(db, result, truth)

    # Safety rules that hold in every scenario
    statement = ledger.get_statement(db, result.statement_id)
    assert statement["status"] == scenario.status
    if scenario.status not in ("ready", "synced"):
        assert ledger.rows_needing_sync(db) == [], "unverified data must never be eligible for Google Sheets"
    if scenario.status == "failed":
        assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
        assert statement["error"], "a failed statement explains why"


# ── Situations that involve more than one upload ──────────────────────────────


def _process(path, settings, db, truth, number):
    with fake_claude({number: truth}):
        return pipeline.process_statement(path, settings, db)


def count(db) -> int:
    return db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]


def test_same_file_uploaded_twice_adds_nothing(settings, db, tmp_path):
    truth = build_statement("2026-11")
    path = write_pdf(truth, tmp_path / "nov.pdf", "SEQ-1")
    _process(path, settings, db, truth, "SEQ-1")
    again = _process(path, settings, db, truth, "SEQ-1")
    assert "Already processed" in again.message and count(db) == len(truth.transactions)


def test_renamed_copy_is_recognized_as_the_same_file(settings, db, tmp_path):
    truth = build_statement("2026-11")
    path = write_pdf(truth, tmp_path / "nov.pdf", "SEQ-1")
    first = _process(path, settings, db, truth, "SEQ-1")
    renamed = tmp_path / "statement (1) copy.pdf"
    shutil.copyfile(path, renamed)
    again = _process(renamed, settings, db, truth, "SEQ-1")
    assert again.statement_id == first.statement_id and "Already processed" in again.message


def test_overlapping_statements_share_rows_without_duplicates(settings, db, tmp_path):
    rows = sorted(SMALL + [(12, "GREEN GROCER CO", 23.75, None), (14, "METRO CARD TOP UP", 30.0, None)])
    first = build_statement("2026-11", rows=rows[:6])
    second = build_statement(
        "2026-11", opening=first.transactions[2].balance, rows=rows[3:] + [(20, "HOTEL BAYVIEW", 180.0, None)]
    )
    _process(write_pdf(first, tmp_path / "a.pdf", "A"), settings, db, first, "A")
    result = _process(write_pdf(second, tmp_path / "b.pdf", "B"), settings, db, second, "B")
    assert result.status == "ready" and result.new_rows == 3
    assert "already known" in result.message
    assert count(db) == 9


def test_two_accounts_with_the_same_shop_are_kept_apart(settings, db, tmp_path):
    rows = [(2, "POS 4471 FRSHMRT*CTY", 54.20, None)]
    bank = build_statement("2026-11", rows=rows, last4="1234")
    other = build_statement("2026-11", rows=rows, last4="5555")
    _process(write_pdf(bank, tmp_path / "a.pdf", "A"), settings, db, bank, "A")
    _process(write_pdf(other, tmp_path / "b.pdf", "B"), settings, db, other, "B")
    assert count(db) == 2
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 2


def test_card_bill_paid_from_bank_is_not_counted_twice(settings, db, tmp_path):
    """Bank statement pays the card bill; card statement holds the purchases. Spending counts them once."""
    bank = build_statement(
        "2026-11",
        rows=[
            (1, "SALARY ACME CORP PAYROLL", None, 3000.0),
            (25, "CREDIT CARD PAYMENT THANK YOU", 289.0, None),
        ],
    )
    card = build_statement(
        "2026-11", opening=0.0, last4="9876", kind="card", rows=[(4, "AIRWAYS 0572 FLIGHT", 289.0, None)]
    )
    _process(write_pdf(bank, tmp_path / "bank.pdf", "BANK"), settings, db, bank, "BANK")
    _process(write_pdf(card, tmp_path / "card.pdf", "CARD"), settings, db, card, "CARD")
    overview = ledger.monthly_overview(db).set_index("month").loc["2026-11"]
    assert overview.spending == 289.0, "the flight counts once, the card bill payment not at all"


def test_failed_statement_can_be_retried_after_fixing_the_cause(settings, db, tmp_path):
    truth = build_statement("2026-11", rows=SMALL)
    path = write_pdf(truth, tmp_path / "locked.pdf", "LOCK", password="pw")
    with reading_claude():
        failed = pipeline.process_statement(path, settings, db)
        fixed = pipeline.process_statement(path, settings, db, "pw")
    assert (failed.status, fixed.status) == ("failed", "ready")
    assert fixed.statement_id == failed.statement_id
    assert ledger.get_statement(db, fixed.statement_id)["error"] is None
