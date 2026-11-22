"""Shared test helpers. Tests never touch real statements, the real Claude API,
real Google Sheets or your Keychain."""

from __future__ import annotations

from pathlib import Path

import pytest

from finance import ledger, pdf_tools, pipeline
from finance.config import Settings
from finance.demo import build_statement, fake_claude, write_pdf

TEST_KEYWORDS = {
    "Subscriptions": ["spotify"],
    "Travel": ["fuel", "metro", "parking", "airways", "hotel"],
    "Investments": ["sip"],
    "Savings": ["fixed deposit"],
    "Not an expense": ["salary", "payroll"],
}


@pytest.fixture(autouse=True)
def no_keychain(monkeypatch):
    """Never read or write the real macOS Keychain during tests."""
    store: dict[str, str] = {}
    monkeypatch.setattr(pdf_tools.keyring, "get_password", lambda s, n: store.get(n))
    monkeypatch.setattr(pdf_tools.keyring, "set_password", lambda s, n, p: store.__setitem__(n, p))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        sheets={
            "Grocery": "id-g",
            "Travel": "id-t",
            "Subscriptions": "id-s",
            "Investments": "id-i",
            "Savings": "id-v",
        },
        keywords=TEST_KEYWORDS,
        service_account_file=tmp_path / "service_account.json",
        db_path=tmp_path / "data" / "ledger.db",
        statements_dir=tmp_path / "data" / "statements",
        backups_dir=tmp_path / "data" / "backups",
        inbox_dir=tmp_path / "data" / "inbox",
        logs_dir=tmp_path / "data" / "logs",
    )


@pytest.fixture
def db(settings):
    conn = ledger.connect(settings.db_path)
    yield conn
    conn.close()


class FakeSheets:
    """In-memory stand-in for Google Sheets: {(category, month): rows}."""

    def __init__(self):
        self.tabs: dict[tuple[str, str], list[list]] = {}
        self.summaries: dict[str, list[str]] = {}
        self.rebuilt: list[tuple[str, str]] = []

    def __call__(self, settings):  # used as sync(..., mirror_factory=fake)
        return self

    def rebuild_tab(self, category, month, rows):
        self.rebuilt.append((category, month))
        if rows:
            self.tabs[(category, month)] = rows
        else:
            self.tabs.pop((category, month), None)

    def rebuild_summary(self, category, months):
        self.summaries[category] = sorted(months, reverse=True)

    def descriptions(self, category, month) -> list[str]:
        return [r[2] for r in self.tabs.get((category, month), [])]


@pytest.fixture
def sheets() -> FakeSheets:
    return FakeSheets()


@pytest.fixture
def run_statement(settings, db, tmp_path):
    """Write a fake statement PDF and push it through the real pipeline with a pretend Claude."""
    counter = iter(range(1, 1000))

    def _run(month="2026-11", stmt=None, truth=None, password=None, open_with=None, **build):
        stmt = stmt or build_statement(month, **build)
        number = f"TEST-{next(counter)}"
        path = write_pdf(stmt, tmp_path / f"{number}.pdf", statement_no=number, password=password)
        with fake_claude({number: truth or stmt}):
            result = pipeline.process_statement(path, settings, db, open_with)
        return result, path, stmt

    return _run
