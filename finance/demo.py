"""Fake statements and a pretend Claude, for tests and a no-key demo.

In plain English: real statements never go anywhere near tests. This file draws
realistic-looking fake bank statements (PDFs), and provides a stand-in for Claude
that "reads" them perfectly and sorts rows with simple keyword rules. The demo
lets you click around the app before setting up any keys.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from finance import categorize, extract
from finance.costs import AICall
from finance.extract import StatementChunk, Txn

BANK = "EXAMPLE BANK"

# (day, description, money out, money in). Some rows change per month (see month_rows).
BASE_ROWS = [
    (1, "SALARY ACME CORP PAYROLL", None, 4200.00),
    (2, "POS 4471 FRSHMRT*CTY", 54.20, None),
    (3, "STREAMFLIX.COM 800-555", 12.99, None),
    (3, "CITY CABS 0091", 18.40, None),
    (4, "RENT TRANSFER LANDLORD J SMITH", 1400.00, None),
    (5, "GREEN GROCER CO", 23.75, None),
    (6, "SHELL FUEL STATION 22", 48.10, None),
    (7, "TRF TO SAVINGS A/C 5678", 500.00, None),
    (8, "BRIGHTVEST BROKERAGE SIP", 300.00, None),
    (9, "CAFE LUNA 12", 6.80, None),
    (10, "SPOTIFY P2C3", 10.99, None),
    (11, "POS 4471 FRSHMRT*CTY", 61.35, None),
    (13, "PIZZA PALACE DELIVERY", 27.50, None),
    (14, "METRO CARD TOP UP", 30.00, None),
    (15, "REFUND FRSHMRT*CTY", None, 8.99),
    (18, "POS 4471 FRSHMRT*CTY", 47.80, None),
    (19, "PHONE CO MONTHLY PLAN", 35.00, None),
    (20, "ATM WITHDRAWAL 0042", 100.00, None),
    (21, "GREEN GROCER CO", 31.20, None),
    (22, "INTEREST CREDIT", None, 3.12),
    (23, "PARKING GARAGE 7", 12.00, None),
    (24, "PIZZA PALACE DELIVERY", 31.00, None),
    (25, "FIXED DEPOSIT BOOKING", 250.00, None),
    (27, "POS 4471 FRSHMRT*CTY", 58.40, None),
    (28, "CREDIT CARD PAYMENT THANK YOU", 620.00, None),
]


FIXED_PRICE = (
    "SALARY",
    "STREAMFLIX",
    "RENT",
    "TRF TO SAVINGS",
    "BRIGHTVEST",
    "SPOTIFY",
    "REFUND",
    "PHONE CO",
    "INTEREST",
    "FIXED DEPOSIT",
    "CREDIT CARD",
)


def month_rows(month: str) -> list[tuple]:
    """Base rows plus a few month-specific ones, so the demo triggers real alerts.
    Everyday spending (groceries, fuel, cabs…) varies a little from month to month."""
    factor = {9: 0.85, 10: 1.0, 11: 1.15, 12: 0.95}.get(int(month[-2:]), 1.0)
    rows = [
        r if r[1].startswith(FIXED_PRICE) or r[2] is None else (r[0], r[1], round(r[2] * factor, 2), None)
        for r in BASE_ROWS
    ]
    rows.append((12, "GYMCO MEMBERSHIP 7781", 29.99, None))  # the forgotten subscription
    if month.endswith("-09"):
        rows.append((16, "CLOUDBOX STORAGE TRIAL", 1.00, None))
    if month.endswith("-10"):
        rows.append((10, "CLOUDBOX STORAGE", 9.99, None))  # trial turned paid
        rows.append((17, "AIRWAYS 0572 FLIGHT", 289.00, None))
    if month.endswith("-11"):
        rows = [r if not r[1].startswith("STREAMFLIX") else (3, r[1], 15.99, None) for r in rows]  # price up
        rows.append((10, "CLOUDBOX STORAGE", 9.99, None))
        rows.append((12, "CITY CABS 0091", 64.00, None))
        rows.append((12, "CITY CABS 0091", 64.00, None))  # double charge
        rows.append((26, "HOTEL BAYVIEW", 180.00, None))
        rows.append((16, "POS 4471 FRSHMRT*CTY", 412.00, None))  # unusually big
    return sorted(rows, key=lambda r: r[0])


def build_statement(
    month: str,
    opening: float = 2500.00,
    last4: str = "1234",
    rows: list[tuple] | None = None,
    *,
    kind: str = "bank",
    currency: str = "USD",
    bank_name: str = BANK,
    running_balance: bool = True,
    opening_printed: bool = True,
    closing_printed: bool = True,
) -> StatementChunk:
    """The 'truth' for a fake statement: what a perfect reader would extract.

    kind="card": a credit card statement, where the balance is what you owe,
    so spending makes it go UP and payments make it go down.
    """
    year, mon = map(int, month.split("-"))
    sign = -1 if kind == "card" else 1
    balance, txns = opening, []
    for day, description, out, money_in in rows if rows is not None else month_rows(month):
        balance = round(balance + sign * ((money_in or 0) - (out or 0)), 2)
        txns.append(
            Txn(
                date=f"{year:04d}-{mon:02d}-{day:02d}",
                description=description,
                debit=out,
                credit=money_in,
                balance=balance if running_balance else None,
            )
        )
    last_day = 30 if mon in (4, 6, 9, 11) else 28 if mon == 2 else 31
    return StatementChunk(
        looks_like_statement=True,
        kind=kind,
        bank_name=bank_name,
        account_last4=last4,
        currency=currency,
        period_start=f"{year:04d}-{mon:02d}-01",
        period_end=f"{year:04d}-{mon:02d}-{last_day:02d}",
        opening_balance=opening if opening_printed else None,
        closing_balance=balance if closing_printed else None,
        transactions=txns,
    )


def _money(x: float | None) -> str:
    """Blank when there's no amount in this column; 0.00 is printed (e.g. a waived fee)."""
    return "" if x is None else f"{x:,.2f}"


