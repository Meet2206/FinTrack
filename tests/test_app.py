"""Web app tests: every page renders without errors on real (fake-statement) data."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from streamlit.testing.v1 import AppTest

from finance import ledger

ROOT = Path(__file__).resolve().parent.parent
PAGES = [
    "app.py",
    "pages/1_Review.py",
    "pages/2_Dashboard.py",
    "pages/3_Transactions.py",
    "pages/4_Statements.py",
    "pages/5_Setup.py",
]


@pytest.fixture
def app_env(settings, db, run_statement, tmp_path, monkeypatch):
    """A config.yaml pointing at a temporary database filled with three months of fake statements."""
    opening = 2500.0
    for month in ("2026-09", "2026-10", "2026-11"):
        _, _, stmt = run_statement(month, opening=opening)
        opening = stmt.closing_balance
    config = {
        "sheets": {},
        "db_path": str(settings.db_path),
        "statements_dir": str(settings.statements_dir),
        "backups_dir": str(settings.backups_dir),
        "inbox_dir": str(settings.inbox_dir),
        "logs_dir": str(settings.logs_dir),
    }
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump(config))
    monkeypatch.setenv("WDMMG_CONFIG", str(cfg))
    return db


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(app_env, page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.title, "every page has a title"


def test_pages_render_with_an_empty_database(settings, monkeypatch, tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump({"db_path": str(tmp_path / "empty.db")}))
    monkeypatch.setenv("WDMMG_CONFIG", str(cfg))
    for page in PAGES:
        at = AppTest.from_file(str(ROOT / page), default_timeout=60).run()
        assert not at.exception, (page, [e.value for e in at.exception])


def test_missing_config_shows_instructions(monkeypatch, tmp_path):
    monkeypatch.setenv("WDMMG_CONFIG", str(tmp_path / "nope.yaml"))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert any("config.example.yaml" in e.value for e in at.error)


def test_review_page_approve_all_empties_the_queue(app_env):
    assert not ledger.review_queue(app_env).empty
    at = AppTest.from_file(str(ROOT / "pages/1_Review.py"), default_timeout=60).run()
    next(b for b in at.button if "Approve all" in b.label).click().run()
    assert not at.exception
    assert ledger.review_queue(app_env).empty


def test_dashboard_shows_alerts_and_can_dismiss(app_env):
    at = AppTest.from_file(str(ROOT / "pages/2_Dashboard.py"), default_timeout=60).run()
    before = len(ledger.open_alerts(app_env))
    assert before > 0 and any(m.label == "Spent" for m in at.metric)
    next(b for b in at.button if b.label == "Dismiss").click().run()
    assert len(ledger.open_alerts(app_env)) == before - 1


@pytest.fixture
def mismatch_env(settings, db, tmp_path, monkeypatch):
    """One statement whose numbers didn't add up (the AI 'misread' an amount)."""
    from finance import pipeline
    from finance.demo import build_statement, fake_claude, write_pdf

    truth = build_statement("2026-11")
    misread = truth.model_copy(deep=True)
    misread.transactions[2].debit = 1.0
    with fake_claude({"MIS-1": misread}):
        pipeline.process_statement(write_pdf(truth, tmp_path / "nov.pdf", "MIS-1"), settings, db)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"db_path": str(settings.db_path), "backups_dir": str(settings.backups_dir)})
    )
    monkeypatch.setenv("WDMMG_CONFIG", str(cfg))
    return db


def test_statements_page_shows_the_problem_and_approves(mismatch_env):
    at = AppTest.from_file(str(ROOT / "pages/4_Statements.py"), default_timeout=60).run()
    assert any("Row 3" in m.value for m in at.markdown), "the exact problem row is shown"
    next(b for b in at.button if "approve" in b.label).click().run()
    assert not at.exception
    assert ledger.get_statement(mismatch_env, 1)["status"] == "ready"


def test_sidebar_warns_about_statements_that_dont_add_up(mismatch_env):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
    assert any("don't add up" in w.value for w in at.sidebar.warning)


def test_setup_page_backup_button(app_env, settings):
    at = AppTest.from_file(str(ROOT / "pages/5_Setup.py"), default_timeout=60).run()
    next(b for b in at.button if "Back up" in b.label).click().run()
    assert not at.exception and list(settings.backups_dir.glob("ledger-*.db"))


def test_transactions_page_filters(app_env):
    at = AppTest.from_file(str(ROOT / "pages/3_Transactions.py"), default_timeout=60).run()
    at.selectbox[1].select("Travel").run()
    assert not at.exception
    assert all(c == "Travel" for c in at.dataframe[0].value["category"]) if at.dataframe else True
