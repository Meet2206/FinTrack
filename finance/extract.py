"""Claude reads statement pages and fills in a strict form.

In plain English: we send Claude a few pages plus a form (the `Txn` and
`StatementChunk` classes below). Claude returns the form filled in, and Pydantic
checks every field has the right type. If a group of pages is too long for one
answer, we cut it in half and try again.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Literal

import anthropic
import pydantic
from pydantic import BaseModel, Field

from finance import costs, prompts
from finance.pdf_tools import page_groups, pages_as_pdf

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """One shared Claude client, created on first use (reads ANTHROPIC_API_KEY)."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


class MissingAPIKey(Exception):
    """No Claude credentials were found (ANTHROPIC_API_KEY isn't set)."""


def claude_parse(**kwargs):
    """messages.parse(), turning the SDK's 'no credentials' TypeError into a clear MissingAPIKey."""
    try:
        return get_client().messages.parse(**kwargs)
    except TypeError as e:
        if "authentication" in str(e).lower():
            raise MissingAPIKey() from e
        raise


class Txn(BaseModel):
    date: str = Field(description="Transaction date as YYYY-MM-DD")
    description: str = Field(description="Exactly as printed; join the lines if it wraps")
    debit: float | None = Field(description="Money out (or a charge on a credit card), as a positive number")
    credit: float | None = Field(
        description="Money in (or a payment/refund on a credit card), as a positive number"
    )
    balance: float | None = Field(description="Running balance printed after this row, if any")


class StatementChunk(BaseModel):
    looks_like_statement: bool = Field(
        description="False if these pages are not from a bank or credit card statement"
    )
    kind: Literal["bank", "card"] | None = Field(description="'card' for a credit card statement")
    bank_name: str | None
    account_last4: str | None = Field(description="Last 4 digits of the account/card number only")
    currency: str | None = Field(description="ISO 4217 code, e.g. USD, EUR, INR")
    period_start: str | None = Field(description="YYYY-MM-DD")
    period_end: str | None = Field(description="YYYY-MM-DD")
    opening_balance: float | None = Field(description="Only if printed on these pages")
    closing_balance: float | None = Field(description="Only if printed on these pages")
    transactions: list[Txn]


# The instructions Claude follows: edit them in prompts/app/extract-statement.md
EXTRACT_PROMPT = prompts.load("extract-statement")


class ChunkTooLong(Exception):
    """Claude's answer was cut off: send fewer pages at a time."""


class AIDeclined(Exception):
    """Claude declined to process these pages."""


def extract_pages(pdf_b64: str, model: str, on_call: Callable[[costs.AICall], None]) -> StatementChunk:
    """Send one group of pages to Claude and get the filled-in form back."""
    started = time.monotonic()
    try:
        resp = claude_parse(
            model=model,
            max_tokens=16000,
            system=EXTRACT_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64},
                        },
                        {"type": "text", "text": "Copy out the transactions on these pages."},
                    ],
                }
            ],
            output_format=StatementChunk,
        )
    except pydantic.ValidationError as e:
        # The answer didn't fit the form, which usually means it was cut off mid-way.
        raise ChunkTooLong() from e

    on_call(costs.from_response("extract", model, resp, started))
    if resp.stop_reason == "max_tokens":
        raise ChunkTooLong()
    if resp.stop_reason == "refusal":
        raise AIDeclined()
    if resp.stop_reason != "end_turn" or resp.parsed_output is None:
        raise RuntimeError(f"Claude stopped unexpectedly while reading pages: {resp.stop_reason}")
    return resp.parsed_output


def extract_statement(reader, settings, on_call: Callable[[costs.AICall], None]) -> StatementChunk:
    """Read every page group and join the results into one statement."""
    if getattr(settings, "offline_mode", False):
        return extract_statement_local(reader)
    chunks: list[StatementChunk] = []
    for pages in page_groups(reader, settings.pages_per_chunk):
        chunks += _extract_with_retry(reader, pages, settings.model, on_call)
    return merge(chunks)


_DATE_RE = re.compile(
    r"^(\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?|\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-[A-Za-z]{3}-\d{2,4})\b"
)
_MONEY_RE = re.compile(r"(?:[$₹€£]\s*)?-?\d[\d,]*(?:\.\d{2})")


def _date(value: str, default_year: int | None = None, month_first: bool = False) -> str | None:
    if default_year and re.fullmatch(r"\d{1,2}[/-]\d{1,2}", value):
        first, second = re.split(r"[/-]", value)
        value = f"{first}/{second}/{default_year}"
        fmt = "%m/%d/%Y" if month_first else "%d/%m/%Y"
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _amount(value: str) -> float:
    return abs(float(value.replace(",", "").replace("$", "").replace("₹", "").replace("€", "").replace("£", "")))


