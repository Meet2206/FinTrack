"""Local, explainable money-saving suggestions.

These are heuristics, not financial advice. They deliberately use only the
transactions already parsed into the local ledger; no API or account data is
needed.
"""

from __future__ import annotations

import pandas as pd

from finance.config import SET_ASIDE, SPENDING


def _money(value: float) -> str:
    return f"{value:,.2f}"


def suggestions_for_frame(frame: pd.DataFrame, currency: str = "USD") -> list[dict[str, str]]:
    """Return a short list of actionable, evidence-backed suggestions.

    ``amount > 0`` is money out in Fintrack and ``amount < 0`` is money in.
    The suggested amount is intentionally conservative and described as an
    opportunity, not a guaranteed saving.
    """
    if frame.empty or "amount" not in frame:
        return []

    rows = frame.copy()
    rows["amount"] = pd.to_numeric(rows["amount"], errors="coerce")
    rows = rows[rows.amount.notna()]
    spending = rows[(rows.amount > 0) & rows.category.isin(SPENDING)].copy()
    income = rows[rows.amount < 0]
    if spending.empty:
        return []

    suggestions: list[dict[str, str]] = []
    total = float(spending.amount.sum())
    by_category = spending.groupby("category").amount.sum().sort_values(ascending=False)
    top_category = str(by_category.index[0])
    top_total = float(by_category.iloc[0])
    if total and top_total / total >= 0.25:
        opportunity = round(top_total * 0.10, 2)
        suggestions.append(
            {
                "title": f"Reduce {top_category} by 10%",
                "text": (
                    f"{top_category} is your largest spending area at {currency} {_money(top_total)} "
                    f"({top_total / total:.0%} of spending). A 10% trim could free about "
                    f"{currency} {_money(opportunity)} in this statement period."
                ),
            }
        )

    subscriptions = spending[spending.category == "Subscriptions"]
    if not subscriptions.empty:
        subscription_total = float(subscriptions.amount.sum())
        if len(subscriptions) >= 2 or subscription_total >= 500:
            opportunity = round(subscription_total * 0.15, 2)
            suggestions.append(
                {
                    "title": "Review recurring subscriptions",
                    "text": (
                        f"You paid {currency} {_money(subscription_total)} across "
                        f"{len(subscriptions)} subscription charge(s). Canceling or downgrading one "
                        f"could save roughly {currency} {_money(opportunity)} (15% estimate)."
                    ),
                }
            )

    merchant_col = "merchant" if "merchant" in spending else "description"
    spending[merchant_col] = spending[merchant_col].fillna("").replace("", "Unknown merchant")
    merchants = spending.groupby(merchant_col).amount.agg(["sum", "count"]).sort_values("sum", ascending=False)
    repeated = merchants[(merchants["count"] >= 2) & (merchants["sum"] >= 1000)]
    if not repeated.empty:
        merchant = str(repeated.index[0])
        merchant_total = float(repeated.iloc[0]["sum"])
        suggestions.append(
            {
                "title": f"Set a cap for {merchant}",
                "text": (
                    f"{merchant} appears {int(repeated.iloc[0]['count'])} times for "
                    f"{currency} {_money(merchant_total)}. Consider a monthly cap and a quick "
                    "check before the next charge."
                ),
            }
        )

    if len(income) and rows[rows.category.isin(SET_ASIDE)].empty:
        opportunity = round(float((-income.amount).sum()) * 0.10, 2)
        if opportunity > 0:
            suggestions.append(
                {
                    "title": "Create a savings transfer",
                    "text": (
                        f"No Savings or Investments transfers were detected. Setting aside 10% of "
                        f"the {currency} {_money(float((-income.amount).sum()))} received here would be "
                        f"about {currency} {_money(opportunity)}."
                    ),
                }
            )

    return suggestions[:4]
