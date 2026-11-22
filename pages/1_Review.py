"""Review queue: rows the AI wasn't sure about."""

from __future__ import annotations

import streamlit as st

from finance import ledger
from finance.config import CATEGORIES
from ui_common import page

settings, db = page("Review", "👀")
st.title("👀 Review")

rows = ledger.review_queue(db)
if rows.empty:
    st.success("Nothing to review 🎉")
    st.caption("Statements whose numbers don't add up are handled on the Statements page.")
    st.stop()

st.write(f"**{len(rows)} row(s)** need a quick look. Change the category if it's wrong, then approve.")
edited = st.data_editor(
    rows,
    column_config={
        "id": None,  # hide the fingerprint column
        "txn_date": st.column_config.TextColumn("Date"),
        "description": st.column_config.TextColumn("Description (as printed)", width="large"),
        "merchant": st.column_config.TextColumn("Shop"),
        "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
        "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES, required=True),
        "confidence": st.column_config.TextColumn("AI was"),
        "review_reason": st.column_config.TextColumn("Why it's here"),
    },
    disabled=["txn_date", "description", "amount", "confidence", "review_reason"],
    hide_index=True,
    width="stretch",
    key="review_editor",
)
remember = st.checkbox(
    "Remember my choices for these shops",
    value=True,
    help="Next time, these shops are sorted instantly, with no AI and no review.",
)
if st.button("Approve all ✓", type="primary"):
    count = ledger.apply_user_review(db, edited, remember=remember)
    st.success(f"Saved {count} row(s). Use **Sync to Google Sheets** in the sidebar when you're ready.")
    st.rerun()
