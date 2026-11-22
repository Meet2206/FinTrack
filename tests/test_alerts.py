"""Alerts: every rule tested on both sides of its threshold."""

from __future__ import annotations

import pytest

from finance import alerts, ledger, pipeline
from finance.demo import build_statement, fake_claude, write_pdf


@pytest.fixture
def history(settings, db, tmp_path):
    """Process several months in order; return the open alerts afterwards."""
    counter = iter(range(1, 1000))

    def _history(plan: dict[str, list[tuple]]):
        opening, last = 20_000.0, None
        for month, rows in plan.items():
            stmt = build_statement(month, opening=opening, rows=rows)
            number = f"A-{next(counter)}"
            with fake_claude({number: stmt}):
                last = pipeline.process_statement(
                    write_pdf(stmt, tmp_path / f"{number}.pdf", number), settings, db
                )
            opening = stmt.closing_balance
        _history.last = last
        return ledger.open_alerts(db)

    return _history


def kinds(df) -> list[str]:
    return list(df.kind)


CAB = "CITY CABS 0091"
MART = "POS 4471 FRSHMRT*CTY"


@pytest.mark.parametrize(
    "second_day, expected",
    [(12, True), (14, True), (15, False)],
    ids=["same-day", "2-days-later", "3-days-later"],
)
def test_double_charge_within_2_days(history, second_day, expected):
    found = history({"2026-11": [(12, CAB, 64.0, None), (second_day, CAB, 64.0, None)]})
    assert ("double_charge" in kinds(found)) is expected


def test_double_charge_needs_the_same_amount(history):
    assert "double_charge" not in kinds(history({"2026-11": [(12, CAB, 64.0, None), (12, CAB, 46.0, None)]}))


def test_one_alert_per_double_charge_pair(history):
    found = history({"2026-11": [(12, CAB, 64.0, None), (12, CAB, 64.0, None)]})
    assert kinds(found).count("double_charge") == 1


@pytest.mark.parametrize("amount, expected", [(151.0, True), (150.0, False)], ids=["over-3x", "exactly-3x"])
def test_big_charge_is_more_than_3x_the_usual(history, amount, expected):
    usual = [(2, MART, 50.0, None), (9, MART, 50.0, None), (16, MART, 50.0, None)]
    found = history({"2026-11": usual + [(23, MART, amount, None)]})
    assert ("big_charge" in kinds(found)) is expected


def test_big_charge_needs_3_earlier_charges(history):
    found = history({"2026-11": [(2, MART, 50.0, None), (9, MART, 50.0, None), (23, MART, 900.0, None)]})
    assert "big_charge" not in kinds(found)


@pytest.mark.parametrize(
    "amount, expected", [(200.0, True), (199.99, False)], ids=["at-threshold", "just-below"]
)
def test_big_first_charge_from_a_new_shop(history, amount, expected):
    found = history({"2026-11": [(5, "MERCHANT 8812 LLC", amount, None)]})
    assert ("new_merchant" in kinds(found)) is expected


def test_moving_money_to_savings_is_not_a_new_merchant_alert(history):
    assert kinds(history({"2026-11": [(5, "TRF TO SAVINGS A/C 5678", 5000.0, None)]})) == []


@pytest.mark.parametrize(
    "paid_day, trial_amount, expected",
    [(17, 1.00, True), (16, 1.00, False), (40, 1.00, True), (42, 1.00, False), (17, 1.50, False)],
    ids=["7-days", "6-days-too-soon", "30-days", "32-days-too-late", "not-a-trial-amount"],
)
def test_free_trial_turned_paid(history, paid_day, trial_amount, expected):
    plan = {"2026-09": [(10, "CLOUDBOX STORAGE TRIAL", trial_amount, None)]}
    if paid_day <= 30:
        plan["2026-09"].append((paid_day, "CLOUDBOX STORAGE", 9.99, None))
    else:
        plan["2026-10"] = [(paid_day - 30, "CLOUDBOX STORAGE", 9.99, None)]
    assert ("trial_converted" in kinds(history(plan))) is expected


def monthly(description, amounts, day=3):
    return {
        f"2026-{m:02d}": [(day, description, a, None)]
        for m, a in zip(range(8, 8 + len(amounts)), amounts, strict=True)
    }


@pytest.mark.parametrize(
    "amounts, expected",
    [([12.99, 12.99, 15.99], True), ([12.99, 12.99, 13.10], False)],
    ids=["23%-rise", "under-2%"],
)
def test_subscription_price_increase(history, amounts, expected):
    found = history(monthly("STREAMFLIX.COM 800-555", amounts))
    assert ("price_increase" in kinds(found)) is expected


def test_forgotten_subscription_is_spotted(history):
    found = history(monthly("GYMCO MEMBERSHIP 7781", [29.99, 29.99, 29.99]))
    assert any("GymCo charges you every month" in m for m in found.message)


@pytest.mark.parametrize(
    "description, amounts",
    [
        ("RENT TRANSFER LANDLORD J SMITH", [1400.0] * 3),  # big monthly payment: not a forgotten subscription
        ("SHELL FUEL STATION 22", [41.0, 58.0, 47.0]),  # monthly but the amount varies
        ("STREAMFLIX.COM 800-555", [12.99] * 3),  # already filed under Subscriptions
        ("TRF TO SAVINGS A/C 5678", [500.0] * 3),  # saving, not spending
        ("GYMCO MEMBERSHIP 7781", [29.99] * 2),
    ],  # only 2 months: too early to tell
    ids=["rent", "varying-fuel", "known-subscription", "savings", "only-2-months"],
)
def test_no_forgotten_subscription_false_alarms(history, description, amounts):
    assert "new_subscription" not in kinds(history(monthly(description, amounts)))


@pytest.mark.parametrize("months_of_history, expected", [(3, True), (2, False)], ids=["3-months", "2-months"])
def test_category_spike(history, months_of_history, expected):
    plan = {f"2026-{m:02d}": [(5, CAB, 100.0, None)] for m in range(10 - months_of_history, 10)}
    plan["2026-10"] = [(5, CAB, 100.0, None), (9, "SHELL FUEL STATION 22", 200.0, None)]  # Travel 300 vs ~100
    found = history(plan)
    assert ("category_spike" in kinds(found)) is expected


def test_alerts_are_never_stored_twice(history, db, settings):
    history({"2026-11": [(12, CAB, 64.0, None), (12, CAB, 64.0, None)]})
    assert alerts.scan(db, history.last.statement_id, settings) == 0


def test_dismissed_alerts_disappear(history, db):
    found = history({"2026-11": [(12, CAB, 64.0, None), (12, CAB, 64.0, None)]})
    ledger.dismiss_alert(db, int(found.id.iloc[0]))
    assert ledger.open_alerts(db).empty
