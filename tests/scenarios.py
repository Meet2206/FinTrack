"""The statement test scenarios, and a pretend Claude that genuinely reads PDF text.

Each Scenario describes one situation a real user can run into: what the statement
PDF looks like, how the AI reads it (correctly, or with a deliberate mistake), and
what the app must do about it. They drive:
  • tests/test_scenarios.py          (automated, free)
  • scripts/make_test_fixtures.py    (writes the PDFs into tests/fixtures/ to open or upload)
  • tests/test_live.py               (the same PDFs through the REAL Claude, opt-in)

Readers ("how the AI behaves" in a scenario):
  text      a pretend Claude that reads the text of each page group it is sent and works
            out money in/out from how the balance moves. This exercises the real page
            splitting, retry-on-too-long and merging code.
  truth     a pretend Claude that returns exactly what we tell it (used to simulate misreads)
  refuse / rate_limit / offline / server_error   simulated API failures
"""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anthropic
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from finance import categorize, extract
from finance.costs import AICall
from finance.demo import build_statement, fake_ask_claude, month_rows, not_a_statement, write_pdf
from finance.extract import StatementChunk, Txn

# ── A pretend Claude that reads the PDF text ────────────────────────────────

DATE_LINE = re.compile(r"^\d{2} [A-Z][a-z]{2} \d{4}$")
NUMBER = re.compile(r"^-?[\d,]+\.\d{2}$")
HEADER = re.compile(
    r"(Account|Card) ending (\S+)\s+Period: (\d{2} \w{3} \d{4}) to (\d{2} \w{3} \d{4})\s+Currency: (\w{3})"
)


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _iso(text: str) -> str:
    return datetime.strptime(text, "%d %b %Y").date().isoformat()


def read_statement_text(pages: list[str]) -> StatementChunk:
    """Read statement pages the way a careful person would: header, then each row.
    Columns are lost in plain text, so money in/out is worked out from the balance movement."""
    text = "\n".join(pages)
    header = HEADER.search(text)
    if not header:
        return not_a_statement()
    is_card = header.group(1) == "Card"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    opening = closing = previous = None
    txns: list[Txn] = []
    i = 0
    while i < len(lines):
        line, nxt = lines[i], lines[i + 1] if i + 1 < len(lines) else ""
        if line == "Opening balance" and NUMBER.match(nxt):
            opening = previous = _num(nxt)
            i += 2
        elif line == "Balance brought forward" and NUMBER.match(nxt):
            previous = _num(nxt)
            i += 2
        elif line == "Balance carried forward":
            i += 2
        elif line == "Closing balance" and NUMBER.match(nxt):
            closing = _num(nxt)
            i += 2
        elif DATE_LINE.match(line):
            j, numbers = i + 2, []
            while j < len(lines) and NUMBER.match(lines[j]):
                numbers.append(_num(lines[j]))
                j += 1
            amount, balance = (numbers + [None, None])[:2]
            went_up = balance is not None and previous is not None and balance > previous
            money_in = (not went_up) if is_card else went_up
            txns.append(
                Txn(
                    date=_iso(line),
                    description=nxt,
                    debit=None if money_in else amount,
                    credit=amount if money_in else None,
                    balance=balance,
                )
            )
            previous = balance if balance is not None else previous
            i = j
        else:
            i += 1
    return StatementChunk(
        looks_like_statement=True,
        kind="card" if is_card else "bank",
        bank_name=lines[0],
        account_last4=header.group(2),
        currency=header.group(5),
        period_start=_iso(header.group(3)),
        period_end=_iso(header.group(4)),
        opening_balance=opening,
        closing_balance=closing,
        transactions=txns,
    )


