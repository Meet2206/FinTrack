"""Claude reads statement pages and fills in a strict form.

In plain English: we send Claude a few pages plus a form (the `Txn` and
`StatementChunk` classes below). Claude returns the form filled in, and Pydantic
checks every field has the right type. If a group of pages is too long for one
answer, we cut it in half and try again.
"""

from __future__ import annotations

import time
from collections.abc import Callable
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
    chunks: list[StatementChunk] = []
    for pages in page_groups(reader, settings.pages_per_chunk):
        chunks += _extract_with_retry(reader, pages, settings.model, on_call)
    return merge(chunks)


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