def _nice(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d %b %Y")


def write_pdf(
    stmt: StatementChunk, path: Path, statement_no: str, password: str | None = None, rows_per_page: int = 16
) -> Path:
    """Draw a realistic-looking statement PDF (optionally password-protected).
    Prints exactly what `stmt` says: balances that are None are simply not printed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    _, height = A4
    txns = stmt.transactions
    pages = [txns[i : i + rows_per_page] for i in range(0, len(txns), rows_per_page)] or [[]]
    carried = stmt.opening_balance
    account_label = "Card ending" if stmt.kind == "card" else "Account ending"
    for page_no, page_rows in enumerate(pages, start=1):
        y = height - 50
        c.setFont("Helvetica-Bold", 15)
        c.drawString(50, y, f"{stmt.bank_name}")
        c.setFont("Helvetica", 9)
        c.drawString(50, y - 16, f"Statement no. {statement_no}        Page {page_no} of {len(pages)}")
        c.drawString(
            50,
            y - 29,
            f"{account_label} {stmt.account_last4}    Period: {_nice(stmt.period_start)} "
            f"to {_nice(stmt.period_end)}    Currency: {stmt.currency}",
        )
        y -= 60
        c.setFont("Helvetica-Bold", 9)
        for x, title in ((50, "Date"), (125, "Description")):
            c.drawString(x, y, title)
        for x, title in ((410, "Money out"), (480, "Money in"), (555, "Balance")):
            c.drawRightString(x, y, title)
        c.line(50, y - 4, 555, y - 4)
        y -= 18
        c.setFont("Helvetica", 9)
        if page_no == 1 and stmt.opening_balance is not None:
            c.drawString(125, y, "Opening balance")
            c.drawRightString(555, y, f"{stmt.opening_balance:,.2f}")
            y -= 16
        elif page_no > 1 and carried is not None:
            c.drawString(125, y, "Balance brought forward")
            c.drawRightString(555, y, f"{carried:,.2f}")
            y -= 16
        for t in page_rows:
            c.drawString(50, y, _nice(t.date))
            c.drawString(125, y, t.description)
            c.drawRightString(410, y, _money(t.debit))
            c.drawRightString(480, y, _money(t.credit))
            if t.balance is not None:
                c.drawRightString(555, y, f"{t.balance:,.2f}")
                carried = t.balance
            y -= 16
        c.setFont("Helvetica-Bold", 9)
        if page_no == len(pages) and stmt.closing_balance is not None:
            c.drawString(125, y - 4, "Closing balance")
            c.drawRightString(555, y - 4, f"{stmt.closing_balance:,.2f}")
        elif page_no < len(pages) and carried is not None and page_rows and page_rows[-1].balance is not None:
            c.drawString(125, y - 4, "Balance carried forward")
            c.drawRightString(555, y - 4, f"{carried:,.2f}")
        c.showPage()
    c.save()

    if password:
        writer = PdfWriter(clone_from=PdfReader(path))
        writer.encrypt(password, algorithm="AES-256")
        with path.open("wb") as f:
            writer.write(f)
    return path


# ── A pretend Claude ─────────────────────────────────────────────────────────

FAKE_RULES = [  # (regex, merchant, category, confidence)
    (r"SALARY|PAYROLL|INTEREST", None, "Not an expense", "high"),
    (r"CREDIT CARD PAYMENT", "Card bill", "Not an expense", "high"),
    (r"PAYMENT RECEIVED", "Card payment", "Not an expense", "high"),
    (r"FRSHMRT", "Fresh Mart", "Grocery", "high"),
    (r"GREEN GROCER", "Green Grocer Co", "Grocery", "high"),
    (r"STREAMFLIX", "StreamFlix", "Subscriptions", "high"),
    (r"SPOTIFY", "Spotify", "Subscriptions", "high"),
    (r"CLOUDBOX", "CloudBox", "Subscriptions", "medium"),
    (r"PHONE CO", "Phone Co", "Subscriptions", "high"),
    (r"CABS|METRO|FUEL|PARKING|AIRWAYS|HOTEL", None, "Travel", "high"),
    (r"TRF TO SAVINGS|FIXED DEPOSIT", None, "Savings", "high"),
    (r"BROKERAGE|SIP", "BrightVest", "Investments", "high"),
    (r"RENT", "Rent", "Other", "high"),
    (r"GYMCO", "GymCo", "Other", "high"),
    (r"PIZZA|CAFE", None, "Other", "high"),
    (r"ATM", "Cash", "Other", "medium"),
]


def fake_label(description: str) -> tuple[str, str, str]:
    for pattern, merchant, category, confidence in FAKE_RULES:
        if re.search(pattern, description, re.IGNORECASE):
            return merchant or description.title()[:30], category, confidence
    return description.title()[:30], "Other", "low"


def fake_ask_claude(batch, corrections, model, on_call):
    """Pretend categorizer: same signature as categorize.ask_claude, rules from FAKE_RULES."""
    on_call(AICall("categorize", "demo", 0, 0, 0, "end_turn"))
    labels = {}
    for n, r in enumerate(batch, start=1):
        merchant, category, confidence = fake_label(r["description"])
        labels[n] = categorize.Labeled(n=n, merchant=merchant, category=category, confidence=confidence)
    return labels


def not_a_statement() -> StatementChunk:
    return StatementChunk(
        looks_like_statement=False,
        kind=None,
        bank_name=None,
        account_last4=None,
        currency=None,
        period_start=None,
        period_end=None,
        opening_balance=None,
        closing_balance=None,
        transactions=[],
    )


@contextmanager
def fake_claude(statements: dict[str, StatementChunk]) -> Iterator[None]:
    """While active, 'Claude' reads demo PDFs perfectly (by statement number) and sorts with FAKE_RULES."""

    def fake_extract_statement(reader, settings, on_call):
        text = reader.pages[0].extract_text() or "" if reader.pages else ""
        match = re.search(r"Statement no\.\s*(\S+)", text)
        on_call(AICall("extract", "demo", 0, 0, 0, "end_turn"))
        if not match or match.group(1) not in statements:
            return not_a_statement()
        return statements[match.group(1)]

    saved = extract.extract_statement, categorize.ask_claude
    extract.extract_statement, categorize.ask_claude = fake_extract_statement, fake_ask_claude
    try:
        yield
    finally:
        extract.extract_statement, categorize.ask_claude = saved