@contextmanager
def reading_claude(max_rows_per_answer: int | None = None, log: list | None = None) -> Iterator[None]:
    """Pretend Claude that reads each page group it is sent. If a group holds more than
    `max_rows_per_answer` rows, it 'runs out of room' exactly like a cut-off real answer."""

    def fake_extract_pages(pdf_b64, model, on_call):
        reader = PdfReader(io.BytesIO(base64.b64decode(pdf_b64)))
        pages = [page.extract_text() or "" for page in reader.pages]
        if log is not None:
            log.append(len(pages))
        chunk = read_statement_text(pages)
        too_long = max_rows_per_answer is not None and len(chunk.transactions) > max_rows_per_answer
        on_call(
            AICall(
                "extract",
                model,
                sum(map(len, pages)) // 4,
                30 * len(chunk.transactions) + 60,
                0,
                "max_tokens" if too_long else "end_turn",
            )
        )
        if too_long:
            raise extract.ChunkTooLong()
        return chunk

    saved = extract.extract_pages, categorize.ask_claude
    extract.extract_pages, categorize.ask_claude = fake_extract_pages, fake_ask_claude
    try:
        yield
    finally:
        extract.extract_pages, categorize.ask_claude = saved


def _api_error(cls, status: int | None = None):
    """Build an Anthropic SDK error without a real HTTP response (only for simulations)."""
    error = cls.__new__(cls)
    Exception.__init__(error, f"simulated {cls.__name__}")
    if status is not None:
        error.status_code = status
    return error


@contextmanager
def failing_claude(mode: str) -> Iterator[None]:
    errors = {
        "refuse": extract.AIDeclined(),
        "rate_limit": _api_error(anthropic.RateLimitError, 429),
        "offline": _api_error(anthropic.APIConnectionError),
        "server_error": _api_error(anthropic.InternalServerError, 500),
    }

    def fail(pdf_b64, model, on_call):
        raise errors[mode]

    saved = extract.extract_pages
    extract.extract_pages = fail
    try:
        yield
    finally:
        extract.extract_pages = saved


# ── Statement contents used by the scenarios ────────────────────────────────

SMALL = [
    (1, "SALARY ACME CORP PAYROLL", None, 4200.00),
    (2, "POS 4471 FRSHMRT*CTY", 54.20, None),
    (3, "CITY CABS 0091", 18.40, None),
    (5, "STREAMFLIX.COM 800-555", 15.99, None),
    (7, "TRF TO SAVINGS A/C 5678", 500.00, None),
    (9, "PIZZA PALACE DELIVERY", 27.50, None),
]
SHOPS = [
    ("POS 4471 FRSHMRT*CTY", 41.0),
    ("GREEN GROCER CO", 18.0),
    ("CITY CABS 0091", 14.0),
    ("SHELL FUEL STATION 22", 46.0),
    ("CAFE LUNA 12", 5.5),
    ("PIZZA PALACE DELIVERY", 24.0),
    ("METRO CARD TOP UP", 20.0),
    ("PARKING GARAGE 7", 9.0),
]


