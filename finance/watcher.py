"""Automation: process PDFs dropped into data/inbox/.

In plain English: `python cli.py inbox` processes whatever is in the folder once
(good for a scheduled job). `python cli.py watch` keeps running and processes new
PDFs the moment they appear. Processed files move to inbox/done/ (or inbox/failed/).
"""

from __future__ import annotations

import queue
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from finance import ledger, pipeline
from finance.sync import SyncError, sync


def _wait_until_stable(path: Path, checks: int = 3, pause: float = 1.0) -> None:
    """Wait until the file stops growing (it may still be copying)."""
    last, stable = -1, 0
    while stable < checks:
        size = path.stat().st_size if path.exists() else -1
        stable = stable + 1 if size == last and size > 0 else 0
        last = size
        time.sleep(pause)


def inbox_pdfs(inbox: Path) -> list[Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")


def process_file(path: Path, settings, db, wait: bool = True) -> tuple[pipeline.Result, str | None]:
    """Process one inbox file, move it out of the inbox, and sync if auto_sync is on."""
    if wait:
        _wait_until_stable(path)
    result = pipeline.process_statement(path, settings, db)
    target = settings.inbox_dir / ("failed" if result.status == "failed" else "done")
    target.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(target / path.name))

    sync_message = None
    if settings.auto_sync and result.status in ("ready", "mismatch"):
        try:
            sync_message = sync(db, settings).message
        except SyncError as e:
            sync_message = f"Sync failed: {e}"
    return result, sync_message


def process_inbox(settings, db, report: Callable[[str], None] = print) -> int:
    files = inbox_pdfs(settings.inbox_dir)
    for path in files:
        result, sync_message = process_file(path, settings, db, wait=False)
        report(f"{path.name}: {result.message}")
        if sync_message:
            report(f"  ↳ {sync_message}")
    return len(files)


class _InboxHandler(FileSystemEventHandler):
    def __init__(self, found: queue.Queue):
        self.found = found

    def _maybe_add(self, raw_path) -> None:
        path = Path(str(raw_path))
        if path.suffix.lower() == ".pdf" and path.parent.name not in ("done", "failed"):
            self.found.put(path)

    def on_created(self, event):
        if not event.is_directory:
            self._maybe_add(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._maybe_add(event.dest_path)


def watch(settings, report: Callable[[str], None] = print) -> None:
    """Keep watching the inbox until Ctrl+C. Database work happens on this (main) thread."""
    db = ledger.connect(settings.db_path)
    process_inbox(settings, db, report)  # anything already waiting
    found: queue.Queue = queue.Queue()
    observer = Observer()
    observer.schedule(_InboxHandler(found), str(settings.inbox_dir), recursive=False)
    observer.start()
    report(f"👀 Watching {settings.inbox_dir}. Drop statement PDFs in. Press Ctrl+C to stop.")
    try:
        while True:
            try:
                path = found.get(timeout=1)
            except queue.Empty:
                continue
            if path.exists():
                result, sync_message = process_file(path, settings, db)
                report(f"{path.name}: {result.message}")
                if sync_message:
                    report(f"  ↳ {sync_message}")
    except KeyboardInterrupt:
        report("Stopped watching.")
    finally:
        observer.stop()
        observer.join()
