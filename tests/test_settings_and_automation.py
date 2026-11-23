"""Settings file, monthly summary + Telegram, folder automation, setup checklist."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from finance import ledger, pipeline, summary, watcher
from finance.config import ConfigError, load_settings
from finance.demo import build_statement, fake_claude, write_pdf
from finance.setup_check import run_checks
from finance.sync import SyncError

# ── Settings file ─────────────────────────────────────────────────────────────


def write_config(tmp_path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    "text, message",
    [
        ("sheets: [oops\n", "isn't valid YAML"),
        ("pages_per_chunk: three\n", "problem"),
        ("pages_per_chunk: 0\n", "problem"),
        ("sheets:\n  Food: abc\n", "problem"),
        ("review:\n  review_if_confidence: [maybe]\n", "problem"),
    ],
    ids=["broken-yaml", "word-instead-of-number", "zero-pages", "unknown-category", "unknown-confidence"],
)
def test_mistakes_in_settings_are_explained(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_settings(write_config(tmp_path, text))


def test_empty_settings_file_uses_safe_defaults(tmp_path):
    s = load_settings(write_config(tmp_path, ""))
    assert (
        s.sheets == {} and s.model == "external-provider" and s.review.review_if_confidence == ["low", "medium"]
    )


def test_paths_are_relative_to_the_settings_file(tmp_path):
    s = load_settings(write_config(tmp_path, "db_path: data/x.db\ninbox_dir: /tmp/absolute-inbox\n"))
    assert s.db_path == tmp_path / "data" / "x.db" and s.inbox_dir == Path("/tmp/absolute-inbox")


def test_settings_file_can_be_chosen_with_an_environment_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("WDMMG_CONFIG", str(write_config(tmp_path, "currency: EUR\n")))
    assert load_settings().currency == "EUR"


def test_example_settings_file_is_valid(tmp_path):
    example = Path(__file__).resolve().parent.parent / "config.example.yaml"
    s = load_settings(write_config(tmp_path, example.read_text()))
    assert s.sheets == {}, "blank IDs in the example mean 'not set up yet'"
    assert "Subscriptions" in s.keywords and s.offline_mode is True


def test_env_file_next_to_settings_is_loaded(tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    (tmp_path / ".env").write_text("TELEGRAM_CHAT_ID=12345\n")
    load_settings(write_config(tmp_path, ""))
    import os

    assert os.environ["TELEGRAM_CHAT_ID"] == "12345"
    monkeypatch.delenv("TELEGRAM_CHAT_ID")


# ── Monthly summary and Telegram ──────────────────────────────────────────────


@pytest.fixture
def months(settings, db, tmp_path):
    def _load(*plan):
        opening = 5000.0
        for i, (month, rows) in enumerate(plan):
            stmt = build_statement(month, opening=opening, rows=rows)
            with fake_claude({f"M-{i}": stmt}):
                pipeline.process_statement(write_pdf(stmt, tmp_path / f"m{i}.pdf", f"M-{i}"), settings, db)
            opening = stmt.closing_balance
        ledger.apply_user_review(db, ledger.review_queue(db), remember=False)

    return _load


SALARY = (1, "SALARY ACME CORP PAYROLL", None, 4000.0)


def test_summary_compares_with_last_month(months, db):
    months(
        ("2026-10", [SALARY, (5, "POS 4471 FRSHMRT*CTY", 100.0, None)]),
        (
            "2026-11",
            [SALARY, (5, "POS 4471 FRSHMRT*CTY", 150.0, None), (7, "TRF TO SAVINGS A/C 5678", 1000.0, None)],
        ),
    )
    text = summary.monthly_summary(db, "2026-11")
    assert (
        "Spent 150.00 (▲ 50% vs Oct)" in text
        and "Savings rate 25%" in text
        and "Top shops: Fresh Mart" in text
    )


def test_summary_of_a_first_month_has_no_comparison(months, db):
    months(("2026-11", [SALARY, (5, "POS 4471 FRSHMRT*CTY", 150.0, None)]))
    assert "vs" not in summary.monthly_summary(db, "2026-11")


def test_summary_without_income_skips_the_savings_rate(months, db):
    months(("2026-11", [(5, "POS 4471 FRSHMRT*CTY", 150.0, None)]))
    assert "Savings rate" not in summary.monthly_summary(db, "2026-11")


def test_summary_for_an_unknown_month(db):
    assert "No reviewed transactions" in summary.monthly_summary(db, "2030-01")


def test_telegram_message_is_sent(monkeypatch):
    sent = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(request, timeout):
        sent["url"], sent["body"] = request.full_url, json.loads(request.data)
        return Response()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(summary.urllib.request, "urlopen", fake_urlopen)
    summary.send_telegram("hello")
    assert sent == {
        "url": "https://api.telegram.org/bot123:abc/sendMessage",
        "body": {"chat_id": "42", "text": "hello"},
    }


def test_telegram_network_failure_is_explained(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def offline(request, timeout):
        raise OSError("network is unreachable")

    monkeypatch.setattr(summary.urllib.request, "urlopen", offline)
    with pytest.raises(summary.SendError, match="Couldn't reach Telegram"):
        summary.send_telegram("hello")


# ── Folder automation ─────────────────────────────────────────────────────────


def test_inbox_sorts_files_into_done_and_failed(settings, db):
    good = build_statement("2026-11")
    write_pdf(good, settings.inbox_dir / "nov.PDF", "W-1")
    write_pdf(good, settings.inbox_dir / "locked.pdf", "W-2", password="pw")
    (settings.inbox_dir / "notes.txt").write_text("not a pdf, ignored")
    lines = []
    with fake_claude({"W-1": good, "W-2": good}):
        assert watcher.process_inbox(settings, db, report=lines.append) == 2
    assert (settings.inbox_dir / "done" / "nov.PDF").exists()
    assert (settings.inbox_dir / "failed" / "locked.pdf").exists()
    assert (settings.inbox_dir / "notes.txt").exists()
    assert any("locked" in line for line in lines)


def test_auto_sync_runs_after_processing(settings, db, monkeypatch):
    settings.auto_sync = True
    calls = []
    monkeypatch.setattr(
        watcher, "sync", lambda db, settings: calls.append(1) or type("R", (), {"message": "Updated"})()
    )
    stmt = build_statement("2026-11")
    write_pdf(stmt, settings.inbox_dir / "nov.pdf", "W-1")
    lines = []
    with fake_claude({"W-1": stmt}):
        watcher.process_inbox(settings, db, report=lines.append)
    assert calls == [1] and any("Updated" in line for line in lines)


def test_auto_sync_failure_is_reported_not_crashed(settings, db, monkeypatch):
    settings.auto_sync = True

    def broken(db, settings):
        raise SyncError("Google said no")

    monkeypatch.setattr(watcher, "sync", broken)
    stmt = build_statement("2026-11")
    write_pdf(stmt, settings.inbox_dir / "nov.pdf", "W-1")
    lines = []
    with fake_claude({"W-1": stmt}):
        watcher.process_inbox(settings, db, report=lines.append)
    assert any("Sync failed: Google said no" in line for line in lines)


def test_watcher_only_picks_up_new_pdfs(tmp_path):
    import queue

    found: queue.Queue = queue.Queue()
    handler = watcher._InboxHandler(found)
    event = type("E", (), {})
    for path, is_dir in [
        (tmp_path / "a.pdf", False),
        (tmp_path / "b.txt", False),
        (tmp_path / "done" / "c.pdf", False),
        (tmp_path / "folder.pdf", True),
    ]:
        e = event()
        e.src_path, e.is_directory = str(path), is_dir
        handler.on_created(e)
    moved = event()
    moved.src_path, moved.dest_path, moved.is_directory = (
        str(tmp_path / "x.crdownload"),
        str(tmp_path / "d.pdf"),
        False,
    )
    handler.on_moved(moved)
    picked = []
    while not found.empty():
        picked.append(found.get().name)
    assert picked == ["a.pdf", "d.pdf"]


def test_watcher_waits_until_a_file_stops_growing(tmp_path, monkeypatch):
    """A PDF that is still being copied keeps growing; processing must wait until it's complete."""
    path = tmp_path / "s.pdf"
    path.write_bytes(b"x")
    still_copying = iter([b"yy", b"zzz"])  # the file grows during the first two pauses, then stops
    pauses = []

    def fake_sleep(seconds):
        pauses.append(seconds)
        with path.open("ab") as f:
            f.write(next(still_copying, b""))

    monkeypatch.setattr(watcher.time, "sleep", fake_sleep)
    watcher._wait_until_stable(path)
    assert path.stat().st_size == 6 and len(pauses) == 6, "it waited for 3 unchanged sizes in a row"


# ── Setup checklist ───────────────────────────────────────────────────────────


def test_checklist_when_nothing_is_set_up(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    checks = {c.label: c for c in run_checks(write_config(tmp_path, ""), online=False)}
    assert not checks["External AI key"].ok and "ANTHROPIC_API_KEY" in checks["External AI key"].fix
    assert not checks["Google Sheets"].ok
    assert not checks[".gitignore protects your secrets and data"].ok


def test_checklist_when_everything_is_set_up(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (tmp_path / "service_account.json").write_text(json.dumps({"client_email": "robot@x.iam"}))
    (tmp_path / ".gitignore").write_text(".env\nservice_account.json\n/data/\n")
    checks = run_checks(write_config(tmp_path, yaml.safe_dump({"sheets": {"Grocery": "abc"}})), online=False)
    assert all(c.ok for c in checks), [(c.label, c.fix) for c in checks if not c.ok]


def test_checklist_reports_a_broken_settings_file(tmp_path):
    checks = run_checks(write_config(tmp_path, "pages_per_chunk: lots\n"), online=False)
    assert not checks[-1].ok and checks[-1].label == "Settings file"
