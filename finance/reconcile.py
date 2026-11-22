"""Check the math, like counting the till at the end of the day.

In plain English: start with the opening balance, apply each row (minus money out,
plus money in), and after every row compare against the balance the bank printed.
If they disagree, we know exactly which row is wrong.

Credit cards work the other way round: the balance is what you owe, so spending
makes it go up.
"""

from __future__ import annotations

from datetime import date, timedelta

TOLERANCE = 0.01


def check(opening, closing, txns, is_card: bool = False, tolerance: float = TOLERANCE) -> list[str]:
    """Return a list of problems. An empty list means the statement is verified."""
    sign = -1 if is_card else 1
    if opening is None and txns and txns[0].balance is not None:
        first = txns[0]  # no opening balance printed: work it out from row 1
        opening = round(first.balance - sign * ((first.credit or 0) - (first.debit or 0)), 2)
    if opening is None:
        return ["No opening or running balance printed, so the statement can't be verified"]

    issues: list[str] = []
    balance = opening
    for row_number, t in enumerate(txns, start=1):
        balance = round(balance + sign * ((t.credit or 0) - (t.debit or 0)), 2)
        if t.balance is not None and abs(balance - t.balance) > tolerance:
            issues.append(
                f"Row {row_number} ({t.date}, '{t.description[:30]}'): "
                f"expected {balance:,.2f}, statement shows {t.balance:,.2f}"
            )
            balance = t.balance  # resync, so one bad row doesn't flag every row after it
    if closing is not None and abs(balance - closing) > tolerance:
        issues.append(f"Closing balance: worked out {balance:,.2f}, statement shows {closing:,.2f}")
    return issues


DATE_SLACK_DAYS = 7  # card statements can include purchases made a few days before the period


def check_dates(
    txns, period_start: str | None, period_end: str | None, slack_days: int = DATE_SLACK_DAYS
) -> list[str]:
    """Balances can't reveal a misread DATE, so check every date is real and inside the
    statement period (give or take a week). A row outside it would land in the wrong month tab."""
    issues: list[str] = []
    try:
        start = date.fromisoformat(period_start) - timedelta(days=slack_days) if period_start else None
        end = date.fromisoformat(period_end) + timedelta(days=slack_days) if period_end else None
    except ValueError:
        start = end = None
    for row_number, t in enumerate(txns, start=1):
        try:
            d = date.fromisoformat(t.date)
        except ValueError:
            issues.append(f"Row {row_number} ('{t.description[:30]}'): '{t.date}' isn't a valid date")
            continue
        if (start and d < start) or (end and d > end):
            issues.append(
                f"Row {row_number} ('{t.description[:30]}'): date {t.date} is outside the "
                f"statement period ({period_start} to {period_end})"
            )
    return issues
