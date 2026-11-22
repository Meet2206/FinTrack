"""Transactions: browse and fix any row (changes flow to Google Sheets on the next sync)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from finance import ledger, pipeline
from finance.config import CATEGORIES
from ui_common import page

settings, db = page("Transactions", "🧾")
st.title("🧾 Transactions")

months = ledger.months(db)
if not months:
    st.info("No transactions yet. Upload a statement first.")
    st.stop()

c1, c2, c3 = st.columns([1, 1, 2])
month = c1.selectbox("Month", ["All"] + months)
category = c2.selectbox("Category", ["All"] + CATEGORIES)
search = c3.text_input("Search description or shop")

before = ledger.transactions_frame(
    db, None if month == "All" else month, None if category == "All" else category, search or None
)
st.caption(
    f"{len(before)} row(s). Edit **Shop**, **Category** or **Amount**, then save. "
    "Edit the amount only to fix a misread number (compare with the PDF)."
)
after = st.data_editor(
    before,
    column_config={
        "id": None,
        "statement_id": None,
        "row_number": None,
        "synced_at": None,
        "txn_date": st.column_config.TextColumn("Date"),
        "description": st.column_config.TextColumn("Description (as printed)", width="large"),
        "merchant": st.column_config.TextColumn("Shop"),
        "amount": st.column_config.NumberColumn("Amount (+ out / − in)", format="%.2f"),
        "category": st.column_config.SelectboxColumn("Category", options=CATEGORIES),
        "confidence": st.column_config.TextColumn("Confidence"),
        "category_source": st.column_config.TextColumn("Decided by"),
        "needs_review": st.column_config.CheckboxColumn("Needs review"),
        "review_reason": st.column_config.TextColumn("Why"),
    },
    disabled=["txn_date", "description", "confidence", "category_source", "needs_review", "review_reason"],
    hide_index=True,
    width="stretch",
    key="transactions_editor",
)
remember = st.checkbox("Remember category changes for these shops", value=True)
if st.button("Save changes", type="primary"):
    changed, statements = ledger.apply_user_edits(db, before, pd.DataFrame(after), remember)
    for sid in statements:  # an amount was fixed: re-check that statement's math
        issues = pipeline.recheck_statement(db, settings, sid)
        if issues:
            st.warning(f"Statement #{sid} still doesn't add up: " + "; ".join(issues[:3]))
        else:
            st.success(f"Statement #{sid} now matches the bank's balances ✅")
    st.success(
        f"Saved {changed} change(s). Use **Sync to Google Sheets** in the sidebar to update the sheets."
    )
