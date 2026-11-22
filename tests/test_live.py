"""Live tests against the REAL Claude API. Opt-in only (they cost a few cents):

    python -m pytest -m live

Skipped automatically when ANTHROPIC_API_KEY isn't set. They use a FAKE statement,
never real data.
"""

from __future__ import annotations

import os

import pytest

from finance import categorize, pipeline
from finance.demo import build_statement, write_pdf

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY not set"),
]


def test_claude_reads_a_fake_statement_perfectly(settings, tmp_path):
    truth = build_statement("2026-11")
    path = write_pdf(truth, tmp_path / "fake.pdf", "LIVE-1", rows_per_page=16)
    calls = []
    stmt, issues, pages = pipeline.read_statement(path, settings, on_call=calls.append)
    assert issues == [], issues  # every balance matches, so every amount was read right
    assert len(stmt.transactions) == len(truth.transactions)
    assert stmt.account_last4 == "1234" and stmt.opening_balance == truth.opening_balance
    assert all(c.purpose == "extract" for c in calls) and len(calls) == -(-pages // settings.pages_per_chunk)


def test_claude_categorizes_obvious_rows(settings):
    rows = [
        {"txn_date": "2026-11-02", "description": "SALARY ACME CORP PAYROLL", "amount": -4200.00},
        {"txn_date": "2026-11-03", "description": "SUPERMARKET FRESH FOODS 22", "amount": 54.20},
        {"txn_date": "2026-11-04", "description": "UBER *TRIP HELP.UBER.COM", "amount": 18.40},
        {"txn_date": "2026-11-05", "description": "NETFLIX.COM", "amount": 15.99},
    ]
    labels = categorize.ask_claude(rows, [], settings.model, on_call=lambda c: None)
    assert [labels[n].category for n in (1, 2, 3, 4)] == [
        "Not an expense",
        "Grocery",
        "Travel",
        "Subscriptions",
    ]
