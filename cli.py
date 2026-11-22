"""Where Did My Money Go?: command line.

Run `python cli.py --help` to see every command.
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import anthropic
import typer
from rich.console import Console
from rich.table import Table

from finance import extract, ledger, pdf_tools, pipeline, summary, watcher
from finance.config import ConfigError, Settings, load_settings
from finance.setup_check import run_checks
from finance.sync import SyncError
from finance.sync import sync as run_sync

app = typer.Typer(
    help="💸 Where Did My Money Go? Turn bank statement PDFs into categorized Google Sheets.",
    no_args_is_help=True,
    add_completion=False,
)
password_app = typer.Typer(
    help="Manage saved PDF passwords (stored in the macOS Keychain).", no_args_is_help=True
)
app.add_typer(password_app, name="password")
console = Console()


def _setup() -> tuple[Settings, object]:
    try:
        settings = load_settings()
    except ConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(settings.logs_dir / "app.log", maxBytes=1_000_000, backupCount=5)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    return settings, ledger.connect(settings.db_path)


def _table(title: str, columns: list[str], rows) -> None:
    table = Table(title=title, show_lines=False)
    for c in columns:
        table.add_column(c)
    for r in rows:
        table.add_row(*["" if v is None else str(v) for v in r])
    console.print(table)


# ── Statements ───────────────────────────────────────────────────────────────


@app.command()
def process(
    pdf: Path = typer.Argument(..., exists=True, dir_okay=False, help="The statement PDF"),
    ask_password: bool = typer.Option(False, "--ask-password", help="Prompt for the PDF's password"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Read and check only; save nothing"),
):
    """Read, check and categorize one statement PDF."""
    settings, db = _setup()
    password = typer.prompt("PDF password", hide_input=True) if ask_password else None
    if dry_run:
        try:
            with console.status("Reading your statement… (usually 1–2 minutes)"):
                stmt, issues, pages = pipeline.read_statement(pdf, settings, password)
        except pdf_tools.WrongPassword:
            console.print("[red]This PDF is locked. Use --ask-password.[/red]")
            raise typer.Exit(1) from None
        except pipeline.NotAStatement:
            console.print("[red]This doesn't look like a bank or card statement.[/red]")
            raise typer.Exit(1) from None
        except extract.MissingAPIKey:
            console.print(
                "[red]No Claude API key found. Add ANTHROPIC_API_KEY to .env (see .env.example).[/red]"
            )
            raise typer.Exit(1) from None
        except anthropic.APIError as e:
            console.print(f"[red]Claude API problem: {e}[/red]")
            raise typer.Exit(1) from None
        _table(
            f"{stmt.bank_name or 'Statement'} ••{stmt.account_last4} · {stmt.period_start} → {stmt.period_end}"
            f" · {pages} pages",
            ["Date", "Description", "Out", "In", "Balance"],
            [(t.date, t.description, t.debit, t.credit, t.balance) for t in stmt.transactions],
        )
        if issues:
            console.print("[yellow]⚠️  The numbers don't match:[/yellow]")
            for issue in issues:
                console.print(f"   • {issue}")
        else:
            console.print("[green]✅ Balances match the statement to the cent.[/green]")
        return

    with console.status("Reading, checking and sorting your statement… (usually 1–2 minutes)"):
        result = pipeline.process_statement(pdf, settings, db, password)
    color = {"failed": "red", "mismatch": "yellow"}.get(result.status, "green")
    console.print(f"[{color}]{result.message}[/{color}]")
    for issue in result.issues:
        console.print(f"   • {issue}")
    if result.sorted_by:
        s = result.sorted_by
        console.print(f"Sorted by: saved rules {s['rule']}, keywords {s['keyword']}, AI {s['ai']}.")
    if result.status == "ready":
        console.print(
            "Next: [bold]python cli.py review[/bold] (or the Review page), then [bold]python cli.py sync[/bold]"
        )
    if result.status == "failed":
        raise typer.Exit(1)


@app.command()
def inbox():
    """Process every PDF waiting in data/inbox/ (good for a scheduled job)."""
    settings, db = _setup()
    count = watcher.process_inbox(settings, db, report=console.print)
    if not count:
        console.print(f"Nothing in {settings.inbox_dir}.")


@app.command()
def watch():
    """Keep watching data/inbox/ and process new PDFs automatically (Ctrl+C to stop)."""
    settings, _ = _setup()
    watcher.watch(settings, report=console.print)


@app.command()
def status():
    """Every statement and where it's up to."""
    _, db = _setup()
    df = ledger.list_statements(db)
    if df.empty:
        console.print("No statements yet. Try: python cli.py process statement.pdf")
        return
    icons = {
        "ready": "🟡",
        "synced": "🟢",
        "mismatch": "🔴",
        "failed": "🔴",
        "processing": "🔵",
        "uploaded": "⚪",
    }
    _table(
        "Statements",
        ["ID", "File", "Account", "Period", "Status", "Rows", "To review", "Not synced"],
        [
            (
                r.id,
                r.file_name,
                r.account,
                f"{r.period_start or '?'} → {r.period_end or '?'}",
                f"{icons.get(r.status, '')} {r.status}",
                r.rows,
                r.to_review,
                r.unsynced,
            )
            for r in df.itertuples()
        ],
    )
    for r in df[df.status.isin(["failed", "mismatch"])].itertuples():
        detail = r.error or "; ".join(json.loads(r.issues or "[]"))
        console.print(f"[yellow]#{r.id} {r.file_name}:[/yellow] {detail}")


