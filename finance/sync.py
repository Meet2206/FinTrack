"""Decide which Google Sheets tabs to rebuild, then rebuild them.

In plain English: sync looks at every approved row that changed since last time and
works out which (category, month) tabs are affected, including the tab a row moved
away from. It rebuilds only those tabs and refreshes the Summary tabs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from finance import ledger
from finance.config import CATEGORIES
from finance.sheets import SheetAccessError, SheetsMirror


class SyncError(Exception):
    pass


@dataclass
class SyncResult:
    tabs: list[tuple[str, str]] = field(default_factory=list)
    rows: int = 0

    @property
    def message(self) -> str:
        if not self.tabs and not self.rows:
            return "Google Sheets are already up to date."
        names = ", ".join(f"{c} {m}" for c, m in self.tabs) or "no sheet tabs"
        return f"Updated {len(self.tabs)} tab(s): {names}. {self.rows} row(s) synced."


def sync(
    db, settings, mirror_factory=SheetsMirror, extra_tabs: set[tuple[str, str]] | frozenset = frozenset()
) -> SyncResult:
    if not settings.sheets and not settings.fintrack_spreadsheet_id:
        raise SyncError(
            "Google Sheets aren't set up yet: add fintrack_spreadsheet_id or spreadsheet IDs "
            "under 'sheets:' in config.yaml."
        )
    single_book = bool(settings.fintrack_spreadsheet_id)
    enabled = set(CATEGORIES) - {"Not an expense"} if single_book else set(settings.sheets)
    changed = ledger.rows_needing_sync(db)  # approved rows with synced_at IS NULL

    tabs = {(r["category"], r["month"]) for r in changed if r["category"] in enabled}
    tabs |= {
        (r["synced_category"], r["synced_month"] or r["month"])  # the tab a row moved away from
        for r in changed
        if r["synced_category"] in enabled
    }
    tabs |= {t for t in extra_tabs if t[0] in enabled}

    if not tabs:
        ledger.mark_synced(db, [r["id"] for r in changed])  # e.g. only "Not an expense" rows
        ledger.refresh_statement_statuses(db)
        return SyncResult([], len(changed))

    ledger.backup(db, settings.backups_dir)
    run_id = ledger.start_sync_run(db)
    try:
        mirror = mirror_factory(settings)
        if single_book:
            for month in sorted({m for _, m in tabs}):
                rows = [
                    [category, *row]
                    for category in sorted(enabled)
                    for row in ledger.rows_for_tab(db, category, month)
                ]
                mirror.rebuild_fintrack_month(month, rows)
            mirror.rebuild_fintrack_summary(db, sorted({m for _, m in tabs}), enabled)
        else:
            for category, month in sorted(tabs):
                mirror.rebuild_tab(category, month, ledger.rows_for_tab(db, category, month))
            for category in sorted({c for c, _ in tabs}):
                mirror.rebuild_summary(category, ledger.months_for(db, category))
    except SheetAccessError as e:
        ledger.finish_sync_run(db, run_id, "failed", error=str(e))
        raise SyncError(str(e)) from e
    except Exception as e:  # network, rate limits, Google errors: record, then explain
        ledger.finish_sync_run(db, run_id, "failed", error=f"{type(e).__name__}: {e}")
        raise SyncError(
            f"Google Sheets update failed ({type(e).__name__}: {e}). It's safe to run sync again."
        ) from e

    ledger.mark_synced(db, [r["id"] for r in changed])
    ledger.finish_sync_run(db, run_id, "ok", tabs=sorted(tabs), rows=len(changed))
    ledger.refresh_statement_statuses(db)
    return SyncResult(sorted(tabs), len(changed))
