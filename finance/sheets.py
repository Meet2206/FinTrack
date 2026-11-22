"""The Google Sheets mirror.

In plain English: the mirror only writes, never reads. For each affected month it
wipes the tab and rewrites it with exactly what the ledger says. That means:
- running sync twice gives the same result,
- a crashed sync is fixed by running it again,
- a row that changes category automatically leaves its old sheet.
"""

from __future__ import annotations

import json
from pathlib import Path

import gspread

HEADERS = ["Date", "Merchant", "Description", "Amount", "Currency", "Account", "Txn ID"]
SUMMARY = "Summary"


class SheetAccessError(Exception):
    """A spreadsheet couldn't be opened (missing, not shared, or bad credentials)."""


def robot_email(service_account_file: Path) -> str:
    """The service account's email: the address you share spreadsheets with."""
    try:
        return json.loads(Path(service_account_file).read_text()).get("client_email", "?")
    except (OSError, ValueError):
        return "the client_email in service_account.json"


class SheetsMirror:
    """Writes ledger rows into the Google Sheets. Never reads data back."""

    def __init__(self, settings):
        self.settings = settings
        if not Path(settings.service_account_file).exists():
            raise SheetAccessError(
                f"'{settings.service_account_file}' not found. Download the service account key "
                "from Google Cloud (see Backend.md → Setup, step 4)."
            )
        self.gc = gspread.service_account(
            filename=str(settings.service_account_file), http_client=gspread.BackOffHTTPClient
        )  # retries "slow down"
        self._books: dict[str, gspread.Spreadsheet] = {}

    def book(self, category: str) -> gspread.Spreadsheet:
        if category not in self._books:
            try:
                self._books[category] = self.gc.open_by_key(self.settings.sheets[category])
            except (
                gspread.exceptions.SpreadsheetNotFound,
                gspread.exceptions.APIError,
                PermissionError,
            ) as e:
                raise SheetAccessError(
                    f"Can't open the {category} spreadsheet. Check its ID in config.yaml and share it "
                    f"with {robot_email(self.settings.service_account_file)} as Editor."
                ) from e
        return self._books[category]

    def rebuild_tab(self, category: str, month: str, rows: list[list]) -> None:
        """Make the month tab contain exactly `rows`, nothing more, nothing less."""
        book = self.book(category)
        try:
            ws = book.worksheet(month)
        except gspread.exceptions.WorksheetNotFound:
            if not rows:
                return
            ws = book.add_worksheet(title=month, rows=len(rows) + 50, cols=len(HEADERS))
        if not rows:  # every row moved elsewhere: remove the empty tab
            book.del_worksheet(ws)
            return
        ws.clear()
        ws.resize(rows=len(rows) + 50, cols=len(HEADERS))
        ws.update(values=[HEADERS] + rows, range_name="A1", value_input_option="USER_ENTERED")
        ws.freeze(rows=1)

    def rebuild_summary(self, category: str, months: list[str]) -> None:
        """Rewrite the Summary tab, then order tabs: Summary first, newest month next."""
        book = self.book(category)
        try:
            summary = book.worksheet(SUMMARY)
        except gspread.exceptions.WorksheetNotFound:
            summary = book.add_worksheet(title=SUMMARY, rows=200, cols=3, index=0)
        newest_first = sorted(months, reverse=True)
        values = [["Month", "Total", "Transactions"]] + [
            [m, f"=SUM('{m}'!D2:D)", f"=COUNTA('{m}'!A2:A)"] for m in newest_first
        ]
        summary.clear()
        summary.update(values=values, range_name="A1", value_input_option="USER_ENTERED")
        summary.freeze(rows=1)
        month_tabs = sorted(
            (ws for ws in book.worksheets() if ws.title != SUMMARY), key=lambda ws: ws.title, reverse=True
        )
        book.reorder_worksheets([summary] + month_tabs)


def check_access(settings) -> list[tuple[bool, str]]:
    """For the setup check: can we open each spreadsheet, and does it have a Summary tab?"""
    results = []
    try:
        mirror = SheetsMirror(settings)
    except SheetAccessError as e:
        return [(False, str(e))]
    for category in settings.sheets:
        try:
            titles = [ws.title for ws in mirror.book(category).worksheets()]
        except SheetAccessError as e:
            results.append((False, str(e)))
            continue
        if SUMMARY in titles:
            results.append((True, f"{category} spreadsheet opens, Summary tab found"))
        else:
            results.append(
                (True, f"{category} spreadsheet opens (a Summary tab will be created on first sync)")
            )
    return results
