"""Command line: every command, run the way you'd type it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import cli
from finance import ledger, pdf_tools, sheets
from finance.config import load_settings
from finance.demo import build_statement, fake_claude, write_pdf
from tests.fake_gspread import FakeClient

runner = CliRunner()


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A project folder with its own config.yaml (no Google sheets yet) and a fake November statement."""
    config = {
        "db_path": "data/ledger.db",
        "statements_dir": "data/statements",
        "backups_dir": "data/backups",
        "inbox_dir": "data/inbox",
        "logs_dir": "data/logs",
        "sheets": {},
        "keywords": {"Travel": ["fuel", "airways", "hotel"], "Not an expense": ["salary", "payroll"]},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config))
    (tmp_path / ".gitignore").write_text(".env\nservice_account.json\n/data/\n")
    monkeypatch.setenv("WDMMG_CONFIG", str(tmp_path / "config.yaml"))
    monkeypatch.setenv("COLUMNS", "200")  # wide tables, nothing truncated
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    stmt = build_statement("2026-11")
    pdf = write_pdf(stmt, tmp_path / "nov.pdf", "CLI-1")
    return {"root": tmp_path, "pdf": pdf, "stmt": stmt, "truth": {"CLI-1": stmt}}


def run(*args, input=None):
    return runner.invoke(cli.app, list(args), input=input)


def process(env, *extra):
    with fake_claude(env["truth"]):
        return run("process", str(env["pdf"]), *extra)


def db_for(env):
    return ledger.connect(load_settings(env["root"] / "config.yaml").db_path)


def test_help_lists_every_command():
    out = run("--help").output
    for command in (
        "process",
        "inbox",
        "watch",
        "status",
        "review",
        "approve",
        "forget",
        "sync",
        "rebuild",
        "alerts",
        "summary",
        "costs",
        "rules",
        "backup",
        "check",
        "password",
    ):
        assert command in out


def test_process_reads_checks_and_sorts(env):
    result = process(env)
    assert result.exit_code == 0, result.output
    assert "Balances match" in result.output and "Sorted by" in result.output
    assert "python cli.py sync" in result.output


def test_dry_run_saves_nothing(env):
    with fake_claude(env["truth"]):
        result = run("process", str(env["pdf"]), "--dry-run")
    assert result.exit_code == 0 and "FRSHMRT" in result.output and "Balances match" in result.output
    assert db_for(env).execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_missing_file_is_rejected_before_anything_runs(env):
    result = run("process", str(env["root"] / "nope.pdf"))
    assert result.exit_code != 0


def test_locked_pdf_asks_for_the_password(env):
    write_pdf(env["stmt"], env["pdf"], "CLI-1", password="pw-1")
    assert process(env).exit_code == 1
    with fake_claude(env["truth"]):
        result = run("process", str(env["pdf"]), "--ask-password", input="pw-1\n")
    assert result.exit_code == 0 and "Balances match" in result.output


def test_information_commands_after_processing(env):
    process(env)
    status = run("status").output
    assert "nov.pdf" in status and "ready" in status
    assert "rows to review" in run("review").output
    assert "Double charge" in run("alerts").output
    summary = run("summary").output
    assert "November 2026" in summary and "Spent" in summary
    assert "extract" in run("costs").output and "categorize" in run("costs").output
    assert "Fresh Mart" in run("rules").output
    assert "Saved" in run("backup").output


def test_commands_on_an_empty_database_explain_what_to_do(env):
    assert "No statements yet" in run("status").output
    assert "Nothing to review" in run("review").output
    assert "No open alerts" in run("alerts").output
    assert "No transactions yet" in run("summary").output
    assert "No AI calls yet" in run("costs").output


def test_sync_without_google_set_up_fails_with_instructions(env):
    process(env)
    result = run("sync")
    assert result.exit_code == 1 and "config.yaml" in result.output


