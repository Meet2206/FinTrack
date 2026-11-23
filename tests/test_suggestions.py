from __future__ import annotations

import pandas as pd

from finance.suggestions import suggestions_for_frame


def test_suggestions_identify_category_subscriptions_and_repeated_merchant():
    frame = pd.DataFrame(
        [
            {"amount": 4000, "category": "Grocery", "merchant": "BigBasket"},
            {"amount": 2500, "category": "Grocery", "merchant": "BigBasket"},
            {"amount": 600, "category": "Subscriptions", "merchant": "Streaming"},
            {"amount": 550, "category": "Subscriptions", "merchant": "Music"},
            {"amount": -10000, "category": "Not an expense", "merchant": "Salary"},
        ]
    )
    result = suggestions_for_frame(frame, "INR")
    titles = [item["title"] for item in result]
    assert "Reduce Grocery by 10%" in titles
    assert "Review recurring subscriptions" in titles
    assert "Set a cap for BigBasket" in titles


def test_suggestions_are_empty_without_spending():
    frame = pd.DataFrame([{"amount": -1000, "category": "Not an expense", "merchant": "Salary"}])
    assert suggestions_for_frame(frame) == []
