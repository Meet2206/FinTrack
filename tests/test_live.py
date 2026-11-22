"""Live tests against the REAL Claude API. Opt-in only (roughly $0.50 for the whole set):

    python -m pytest -m live

Skipped automatically when ANTHROPIC_API_KEY isn't set. They only use the FAKE statements
from tests/fixtures/ (regenerate with: python scripts/make_test_fixtures.py).
"""

from __future__ import annotations

import os

import pytest

from finance import categorize, pdf_tools, pipeline
from tests.scenarios import SCENARIOS, write_scenario_file

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]

FILE_SCENARIOS = [
    s
    for s in SCENARIOS
    if ("fixture" in s.tags or s.password) and s.reader == "text" and not s.max_rows_per_answer
]


@pytest.mark.parametrize("scenario", FILE_SCENARIOS, ids=[s.id for s in FILE_SCENARIOS])
def test_real_claude_reads_each_fixture(scenario, settings, tmp_path):
    """The real Claude must read every fixture so that every balance matches (no misread amounts)."""
    if scenario.saved_password:
        pdf_tools.save_password("mybank", scenario.saved_password)
    path = write_scenario_file(scenario, tmp_path)
    truth = scenario.build() if scenario.build else None
    try:
        stmt, issues, pages = pipeline.read_statement(path, settings, scenario.typed_password)
    except (pdf_tools.WrongPassword, pdf_tools.BadPdf, pipeline.NotAStatement):
        assert scenario.status == "failed", f"{scenario.id} should have been readable"
        return
    assert scenario.status != "failed", f"{scenario.id} should have been rejected"
    assert issues == [], issues
    assert len(stmt.transactions) == len(truth.transactions)
    assert [t.date for t in stmt.transactions] == [t.date for t in truth.transactions]
    assert stmt.kind == truth.kind and stmt.account_last4 == truth.account_last4
    assert stmt.currency == truth.currency


def test_real_claude_categorizes_obvious_rows(settings):
    rows = [
        {"txn_date": "2026-11-02", "description": "SALARY ACME CORP PAYROLL", "amount": -4200.00},
        {"txn_date": "2026-11-03", "description": "SUPERMARKET FRESH FOODS 22", "amount": 54.20},
        {"txn_date": "2026-11-04", "description": "UBER *TRIP HELP.UBER.COM", "amount": 18.40},
        {"txn_date": "2026-11-05", "description": "NETFLIX.COM", "amount": 15.99},
        {"txn_date": "2026-11-06", "description": "TRANSFER TO OWN SAVINGS ACCOUNT", "amount": 500.00},
        {"txn_date": "2026-11-07", "description": "VANGUARD BROKERAGE INVESTMENT", "amount": 300.00},
    ]
    labels = categorize.ask_claude(rows, [], settings.model, on_call=lambda c: None)
    assert [labels[n].category for n in range(1, 7)] == [
        "Not an expense",
        "Grocery",
        "Travel",
        "Subscriptions",
        "Savings",
        "Investments",
    ]
