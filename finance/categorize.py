"""Sort transactions into categories.

In plain English: for each transaction we try three things, in order:
1. Saved rule: "we've seen this shop before" (from your fixes or a confident AI answer).
2. Keyword: a word from config.yaml appears in the description (e.g. "netflix").
3. Ask Claude: about 100 unknown rows per request, with your past corrections as examples.
Claude also says how sure it is; unsure answers go to your review queue.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from itertools import batched
from typing import Literal

from pydantic import BaseModel, Field

from finance import costs, ledger, prompts
from finance.config import Category, Settings
from finance.extract import claude_parse
from finance.ids import merchant_key, pretty_merchant

# The instructions Claude follows: edit them in prompts/app/categorize-transactions.md
CATEGORIZE_PROMPT = prompts.load("categorize-transactions")


class Labeled(BaseModel):
    n: int = Field(description="The row number given in the input")
    merchant: str = Field(description="Short, clean shop name")
    category: Category
    confidence: Literal["high", "medium", "low"]


class Labels(BaseModel):
    items: list[Labeled]


def keyword_category(description: str, keywords: dict[str, list[str]]) -> str | None:
    """First category whose keyword appears as a whole word ('sip' won't match 'gossip')."""
    for category, words in keywords.items():
        for word in words:
            if word and re.search(rf"\b{re.escape(word)}\b", description, re.IGNORECASE):
                return category
    return None


def categorize_statement(
    db, settings: Settings, statement_id: int, on_call: Callable[[costs.AICall], None]
) -> dict[str, int]:
    """Categorize this statement's rows, plus any left uncategorized by an earlier failed attempt.
    Returns how many rows each method sorted."""
    rows = ledger.uncategorized(db)
    rules = ledger.merchant_rules(db)  # {merchant_key: (merchant, category)}
    updates, for_ai, used_rules = [], [], []
    tally = {"rule": 0, "keyword": 0, "ai": 0}

    for r in rows:
        key = merchant_key(r["description"])
        if key in rules:  # 1. saved rule
            merchant, category = rules[key]
            updates.append(
                dict(id=r["id"], merchant=merchant, category=category, confidence="high", source="rule")
            )
            used_rules.append(key)
            tally["rule"] += 1
        elif category := keyword_category(r["description"], settings.keywords):  # 2. keyword
            updates.append(
                dict(
                    id=r["id"],
                    merchant=pretty_merchant(r["description"]),
                    category=category,
                    confidence="high",
                    source="keyword",
                )
            )
            tally["keyword"] += 1
        elif getattr(settings, "offline_mode", False):
            category = local_category(r["description"], settings.keywords)
            updates.append(
                dict(
                    id=r["id"],
                    merchant=pretty_merchant(r["description"]),
                    category=category,
                    confidence="medium" if category == "Other" else "high",
                    source="keyword",
                )
            )
            tally["keyword"] += 1
        else:
            for_ai.append(r)  # 3. ask Claude

    corrections = ledger.recent_corrections(db, limit=40)
    for batch in batched(for_ai, settings.categorize_batch_size):
        labels = ask_claude(list(batch), corrections, settings.model, on_call)
        for n, r in enumerate(batch, start=1):
            label = labels.get(n)
            tally["ai"] += 1
            if label is None:  # Claude skipped this row: send it to review
                updates.append(
                    dict(
                        id=r["id"],
                        merchant=pretty_merchant(r["description"]),
                        category="Other",
                        confidence="low",
                        source="ai",
                    )
                )
                continue
            updates.append(
                dict(
                    id=r["id"],
                    merchant=label.merchant,
                    category=label.category,
                    confidence=label.confidence,
                    source="ai",
                )
            )
            if label.confidence == "high":  # learn it, so next month it's free
                ledger.save_rule(
                    db, merchant_key(r["description"]), label.merchant, label.category, "ai", commit=False
                )

    ledger.apply_categories(db, updates, review_if=settings.review.review_if_confidence)
    if used_rules:
        ledger.bump_rules(db, used_rules)
    return tally


def local_category(description: str, keywords: dict[str, list[str]]) -> str:
    """Conservative, explainable categorization for offline use."""
    direct = keyword_category(description, keywords)
    if direct:
        return direct
    text = description.lower()
    if re.search(r"salary|payroll|interest|cash deposit|credit|refund|transfer from", text):
        return "Not an expense"
    if re.search(r"uber|ola|irctc|rail|metro|air|flight|hotel|fuel|parking|toll|atm", text):
        return "Travel"
    if re.search(r"grocery|bigbasket|dmart|mart|supermarket|fresh greens", text):
        return "Grocery"
    if re.search(r"sip|mutual fund|broker|etf|stock", text):
        return "Investments"
    if re.search(r"savings|fixed deposit|recurring deposit", text):
        return "Savings"
    return "Other"


def ask_claude(
    batch, corrections: list[str], model: str, on_call: Callable[[costs.AICall], None]
) -> dict[int, Labeled]:
    lines = "\n".join(
        f"{n} | {r['txn_date']} | {r['amount']:.2f} | {r['description']}"
        for n, r in enumerate(batch, start=1)
    )
    system = CATEGORIZE_PROMPT
    if corrections:
        system += (
            "\n\nThe user corrected these before. Make the same choices for similar rows:\n"
            + "\n".join(corrections)
        )
    started = time.monotonic()
    resp = claude_parse(
        model=model,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": f"n | date | amount | description\n{lines}"}],
        output_format=Labels,
    )
    on_call(costs.from_response("categorize", model, resp, started))
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"Categorization stopped early: {resp.stop_reason}")
    return {label.n: label for label in resp.parsed_output.items}