def _period(text: str) -> tuple[str | None, str | None]:
    def month_date(day: str, month: str, year: str) -> str:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(f"{day} {month} {year}", fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError

    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*[–-]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        text,
    )
    if m:
        try:
            return (
                month_date(m[1], m[2], m[3]),
                month_date(m[4], m[5], m[6]),
            )
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+to\s+(\d{1,2})/(\d{1,2})/(\d{4})", text, re.I)
    if m:
        return f"{m[3]}-{m[2]}-{m[1]}", f"{m[6]}-{m[5]}-{m[4]}"
    m = re.search(
        r"Statement period\s*:\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s+to\s+"
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        text,
        re.I,
    )
    if m:
        try:
            return month_date(m[1], m[2], m[3]), month_date(m[4], m[5], m[6])
        except ValueError:
            pass
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*[–-]\s*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        try:
            return (
                month_date(m[2], m[1], m[5]),
                month_date(m[4], m[3], m[5]),
            )
        except ValueError:
            pass
    return None, None


def extract_statement_local(reader) -> StatementChunk:
    """Parse the text-based statement pack locally; never calls a network service."""
    text = "\n".join(page.extract_text() or "" for page in reader.pages).replace("\x7f", "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    period_start, period_end = _period(text)
    account = re.search(r"(?:account|card)(?: number)?[^\n]*?(\d{4})\b", text, re.I)
    bank = next((line for line in lines[:12] if "bank" in line.lower()), lines[0] if lines else None)
    currency = (re.search(r"\b(INR|USD|EUR|GBP)\b", text) or [None, None])[1]
    opening_m = re.search(
        r"Opening balance(?: \([^)]*\))?[^\d\n]*(?:\n[^\d\n]*)?([\d,]+\.\d{2})", text, re.I
    )
    closing_m = re.search(
        r"Closing balance(?: \([^)]*\))?[^\d\n]*(?:\n[^\d\n]*)?([\d,]+\.\d{2})", text, re.I
    )
    opening = _amount(opening_m[1]) if opening_m else None
    closing = _amount(closing_m[1]) if closing_m else None

    header_index = next(
        (i for i, line in enumerate(lines) if line.lower() == "date" or line.lower().startswith("date ")),
        -1,
    )
    starts = [i for i, line in enumerate(lines) if i > header_index and _DATE_RE.match(line)]
    transactions: list[Txn] = []
    previous_balance = opening
    for pos, start in enumerate(starts):
        chunk = lines[start : starts[pos + 1] if pos + 1 < len(starts) else len(lines)]
        match = _DATE_RE.match(chunk[0])
        txn_date = (
            _date(
                match[1],
                default_year=int(period_start[:4]) if period_start else None,
                month_first="riverbend" in text.lower(),
            )
            if match
            else None
        )
        if not txn_date or any(x.lower() in chunk[0].lower() for x in ("opening balance", "closing balance")):
            continue
        body = chunk[0][match.end() :].strip() + " " + " ".join(chunk[1:])
        if re.search(r"\b(opening|closing) balance\b", body, re.I):
            continue
        numbers = _MONEY_RE.findall(body)
        if len(numbers) < 2:
            continue
        balance = _amount(numbers[-1])
        amount = _amount(numbers[-2])
        description = body
        for number in numbers[-2:]:
            description = description.replace(number, " ", 1)
        description = re.sub(r"\s+", " ", description).strip(" -")
        description = re.split(
            r"\b(?:This document|This statement|Synthetic customer|SPECIMEN\s*-|S Y N T H E T I C)\b",
            description,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" -")
        explicit_type = next((x.upper() for x in chunk[1:4] if x.upper() in {"DEBIT", "CREDIT"}), None)
        if explicit_type == "DEBIT":
            debit, credit = amount, None
        elif explicit_type == "CREDIT":
            debit, credit = None, amount
        elif previous_balance is not None and balance >= previous_balance:
            debit, credit = None, amount
        else:
            debit, credit = amount, None
        transactions.append(Txn(date=txn_date, description=description, debit=debit, credit=credit, balance=balance))
        previous_balance = balance

    looks_like = bool(transactions) and bool(re.search(r"statement|balance|transaction", text, re.I))
    return StatementChunk(
        looks_like_statement=looks_like,
        kind="card" if re.search(r"credit card statement|credit card account|card statement", text, re.I) else "bank",
        bank_name=bank,
        account_last4=account[1] if account else None,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        opening_balance=opening,
        closing_balance=closing,
        transactions=transactions,
    )


def _extract_with_retry(reader, pages: range, model: str, on_call) -> list[StatementChunk]:
    try:
        return [extract_pages(pages_as_pdf(reader, pages), model, on_call)]
    except ChunkTooLong:
        if len(pages) == 1:
            raise  # can't split a single page further
        middle = pages.start + len(pages) // 2  # split the group in half and retry
        return _extract_with_retry(reader, range(pages.start, middle), model, on_call) + _extract_with_retry(
            reader, range(middle, pages.stop), model, on_call
        )


def merge(chunks: list[StatementChunk]) -> StatementChunk:
    """Header details from the first group that has them, closing balance from the
    last group that has it, and every transaction in order."""

    def first(field, items):
        return next((getattr(c, field) for c in items if getattr(c, field) is not None), None)

    header = [
        "kind",
        "bank_name",
        "account_last4",
        "currency",
        "period_start",
        "period_end",
        "opening_balance",
    ]
    return StatementChunk(
        looks_like_statement=bool(chunks) and chunks[0].looks_like_statement,
        **{field: first(field, chunks) for field in header},
        closing_balance=first("closing_balance", list(reversed(chunks))),
        transactions=[t for c in chunks for t in c.transactions],
    )
