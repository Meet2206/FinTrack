"""Is everything set up? Used by `python cli.py check` and the Setup page.

In plain English: a checklist that tests your settings file, Claude key, Google
robot account, spreadsheets, folders and .gitignore, and says how to fix each problem.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import anthropic

from finance.config import ConfigError, config_path, load_settings


@dataclass
class Check:
    ok: bool
    label: str
    fix: str = ""


def run_checks(path: str | Path | None = None, online: bool = True) -> list[Check]:
    checks: list[Check] = []
    v = sys.version_info
    checks.append(
        Check(
            v >= (3, 12),
            f"Python {v.major}.{v.minor}.{v.micro}",
            "Install Python 3.12 or newer (python.org).",
        )
    )

    cfg = Path(path) if path else config_path()
    try:
        settings = load_settings(cfg)
        checks.append(Check(True, f"Settings file {cfg.name} is valid"))
    except ConfigError as e:
        checks.append(Check(False, "Settings file", str(e)))
        return checks
    base = cfg.resolve().parent

    # AI or local parser
    if settings.offline_mode:
        checks.append(Check(True, "Offline mode", "Text-based PDFs are parsed locally; no API key or network is used."))
    elif os.environ.get("ANTHROPIC_API_KEY"):
        if online:
            try:
                anthropic.Anthropic().models.list(limit=1)  # free: just lists models
                checks.append(Check(True, "Claude API key works"))
            except anthropic.AuthenticationError:
                checks.append(
                    Check(
                        False,
                        "Claude API key",
                        "The key in .env was rejected. Create a new one at platform.claude.com → API Keys.",
                    )
                )
            except anthropic.APIError as e:
                checks.append(Check(False, "Claude API", f"Couldn't reach Claude: {e}"))
        else:
            checks.append(Check(True, "Claude API key is set (not tested offline)"))
    else:
        checks.append(
            Check(
                False,
                "Claude API key",
                "Add ANTHROPIC_API_KEY=sk-ant-… to .env (copy .env.example to .env first).",
            )
        )

    # Google
    if not settings.sheets and not settings.fintrack_spreadsheet_id:
        checks.append(
            Check(
                False,
                "Google Sheets",
                "Add a FinTrack spreadsheet ID or category spreadsheet IDs in config.yaml.",
            )
        )
    elif not settings.service_account_file.exists():
        checks.append(
            Check(
                False,
                "Google robot key",
                f"'{settings.service_account_file.name}' not found. "
                "Download it from Google Cloud (Backend.md → Setup, step 4).",
            )
        )
    elif online:
        from finance.sheets import check_access, robot_email

        checks.append(Check(True, f"Google robot account: {robot_email(settings.service_account_file)}"))
        for ok, message in check_access(settings):
            checks.append(Check(ok, message if ok else "Google Sheets", "" if ok else message))
    else:
        checks.append(Check(True, "Google robot key found (spreadsheets not tested offline)"))

    # Folders
    for folder in (
        settings.db_path.parent,
        settings.statements_dir,
        settings.inbox_dir,
        settings.backups_dir,
    ):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".write-test"
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            checks.append(Check(False, f"Folder {folder}", f"Can't write here: {e}"))
            break
    else:
        checks.append(Check(True, "Data folders are writable"))

    # Git safety
    gitignore = base / ".gitignore"
    needed = [".env", "service_account.json", "data/"]
    text = gitignore.read_text() if gitignore.exists() else ""
    missing = [n for n in needed if n not in text]
    checks.append(
        Check(
            not missing,
            ".gitignore protects your secrets and data",
            f"Add these lines to .gitignore: {', '.join(missing)}",
        )
    )
    return checks