def long_rows(count: int = 320) -> list[tuple]:
    """A busy month: salary first, then `count - 1` everyday purchases spread over the month."""
    rows = [(1, "SALARY ACME CORP PAYROLL", None, 9000.00)]
    for i in range(count - 1):
        shop, base = SHOPS[i % len(SHOPS)]
        rows.append((1 + (i * 29) // count, shop, round(base + (i * 37 % 100) / 10, 2), None))
    return rows


CARD_ROWS = [
    (2, "POS 4471 FRSHMRT*CTY", 54.20, None),
    (4, "AIRWAYS 0572 FLIGHT", 289.00, None),
    (6, "STREAMFLIX.COM 800-555", 15.99, None),
    (9, "REFUND FRSHMRT*CTY", None, 8.99),
    (15, "PAYMENT RECEIVED THANK YOU", None, 400.00),
    (20, "HOTEL BAYVIEW", 180.00, None),
]


def two_month_statement() -> StatementChunk:
    oct_part = build_statement(
        "2026-10",
        opening=1000.0,
        rows=[(20, "POS 4471 FRSHMRT*CTY", 50.0, None), (28, "CITY CABS 0091", 12.0, None)],
    )
    nov_part = build_statement(
        "2026-11",
        opening=oct_part.closing_balance,
        rows=[(3, "POS 4471 FRSHMRT*CTY", 61.0, None), (9, "GREEN GROCER CO", 22.5, None)],
    )
    return oct_part.model_copy(
        update={
            "transactions": oct_part.transactions + nov_part.transactions,
            "closing_balance": nov_part.closing_balance,
            "period_start": "2026-10-15",
            "period_end": "2026-11-14",
        }
    )


def misread(stmt: StatementChunk, change: Callable[[list[Txn]], None], **fields) -> StatementChunk:
    copy = stmt.model_copy(deep=True)
    change(copy.transactions)
    return copy.model_copy(update=fields)


def _set(i: int, **values):
    def change(txns):
        for k, v in values.items():
            setattr(txns[i], k, v)

    return change


# ── The scenarios ───────────────────────────────────────────────────────────


@dataclass
class Scenario:
    id: str
    title: str  # plain English: what situation is this?
    expect: str  # plain English: what must the app do?
    build: Callable[[], StatementChunk] | None = None
    reads_as: Callable[[StatementChunk], StatementChunk] | None = None  # simulate an AI misread
    reader: str = "text"
    password: str | None = None  # the PDF is locked with this
    typed_password: str | None = None  # …and the user typed this
    saved_password: str | None = None  # …or saved this in the Keychain earlier
    rows_per_page: int = 16
    max_rows_per_answer: int | None = None
    raw_file: Callable[[Path], None] | None = None  # write a non-statement / broken file instead
    status: str = "ready"
    message: str | None = None  # text the result message must contain
    issue: str | None = None  # text the first issue must contain
    check: Callable | None = None  # extra assertions: check(db, result, truth)
    tags: list[str] = field(default_factory=list)


def _menu_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.drawString(100, 750, "LUIGI'S PIZZERIA - MENU")
    c.drawString(100, 730, "Margherita 9.50    Pepperoni 11.00    Tiramisu 5.00")
    c.save()


def _blank_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path))
    c.showPage()
    c.save()


def _broken_pdf(path: Path) -> None:
    path.write_bytes(b"%PDF-1.7\nthis file was cut off during download")


def _rows(db) -> list:
    return db.execute("SELECT * FROM transactions ORDER BY txn_date, row_number").fetchall()


def _check_all_saved(db, result, truth):
    rows = _rows(db)
    assert len(rows) == len(truth.transactions)
    assert all(r["category"] for r in rows), "every row got a category"
    expected = sorted(round((t.debit or 0) - (t.credit or 0), 2) for t in truth.transactions)
    assert sorted(r["amount"] for r in rows) == expected, "every amount saved exactly"


def _check_card(db, result, truth):
    _check_all_saved(db, result, truth)
    account = db.execute("SELECT kind, account_last4 FROM accounts").fetchone()
    assert (account["kind"], account["account_last4"]) == ("card", "9876")
    flight = db.execute(
        "SELECT amount, category FROM transactions WHERE description LIKE 'AIRWAYS%'"
    ).fetchone()
    assert flight["amount"] == 289.00 and flight["category"] == "Travel"  # purchase = money out
    payment = db.execute(
        "SELECT amount, category FROM transactions WHERE description LIKE 'PAYMENT%'"
    ).fetchone()
    assert payment["amount"] == -400.00 and payment["category"] == "Not an expense"  # paying the card
    refund = db.execute(
        "SELECT amount, category FROM transactions WHERE description LIKE 'REFUND%'"
    ).fetchone()
    assert refund["amount"] == -8.99 and refund["category"] == "Grocery"


def _check_currency(db, result, truth):
    assert {r["currency"] for r in _rows(db)} == {"EUR"}


def _check_special_characters(db, result, truth):
    saved = {r["description"] for r in _rows(db)}
    assert {t.description for t in truth.transactions} <= saved


def _check_two_months(db, result, truth):
    assert {r["month"] for r in _rows(db)} == {"2026-10", "2026-11"}


def _check_twins(db, result, truth):
    coffees = [r for r in _rows(db) if r["description"] == "CAFE LUNA 12"]
    assert len(coffees) == 2 and coffees[0]["id"] != coffees[1]["id"]


def _check_quiet(db, result, truth):
    assert _rows(db) == [] and result.new_rows == 0


