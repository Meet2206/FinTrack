"""The monthly summary message, optionally sent to Telegram.

In plain English: a short text like "You spent 2,340 in November (▲ 8%)…" built
from the ledger, ready to read in the terminal or receive on your phone.
"""

from __future__ import annotations

import json
import os
import urllib.request

import pandas as pd

from finance import ledger
from finance.config import EMOJI, SET_ASIDE, SPENDING


class SendError(Exception):
    pass


def latest_month(db) -> str | None:
    months = ledger.months(db)
    return months[0] if months else None


def monthly_summary(db, month: str) -> str:
    overview = ledger.monthly_overview(db).set_index("month")
    if month not in overview.index:
        return f"No reviewed transactions for {month} yet."
    row = overview.loc[month]
    previous = str(pd.Period(month, "M") - 1)
    title = pd.Period(month, "M").strftime("%B %Y")

    lines = [f"💸 {title}"]
    change = ""
    if previous in overview.index and overview.loc[previous, "spending"] > 0:
        pct = (row.spending / overview.loc[previous, "spending"] - 1) * 100
        change = f" ({'▲' if pct >= 0 else '▼'} {abs(pct):.0f}% vs {pd.Period(previous, 'M'):%b})"
    lines.append(f"Spent {row.spending:,.2f}{change}")
    rate = f" · Savings rate {row.set_aside / row.money_in:.0%}" if row.money_in > 0 else ""
    lines.append(f"Set aside {row.set_aside:,.2f}{rate}")

    totals = ledger.category_totals(db)
    totals = totals[totals.month == month].set_index("category").total
    spend = " · ".join(f"{EMOJI[c]} {c} {totals[c]:,.2f}" for c in SPENDING if c in totals)
    aside = " · ".join(f"{EMOJI[c]} {c} {totals[c]:,.2f}" for c in SET_ASIDE if c in totals)
    lines += [line for line in (spend, aside) if line]

    shops = ledger.top_shops(db, month, limit=3)
    if not shops.empty:
        lines.append("Top shops: " + ", ".join(f"{s.shop} {s.total:,.2f}" for s in shops.itertuples()))
    open_alerts = len(ledger.open_alerts(db))
    if open_alerts:
        lines.append(f"⚠️ {open_alerts} open alert(s). Check the dashboard.")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise SendError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env first (see .env.example).")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise SendError(f"Telegram answered {response.status}")
    except OSError as e:
        raise SendError(f"Couldn't reach Telegram: {e}") from e