@app.command()
def review():
    """List rows waiting for your OK (approve them on the Review page of the web app)."""
    _, db = _setup()
    df = ledger.review_queue(db)
    if df.empty:
        console.print("Nothing to review 🎉")
        return
    _table(
        f"{len(df)} rows to review",
        ["Date", "Description", "Amount", "Suggested", "Confidence"],
        [(r.txn_date, r.description, f"{r.amount:,.2f}", r.category, r.confidence) for r in df.itertuples()],
    )
    console.print(
        "Approve or fix them in the web app: streamlit run app.py --server.address localhost → Review"
    )


@app.command()
def approve(statement_id: int):
    """Accept a statement whose numbers didn't match (only after checking it against the PDF!)."""
    settings, db = _setup()
    s = ledger.get_statement(db, statement_id)
    if not s:
        console.print(f"[red]No statement #{statement_id}.[/red]")
        raise typer.Exit(1)
    if s["status"] != "mismatch":
        console.print(f"Statement #{statement_id} is '{s['status']}', so there's nothing to approve.")
        return
    ledger.approve_statement(db, statement_id, settings.review.review_if_confidence)
    console.print(f"[green]Approved statement #{statement_id}.[/green] Next: python cli.py sync")


@app.command()
def forget(statement_id: int, yes: bool = typer.Option(False, "--yes", help="Don't ask for confirmation")):
    """Delete a statement, its rows and its stored PDF, then refresh the affected sheets."""
    settings, db = _setup()
    s = ledger.get_statement(db, statement_id)
    if not s:
        console.print(f"[red]No statement #{statement_id}.[/red]")
        raise typer.Exit(1)
    if not yes and not typer.confirm(
        f"Delete statement #{statement_id} ({s['file_name']}) and all its rows?"
    ):
        raise typer.Abort()
    tabs, stored = ledger.forget_statement(db, statement_id)
    if stored:
        Path(stored).unlink(missing_ok=True)
    console.print(f"Deleted statement #{statement_id}.")
    if tabs:
        try:
            console.print(run_sync(db, settings, extra_tabs=tabs).message)
        except SyncError as e:
            console.print(f"[yellow]Sheets not refreshed: {e}[/yellow] Run: python cli.py rebuild --all")


# ── Google Sheets ────────────────────────────────────────────────────────────


@app.command()
def sync():
    """Update Google Sheets with every approved change."""
    settings, db = _setup()
    try:
        with console.status("Updating Google Sheets…"):
            result = run_sync(db, settings)
    except SyncError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e
    console.print(f"[green]{result.message}[/green]")
    waiting = ledger.counts(db)["to_review"]
    if waiting:
        console.print(f"({waiting} row(s) are still waiting for review and weren't synced.)")


@app.command()
def rebuild(
    month: str = typer.Argument(None, help="e.g. 2026-11"),
    all_months: bool = typer.Option(False, "--all", help="Rebuild every month"),
):
    """Rebuild Google Sheets tabs from the database (fixes anything that looks off)."""
    settings, db = _setup()
    if not month and not all_months:
        console.print("Give a month (e.g. 2026-11) or --all.")
        raise typer.Exit(1)
    marked = ledger.mark_for_resync(db, None if all_months else month)
    console.print(f"Marked {marked} row(s) for rebuilding.")
    sync()


