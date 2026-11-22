"""A small in-memory imitation of the parts of gspread that finance/sheets.py uses.

It lets the REAL SheetsMirror code run in tests without Google. It behaves like Google
where it matters: worksheets have a fixed grid size (writing past it fails), titles are
unique, missing tabs raise WorksheetNotFound, unshared spreadsheets can't be opened,
and Summary formulas can be evaluated to check the totals.
"""

from __future__ import annotations

import re

import gspread

WRITES = {"update", "clear", "resize", "add_worksheet", "del_worksheet", "reorder", "freeze"}


class FakeWorksheet:
    def __init__(self, book: FakeSpreadsheet, title: str, rows: int = 1000, cols: int = 26):
        self.book, self.title, self.row_count, self.col_count = book, title, rows, cols
        self.values: list[list] = []
        self.frozen_rows = 0

    def _log(self, action: str) -> None:
        self.book.client.calls.append((action, self.book.key, self.title))

    def clear(self):
        self._log("clear")
        self.values = []

    def resize(self, rows=None, cols=None):
        self._log("resize")
        self.row_count, self.col_count = rows or self.row_count, cols or self.col_count

    def update(self, values=None, range_name=None, value_input_option=None, **_):
        self._log("update")
        assert range_name == "A1", "the mirror always writes whole tabs from A1"
        assert value_input_option == "USER_ENTERED", "so dates and numbers are real dates and numbers"
        if len(values) > self.row_count:
            raise ValueError(f"Range exceeds grid limits: {len(values)} rows > {self.row_count}")
        self.values = [list(r) for r in values]

    def freeze(self, rows=None, cols=None):
        self._log("freeze")
        self.frozen_rows = rows or 0

    # helpers for assertions
    @property
    def header(self) -> list:
        return self.values[0] if self.values else []

    @property
    def rows(self) -> list[list]:
        return self.values[1:]


class FakeSpreadsheet:
    def __init__(self, client: FakeClient, key: str, with_summary: bool = True):
        self.client, self.key = client, key
        self._sheets: list[FakeWorksheet] = (
            [FakeWorksheet(self, "Summary")] if with_summary else [FakeWorksheet(self, "Sheet1")]
        )

    def worksheet(self, title: str) -> FakeWorksheet:
        for ws in self._sheets:
            if ws.title == title:
                return ws
        raise gspread.exceptions.WorksheetNotFound(title)

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._sheets)

    def add_worksheet(self, title, rows, cols, index=None) -> FakeWorksheet:
        self.client.calls.append(("add_worksheet", self.key, title))
        if any(ws.title == title for ws in self._sheets):
            raise ValueError(f'A sheet with the name "{title}" already exists')
        ws = FakeWorksheet(self, title, rows, cols)
        self._sheets.insert(len(self._sheets) if index is None else index, ws)
        return ws

    def del_worksheet(self, ws: FakeWorksheet) -> None:
        self.client.calls.append(("del_worksheet", self.key, ws.title))
        self._sheets.remove(ws)

    def reorder_worksheets(self, order) -> None:
        self.client.calls.append(("reorder", self.key, ""))
        assert {ws.title for ws in order} == {ws.title for ws in self._sheets}, "reorder must keep every tab"
        self._sheets = list(order)

    # helpers for assertions
    @property
    def titles(self) -> list[str]:
        return [ws.title for ws in self._sheets]

    def evaluate(self, formula: str) -> float:
        """Evaluate the two formula shapes the Summary tab uses: =SUM('m'!D2:D) and =COUNTA('m'!A2:A)."""
        m = re.fullmatch(r"=(SUM|COUNTA)\('([^']+)'!([A-Z])2:\3\)", formula)
        assert m, f"unexpected formula {formula}"
        func, tab, col = m.groups()
        cells = [r[ord(col) - ord("A")] for r in self.worksheet(tab).rows]
        return round(sum(cells), 2) if func == "SUM" else len([c for c in cells if c not in ("", None)])

    def summary(self) -> dict[str, tuple[float, int]]:
        rows = self.worksheet("Summary").rows
        return {month: (self.evaluate(total), self.evaluate(count)) for month, total, count in rows}


class FakeClient:
    def __init__(self, unshared: set[str] | None = None, without_summary: set[str] | None = None):
        self.books: dict[str, FakeSpreadsheet] = {}
        self.calls: list[tuple[str, str, str]] = []
        self.unshared = unshared or set()
        self.without_summary = without_summary or set()

    def open_by_key(self, key: str) -> FakeSpreadsheet:
        if key in self.unshared:
            raise gspread.exceptions.SpreadsheetNotFound(key)
        if key not in self.books:
            self.books[key] = FakeSpreadsheet(self, key, with_summary=key not in self.without_summary)
        return self.books[key]

    def writes(self) -> list[tuple[str, str, str]]:
        return [c for c in self.calls if c[0] in WRITES]
