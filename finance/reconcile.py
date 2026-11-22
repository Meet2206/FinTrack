"""Check the math, like counting the till at the end of the day.

In plain English: start with the opening balance, apply each row (minus money out,
plus money in), and after every row compare against the balance the bank printed.
If they disagree, we know exactly which row is wrong.

Credit cards work the other way round: the balance is what you owe, so spending
makes it go up.
"""

from __future__ import annotations

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
