"""Spot weird charges.

In plain English: after each statement, compare the new rows with your history.
This is plain arithmetic with pandas, not AI, so it's free, instant and explainable.
"""

from __future__ import annotations

import pandas as pd

from finance import ledger
from finance.config import SPENDING

DOUBLE_CHARGE_DAYS = 2
BIG_CHARGE_FACTOR = 3
TRIAL_MAX = 1.00
SPIKE_FACTOR = 1.5


def scan(db, statement_id: int, settings) -> int:
    """Look for alerts caused by one statement. Returns how many new alerts were stored."""
    df = ledger.spending_frame(db)
    if df.empty:
        return 0
    new = df[df.statement_id == statement_id]
    if new.empty:
        return 0
    found = (
        _per_transaction(df, new, settings.review.large_charge)
        + _subscriptions(df, new, settings.review.large_charge)
        + _category_spikes(db, new)
    )
    return ledger.save_alerts(db, found)


def _per_transaction(df: pd.DataFrame, new: pd.DataFrame, large_charge: float) -> list[tuple]:
    found = []
    for t in new.itertuples(index=False):
        same = df[df.shop == t.shop]
        earlier = same[same.txn_date < t.txn_date]
        if t.category in SPENDING:
            if earlier.empty and t.amount >= large_charge:
                found.append(
                    (
                        t.id,
                        "new_merchant",
                        f"First charge from {t.shop}: {t.amount:,.2f}",
                        f"new_merchant:{t.id}",
                    )
                )
            elif len(earlier) >= 3 and t.amount > BIG_CHARGE_FACTOR * earlier.amount.median():
                found.append(
                    (
                        t.id,
                        "big_charge",
                        f"{t.shop}: {t.amount:,.2f} (usually about {earlier.amount.median():,.2f})",
                        f"big_charge:{t.shop.lower()}:{t.txn_date:%Y-%m-%d}",  # once per shop per day
                    )
                )

        twins = same[
            (same.id != t.id)
            & ((same.amount - t.amount).abs() < 0.005)
            & ((same.txn_date - t.txn_date).abs() <= pd.Timedelta(days=DOUBLE_CHARGE_DAYS))
        ]
        if not twins.empty:
            pair = "|".join(sorted([t.id, twins.iloc[0].id]))
            found.append(
                (
                    t.id,
                    "double_charge",
                    f"{t.shop} charged {t.amount:,.2f} twice within {DOUBLE_CHARGE_DAYS} days "
                    f"({t.txn_date:%d %b}). Double charge?",
                    f"double_charge:{pair}",
                )
            )

        if t.amount > TRIAL_MAX:
            days_before = (t.txn_date - earlier.txn_date).dt.days
            trial = earlier[(earlier.amount <= TRIAL_MAX) & days_before.between(7, 30)]
            if not trial.empty:
                first = trial.iloc[-1]
                found.append(
                    (
                        t.id,
                        "trial_converted",
                        f"{t.shop}: {first.amount:,.2f} trial, then {t.amount:,.2f} "
                        f"{(t.txn_date - first.txn_date).days} days later",
                        f"trial_converted:{t.id}",
                    )
                )
    return found


def recurring(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly charges: a spending shop charged 3+ times, about a month apart (26–35 days),
    for a steady amount (the two charges before the latest within 10% of each other;
    the latest may differ, which is how a price increase shows up)."""
    rows = []
    spending = df[df.category.isin(SPENDING)]
    for shop, g in spending.sort_values("txn_date").groupby("shop"):
        if len(g) < 3:
            continue
        gaps = g.txn_date.diff().dt.days.dropna()
        if not gaps.tail(2).between(26, 35).all():
            continue
        a, b = g.amount.iloc[-3], g.amount.iloc[-2]
        if abs(a - b) > 0.10 * max(a, b):
            continue
        last, prev = g.iloc[-1], g.iloc[-2]
        rows.append(
            {
                "shop": shop,
                "category": last.category,
                "amount": last.amount,
                "previous": prev.amount,
                "last_charged": last.txn_date.date(),
                "last_id": last.id,
                "last_statement": last.statement_id,
            }
        )
    return pd.DataFrame(
        rows, columns=["shop", "category", "amount", "previous", "last_charged", "last_id", "last_statement"]
    )


def _subscriptions(df: pd.DataFrame, new: pd.DataFrame, large_charge: float) -> list[tuple]:
    found = []
    subs = recurring(df[df.shop.isin(set(new.shop))])
    for s in subs.itertuples(index=False):
        # Known subscriptions need no alert; big monthly payments (rent, loans) aren't forgotten ones.
        if s.category != "Subscriptions" and s.previous <= large_charge:
            found.append(
                (
                    None,
                    "new_subscription",
                    f"{s.shop} charges you every month (about {s.previous:,.2f}). "
                    "A subscription you forgot about?",
                    f"new_subscription:{s.shop.lower()}",
                )
            )
        if s.last_id in set(new.id) and s.amount > s.previous * 1.02:
            found.append(
                (
                    s.last_id,
                    "price_increase",
                    f"{s.shop} went from {s.previous:,.2f} to {s.amount:,.2f}",
                    f"price_increase:{s.last_id}",
                )
            )
    return found


def _category_spikes(db, new: pd.DataFrame) -> list[tuple]:
    totals = ledger.category_totals(db)
    found = []
    for month in sorted(set(new.txn_date.dt.strftime("%Y-%m"))):
        period = pd.Period(month, "M")
        previous = [str(period - i) for i in (1, 2, 3)]
        for category in SPENDING:
            current = totals[(totals.month == month) & (totals.category == category)].total.sum()
            history = totals[totals.month.isin(previous) & (totals.category == category)]
            if len(history) < 3 or current <= 0:
                continue
            average = history.total.mean()
            if average > 0 and current > SPIKE_FACTOR * average:
                found.append(
                    (
                        None,
                        "category_spike",
                        f"{category} in {month}: {current:,.2f}, {current / average:.1f}× your "
                        f"3-month average ({average:,.2f})",
                        f"category_spike:{category}:{month}",
                    )
                )
    return found