def _check_held(db, result, truth):
    rows = _rows(db)
    assert rows and all(r["needs_review"] == 1 for r in rows), "every row is held back"
    assert all(r["review_reason"] == "Statement totals don't match" for r in rows)


def _check_big(db, result, truth):
    assert max(r["amount"] for r in _rows(db)) == 1234567.89


def _check_zero(db, result, truth):
    fee = db.execute("SELECT amount FROM transactions WHERE description = 'ANNUAL FEE WAIVED'").fetchone()
    assert fee["amount"] == 0


def _check_long(db, result, truth):
    _check_all_saved(db, result, truth)
    calls = db.execute("SELECT COUNT(*) FROM ai_calls WHERE purpose = 'extract'").fetchone()[0]
    pages = db.execute("SELECT page_count FROM statements").fetchone()[0]
    assert pages == 20 and calls == 7, "20 pages are read in 7 groups of up to 3 pages"


def _check_split(db, result, truth):
    _check_all_saved(db, result, truth)
    calls = db.execute("SELECT COUNT(*) FROM ai_calls WHERE purpose = 'extract'").fetchone()[0]
    assert calls > 3, "groups that were too long were split and re-read"


SCENARIOS: list[Scenario] = [
    # ── Reading normal statements ──
    Scenario(
        "S01-standard",
        "A normal month: 2-page bank statement, 31 transactions",
        "Read every row, balances match, everything categorized",
        build=lambda: build_statement("2026-11"),
        message="Balances match",
        check=_check_all_saved,
        tags=["fixture"],
    ),
    Scenario(
        "S02-long-20-pages",
        "A very busy month: 320 transactions over 20 pages",
        "Read in groups of 3 pages, stitched back together, nothing lost",
        build=lambda: build_statement("2026-11", rows=long_rows()),
        check=_check_long,
        tags=["fixture"],
    ),
    Scenario(
        "S03-answer-too-long",
        "Page groups too long for one AI answer",
        "Split the group in half and re-read until it fits",
        build=lambda: build_statement("2026-11"),
        rows_per_page=12,
        max_rows_per_answer=14,
        check=_check_split,
    ),
    Scenario(
        "S04-one-row",
        "A statement with a single transaction",
        "Works the same as a big one",
        build=lambda: build_statement("2026-11", rows=[(4, "POS 4471 FRSHMRT*CTY", 54.20, None)]),
        check=_check_all_saved,
        tags=["fixture"],
    ),
    Scenario(
        "S05-quiet-month",
        "A quiet month: zero transactions, opening = closing",
        "Accepted as a valid statement with 0 rows (nothing to sync, so it's already 'synced')",
        build=lambda: build_statement("2026-11", rows=[]),
        status="synced",
        message="Read 0 transactions",
        check=_check_quiet,
        tags=["fixture"],
    ),
    Scenario(
        "S06-credit-card",
        "A credit card statement (balance = what you owe)",
        "Purchases count as money out, the card payment is 'Not an expense', refunds are negative",
        build=lambda: build_statement(
            "2026-11", opening=150.0, last4="9876", rows=CARD_ROWS, kind="card", bank_name="EXAMPLE CARD CO"
        ),
        check=_check_card,
        tags=["fixture"],
    ),
    Scenario(
        "S07-euro",
        "A statement in euros",
        "Currency stored as EUR",
        build=lambda: build_statement("2026-11", rows=SMALL, currency="EUR"),
        check=_check_currency,
        tags=["fixture"],
    ),
    Scenario(
        "S08-special-characters",
        "Descriptions with accents, quotes and symbols",
        "Saved exactly as printed",
        build=lambda: build_statement(
            "2026-11",
            rows=[
                (2, "CAFÉ MÜLLER & SÖHNE", 12.40, None),
                (3, "O'NEILL'S PUB", 23.00, None),
                (5, 'BOOKS "R" US #42', 18.75, None),
            ],
        ),
        check=_check_special_characters,
        tags=["fixture"],
    ),
    Scenario(
        "S09-big-amounts",
        "Amounts over a million",
        "Stored to the cent",
        build=lambda: build_statement(
            "2026-11", opening=2_000_000.00, rows=[(2, "HOUSE DEPOSIT TRANSFER", 1234567.89, None)]
        ),
        check=_check_big,
        tags=["fixture"],
    ),
    Scenario(
        "S10-zero-amount",
        "A 0.00 line (a waived fee)",
        "Kept as a 0.00 row; math still checks out",
        build=lambda: build_statement("2026-11", rows=SMALL + [(12, "ANNUAL FEE WAIVED", 0.00, None)]),
        check=_check_zero,
        tags=["fixture"],
    ),
    Scenario(
        "S11-two-months",
        "A statement covering Oct 15 – Nov 14",
        "Rows land in both month tabs",
        build=two_month_statement,
        check=_check_two_months,
        tags=["fixture"],
    ),
    Scenario(
        "S12-identical-twins",
        "Two identical coffees on the same day",
        "Both are kept (both happened)",
        build=lambda: build_statement(
            "2026-11", rows=SMALL + [(9, "CAFE LUNA 12", 4.50, None), (9, "CAFE LUNA 12", 4.50, None)]
        ),
        check=_check_twins,
        tags=["fixture"],
    ),
    # ── Locked PDFs ──
    Scenario(
        "S13-locked-right-password",
        "Password-protected PDF, correct password typed",
        "Opens and reads",
        build=lambda: build_statement("2026-11", rows=SMALL),
        password="Dob-1990",
        typed_password="Dob-1990",
        tags=["fixture"],
    ),
    Scenario(
        "S14-locked-no-password",
        "Password-protected PDF, no password given",
        "Fails safely and asks for the password",
        build=lambda: build_statement("2026-11", rows=SMALL),
        password="Dob-1990",
        status="failed",
        message="locked",
    ),
    Scenario(
        "S15-locked-wrong-password",
        "Password-protected PDF, wrong password typed",
        "Fails safely and asks for the password",
        build=lambda: build_statement("2026-11", rows=SMALL),
        password="Dob-1990",
        typed_password="1990-Dob",
        status="failed",
        message="locked",
    ),
    Scenario(
        "S16-locked-saved-password",
        "Password-protected PDF, password saved earlier in the Keychain",
        "Opens automatically without asking",
        build=lambda: build_statement("2026-11", rows=SMALL),
        password="Dob-1990",
        saved_password="Dob-1990",
    ),
    # ── Statements that print fewer balances ──
    Scenario(
        "S17-no-opening-balance",
        "No opening balance printed (running balances are)",
        "Opening worked out from row 1; verified",
        build=lambda: build_statement("2026-11", rows=SMALL, opening_printed=False),
        reader="truth",
    ),
    Scenario(
        "S18-only-opening-and-closing",
        "Only opening and closing balances printed",
        "Verified by the closing balance alone",
        build=lambda: build_statement("2026-11", rows=SMALL, running_balance=False),
        reader="truth",
    ),
    Scenario(
        "S19-no-balances",
        "No balances printed at all",
        "Can't be verified: every row held for you",
        build=lambda: build_statement(
            "2026-11", rows=SMALL, running_balance=False, opening_printed=False, closing_printed=False
        ),
        reader="truth",
        status="mismatch",
        issue="can't be verified",
        check=_check_held,
    ),
    # ── The AI makes a mistake ──
    Scenario(
        "S20-misread-amount",
        "AI misreads one amount (18.40 → 18.04)",
        "Caught: points at row 3, holds every row",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, _set(2, debit=18.04)),
        reader="truth",
        status="mismatch",
        issue="Row 3",
        check=_check_held,
    ),
    Scenario(
        "S21-misread-money-direction",
        "AI reads money out as money in",
        "Caught: the balance moves the wrong way",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, _set(1, debit=None, credit=54.20)),
        reader="truth",
        status="mismatch",
        issue="Row 2",
    ),
    Scenario(
        "S22-skipped-row",
        "AI skips a row",
        "Caught: the next balance jumps",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, lambda t: t.pop(3)),
        reader="truth",
        status="mismatch",
        issue="Row 4",
    ),
    Scenario(
        "S23-duplicated-row",
        "AI reads a row twice",
        "Caught: the copy breaks the balance",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, lambda t: t.insert(2, t[2].model_copy())),
        reader="truth",
        status="mismatch",
        issue="Row 4",
    ),  # the copy (row 3) still fits; the real row 4 doesn't
    Scenario(
        "S24-misread-closing",
        "AI misreads the closing balance",
        "Caught at the closing line",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, lambda t: None, closing_balance=s.closing_balance + 100),
        reader="truth",
        status="mismatch",
        issue="Closing balance",
    ),
    Scenario(
        "S25-misread-date",
        "AI misreads a year (2026 → 2027)",
        "Caught: date is outside the statement period",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, _set(3, date="2027-11-05")),
        reader="truth",
        status="mismatch",
        issue="outside the statement period",
    ),
    Scenario(
        "S26-impossible-date",
        "AI returns an impossible date (30 February)",
        "Caught: not a valid date",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reads_as=lambda s: misread(s, _set(3, date="2026-02-30")),
        reader="truth",
        status="mismatch",
        issue="isn't a valid date",
    ),
    # ── Not a statement / broken files ──
    Scenario(
        "S27-not-a-statement",
        "A restaurant menu PDF uploaded by mistake",
        "Politely rejected",
        raw_file=_menu_pdf,
        status="failed",
        message="doesn't look like",
        tags=["fixture"],
    ),
    Scenario(
        "S28-blank-pdf",
        "A blank PDF page",
        "Politely rejected",
        raw_file=_blank_pdf,
        status="failed",
        message="doesn't look like",
        tags=["fixture"],
    ),
    Scenario(
        "S29-broken-file",
        "A corrupted / half-downloaded PDF",
        "Rejected as unreadable",
        raw_file=_broken_pdf,
        status="failed",
        message="isn't a readable PDF",
        tags=["fixture"],
    ),
    Scenario(
        "S30-page-too-dense",
        "One page holds more rows than the AI can return",
        "Fails with a clear message instead of guessing",
        build=lambda: build_statement("2026-11", rows=long_rows(45)),
        rows_per_page=45,
        max_rows_per_answer=20,
        status="failed",
        message="too many rows",
    ),
    # ── The AI service has a problem ──
    Scenario(
        "S31-ai-declines",
        "The AI declines the request",
        "Fails safely, can retry",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reader="refuse",
        status="failed",
        message="declined",
    ),
    Scenario(
        "S32-ai-busy",
        "Claude is busy (rate limit)",
        "Fails safely: 'try again in a minute'",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reader="rate_limit",
        status="failed",
        message="busy",
    ),
    Scenario(
        "S33-offline",
        "No internet connection",
        "Fails safely: 'check your connection'",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reader="offline",
        status="failed",
        message="internet",
    ),
    Scenario(
        "S34-ai-server-error",
        "Claude has a server error (500)",
        "Fails safely with the error code",
        build=lambda: build_statement("2026-11", rows=SMALL),
        reader="server_error",
        status="failed",
        message="500",
    ),
]


def write_scenario_file(scenario: Scenario, folder: Path) -> Path:
    """Create the file a user would upload for this scenario."""
    path = Path(folder) / f"{scenario.id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if scenario.raw_file:
        scenario.raw_file(path)
        return path
    return write_pdf(
        scenario.build(),
        path,
        statement_no=scenario.id,
        password=scenario.password,
        rows_per_page=scenario.rows_per_page,
    )


@contextmanager
def ai_for(scenario: Scenario, truth: StatementChunk | None) -> Iterator[None]:
    """Make the pretend Claude behave the way the scenario says."""
    if scenario.reader == "text":
        with reading_claude(scenario.max_rows_per_answer):
            yield
    elif scenario.reader == "truth":
        from finance.demo import fake_claude

        seen = scenario.reads_as(truth) if scenario.reads_as else truth
        with fake_claude({scenario.id: seen}):
            yield
    else:
        with reading_claude(), failing_claude(scenario.reader):  # failure wins for reading pages
            yield


__all__ = [
    "SCENARIOS",
    "Scenario",
    "ai_for",
    "month_rows",
    "read_statement_text",
    "reading_claude",
    "write_scenario_file",
]
