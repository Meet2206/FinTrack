"""Statements: every upload, its status, and fixes for mismatches and failures."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from finance import ledger, pipeline
from ui_common import STATUS_BADGE, page

settings, db = page("Statements", "📄")
st.title("📄 Statements")

df = ledger.list_statements(db)
if df.empty:
    st.info("No statements yet. Upload one on the home page.")
    st.stop()

st.dataframe(
    df.assign(
        status=df.status.map(STATUS_BADGE),
        period=df.period_start.fillna("?") + " → " + df.period_end.fillna("?"),
    )[["id", "file_name", "account", "period", "status", "rows", "to_review", "unsynced", "uploaded_at"]],
    hide_index=True,
    width="stretch",
    column_config={
        "id": "ID",
        "file_name": "File",
        "to_review": "To review",
        "unsynced": "Not synced",
        "uploaded_at": "Uploaded",
    },
)

for s in df[df.status.isin(["mismatch", "failed"])].itertuples():
    with st.container(border=True):
        st.markdown(f"**#{s.id} · {s.file_name}**: {STATUS_BADGE[s.status]}")
        stored = Path(s.stored_path) if s.stored_path else None
        if s.status == "mismatch":
            for issue in json.loads(s.issues or "[]"):
                st.write("•", issue)
            st.caption(
                "Open the PDF and compare. If the AI misread an amount, fix it on the Transactions page "
                "and this statement is re-checked automatically. If the PDF itself is odd but the rows "
                "are right, approve it."
            )
            if st.button("I've checked it: approve", key=f"approve-{s.id}"):
                ledger.approve_statement(db, s.id, settings.review.review_if_confidence)
                st.rerun()
        else:
            st.error(s.error or "Unknown error")
            pw = st.text_input("Password (if it's locked)", type="password", key=f"pw-{s.id}")
            if stored and stored.exists() and st.button("Try again", key=f"retry-{s.id}"):
                with st.spinner("Trying again…"):
                    result = pipeline.process_statement(stored, settings, db, pw or None)
                (st.error if result.status == "failed" else st.success)(result.message)
                st.rerun()
        if stored and stored.exists():
            st.download_button(
                "Download the PDF to compare",
                stored.read_bytes(),
                file_name=s.file_name,
                mime="application/pdf",
                key=f"dl-{s.id}",
            )

with st.expander("🗑️ Forget a statement"):
    choice = st.selectbox(
        "Statement", df.id, format_func=lambda i: f"#{i} · {df.set_index('id').file_name[i]}"
    )
    sure = st.checkbox("Yes, delete this statement, its rows and its stored PDF")
    if st.button("Forget it", disabled=not sure):
        tabs, stored_path = ledger.forget_statement(db, int(choice))
        if stored_path:
            Path(stored_path).unlink(missing_ok=True)
        if tabs and settings.sheets:
            from finance.sync import SyncError, sync

            try:
                sync(db, settings, extra_tabs=tabs)
            except SyncError as e:
                st.warning(f"Deleted, but the sheets weren't refreshed: {e}")
        st.rerun()