def test_sync_and_rebuild_with_google(env, monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(sheets.gspread, "service_account", lambda filename, http_client=None: client)
    cfg = yaml.safe_load((env["root"] / "config.yaml").read_text())
    cfg["sheets"] = {"Grocery": "g", "Travel": "t", "Subscriptions": "s", "Investments": "i", "Savings": "v"}
    (env["root"] / "config.yaml").write_text(yaml.safe_dump(cfg))
    (env["root"] / "service_account.json").write_text(json.dumps({"client_email": "robot@x.iam"}))
    process(env)
    first = run("sync")
    assert first.exit_code == 0 and "Updated" in first.output and "still waiting for review" in first.output
    assert "already up to date" in run("sync").output
    assert run("rebuild").exit_code == 1
    rebuilt = run("rebuild", "--all")
    assert rebuilt.exit_code == 0 and "Marked" in rebuilt.output and "Updated" in rebuilt.output


def test_approve_only_applies_to_mismatched_statements(env):
    process(env)
    assert "nothing to approve" in run("approve", "1").output
    assert run("approve", "99").exit_code == 1


def test_approve_a_mismatched_statement(env):
    misread = env["stmt"].model_copy(deep=True)
    misread.transactions[2].debit = 1.0
    with fake_claude({"CLI-1": misread}):
        result = run("process", str(env["pdf"]))
    assert "doesn't match" in result.output
    assert "Approved" in run("approve", "1").output
    assert ledger.get_statement(db_for(env), 1)["status"] == "ready"


def test_forget_deletes_the_statement_rows_and_pdf(env):
    process(env)
    stored = Path(ledger.get_statement(db_for(env), 1)["stored_path"])
    assert stored.exists()
    result = run("forget", "1", "--yes")
    assert result.exit_code == 0 and "Deleted" in result.output
    assert not stored.exists()
    assert db_for(env).execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0


def test_forget_asks_before_deleting(env):
    process(env)
    result = run("forget", "1", input="n\n")
    assert result.exit_code != 0
    assert ledger.get_statement(db_for(env), 1) is not None


def test_rules_can_be_removed(env):
    process(env)
    assert "Removed" in run("rules", "--remove", "pos frshmrt cty").output
    assert "pos frshmrt cty" not in ledger.merchant_rules(db_for(env))


def test_inbox_processes_every_waiting_pdf(env):
    inbox = env["root"] / "data" / "inbox"
    write_pdf(env["stmt"], inbox / "good.pdf", "CLI-1")
    (inbox / "broken.pdf").write_bytes(b"%PDF-1.7 truncated")
    with fake_claude(env["truth"]):
        result = run("inbox")
    assert "good.pdf" in result.output and "broken.pdf" in result.output
    assert (inbox / "done" / "good.pdf").exists() and (inbox / "failed" / "broken.pdf").exists()
    assert "Nothing in" in run("inbox").output


def test_summary_send_without_telegram_set_up(env, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    process(env)
    result = run("summary", "--send")
    assert result.exit_code == 1 and "TELEGRAM_BOT_TOKEN" in result.output


def test_check_offline_lists_what_is_missing(env):
    result = run("check", "--offline")
    assert result.exit_code == 1
    assert "External AI key" in result.output and "Google Sheets" in result.output
    assert "Data folders are writable" in result.output


def test_missing_settings_file_is_explained(env, monkeypatch):
    monkeypatch.setenv("WDMMG_CONFIG", str(env["root"] / "missing.yaml"))
    result = run("status")
    assert result.exit_code == 1 and "cp config.example.yaml" in " ".join(result.output.split())


def test_password_add_list_remove(env, monkeypatch):
    monkeypatch.setattr(pdf_tools.keyring, "delete_password", lambda service, name: None)
    assert run("password", "add", "mainbank", input="secret\nsecret\n").exit_code == 0
    assert "mainbank" in run("password", "list").output
    assert "Removed" in run("password", "remove", "mainbank").output
    assert "No saved passwords" in run("password", "list").output
