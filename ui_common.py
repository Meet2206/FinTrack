"""Shared bits for every web page: settings, database connection and the sidebar."""

from __future__ import annotations

import sqlite3

import streamlit as st

from finance import ledger
from finance.config import ConfigError, Settings, load_settings
from finance.sync import SyncError, sync

STATUS_BADGE = {
    "uploaded": "⚪ Waiting",
    "processing": "🔵 Working…",
    "mismatch": "🔴 Numbers don't match",
    "ready": "🟡 Ready to sync",
    "synced": "🟢 In Google Sheets",
    "failed": "🔴 Failed",
}


def page(title: str, icon: str) -> tuple[Settings, sqlite3.Connection]:
    """Call first on every page: sets up the page, loads settings, connects, draws the sidebar."""
    st.set_page_config(page_title=f"{title} · Where Did My Money Go?", page_icon=icon, layout="wide")
    try:
        settings = load_settings()
    except ConfigError as e:
        st.error(str(e))
        st.info("Run `cp config.example.yaml config.yaml` in the project folder, then refresh this page.")
        st.stop()
    # A fresh connection on every run: Streamlit may use different threads, and SQLite
    # connections shouldn't be shared between threads. Opening one is cheap.
    db = ledger.connect(settings.db_path)
    sidebar(settings, db)
    return settings, db


def sidebar(settings: Settings, db: sqlite3.Connection) -> None:
    c = ledger.counts(db)
    with st.sidebar:
        st.markdown("### 💸 Where Did My Money Go?")
        col1, col2 = st.columns(2)
        col1.metric("To review", c["to_review"])
        col2.metric("Not synced", c["unsynced"])
        if c["mismatches"]:
            st.warning(f"{c['mismatches']} statement(s) don't add up. See Statements.")
        # Alerts remain available on Dashboard; don't repeat a persistent banner
        # in the sidebar every time Streamlit reruns or the page is refreshed.
        sheets_ready = bool(settings.sheets or settings.fintrack_spreadsheet_id)
        if st.button(
            "🔄 Sync to Google Sheets",
            width="stretch",
            disabled=not c["unsynced"] or not sheets_ready,
        ):
            with st.spinner("Updating Google Sheets…"):
                try:
                    st.success(sync(db, settings).message)
                except SyncError as e:
                    st.error(str(e))
        last = ledger.last_sync(db)
        if last:
            st.caption(f"Last sync: {last['finished_at'] or last['started_at']} ({last['status']})")
        if not settings.sheets and not settings.fintrack_spreadsheet_id:
            st.caption("Google Sheets not set up yet. See the Setup page.")


def money(x) -> str:
    return f"{x:,.2f}"