# ── Information ──────────────────────────────────────────────────────────────


@app.command()
def alerts():
    """Open alerts (double charges, price increases…)."""
    _, db = _setup()
    df = ledger.open_alerts(db)
    if df.empty:
        console.print("No open alerts 😌")
        return
    _table(
        "Alerts",
        ["ID", "Kind", "Message", "When"],
        [(r.id, r.kind.replace("_", " "), r.message, r.created_at) for r in df.itertuples()],
    )


@app.command("summary")
def summary_cmd(
    month: str = typer.Option(None, "--month", help="e.g. 2026-11 (default: latest)"),
    send: bool = typer.Option(False, "--send", help="Also send it to Telegram"),
):
    """A short monthly summary (optionally sent to Telegram)."""
    _, db = _setup()
    month = month or summary.latest_month(db)
    if not month:
        console.print("No transactions yet.")
        return
    text = summary.monthly_summary(db, month)
    console.print(text)
    if send:
        try:
            summary.send_telegram(text)
            console.print("[green]Sent to Telegram.[/green]")
        except summary.SendError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def costs(month: str = typer.Option(None, "--month", help="e.g. 2026-11 (default: all time)")):
    """What the AI has cost so far."""
    _, db = _setup()
    df = ledger.costs_summary(db, month)
    if df.empty:
        console.print("No AI calls yet.")
        return
    _table(
        f"AI costs {month or '(all time)'}",
        ["Purpose", "Calls", "Tokens in", "Tokens out", "USD"],
        [
            (r.purpose, r.calls, f"{r.tokens_in:,}", f"{r.tokens_out:,}", f"${r.usd:.4f}")
            for r in df.itertuples()
        ],
    )
    console.print(f"Total: [bold]${df.usd.sum():.4f}[/bold]")


@app.command()
def rules(remove: str = typer.Option(None, "--remove", help="Forget the rule with this merchant key")):
    """Shops the app has learned."""
    _, db = _setup()
    if remove:
        ledger.delete_rule(db, remove)
        console.print(f"Removed rule '{remove}'.")
        return
    df = ledger.list_rules(db)
    if df.empty:
        console.print("No rules yet. They're learned as you process statements and fix categories.")
        return
    _table(
        "Saved shop rules",
        ["Key", "Shop", "Category", "Source", "Used"],
        [(r.merchant_key, r.merchant, r.category, r.source, r.times_used) for r in df.itertuples()],
    )


@app.command()
def backup():
    """Back up the database to data/backups/."""
    settings, db = _setup()
    console.print(f"Saved {ledger.backup(db, settings.backups_dir)}")


@app.command()
def check(offline: bool = typer.Option(False, "--offline", help="Skip network checks")):
    """Check keys, spreadsheets, folders and .gitignore."""
    failed = 0
    for c in run_checks(online=not offline):
        if c.ok:
            console.print(f"✅ {c.label}")
        else:
            failed += 1
            console.print(f"❌ {c.label} → {c.fix}")
    if failed:
        raise typer.Exit(1)
    console.print("[green]All good. Run: streamlit run app.py --server.address localhost[/green]")


# ── Passwords ────────────────────────────────────────────────────────────────


@password_app.command("add")
def password_add(name: str = typer.Argument(..., help="A short name, e.g. mainbank")):
    """Save a PDF password in the macOS Keychain. Saved passwords are tried automatically."""
    secret = typer.prompt(f"Password for {name}", hide_input=True, confirmation_prompt=True)
    pdf_tools.save_password(name, secret)
    console.print(f"Saved '{name}'. Locked statements will now open automatically.")


@password_app.command("remove")
def password_remove(name: str):
    """Remove a saved PDF password."""
    removed = pdf_tools.remove_password(name)
    console.print(f"Removed '{name}'." if removed else f"No saved password called '{name}'.")


@password_app.command("list")
def password_list():
    """Names of saved PDF passwords (never the passwords themselves)."""
    names = pdf_tools.saved_password_names()
    console.print("\n".join(names) if names else "No saved passwords.")


if __name__ == "__main__":
    app()
