"""Setup: is everything connected? Plus AI costs and saved rules."""

from __future__ import annotations

import streamlit as st

from finance import ledger
from finance.setup_check import run_checks
from ui_common import page

settings, db = page("Setup", "🛠️")
st.title("🛠️ Setup & housekeeping")

st.subheader("Checklist")
if st.button("Run checks"):
    with st.spinner("Checking…"):
        for c in run_checks():
            if c.ok:
                st.write(f"✅ {c.label}")
            else:
                st.write(f"❌ **{c.label}**: {c.fix}")
else:
    st.caption(
        "Tests your Claude key, Google spreadsheets, folders and .gitignore. "
        "Step-by-step setup is in Backend.md → Setup."
    )

st.subheader("AI costs")
costs = ledger.costs_summary(db)
if costs.empty:
    st.caption("No AI calls yet.")
else:
    st.dataframe(
        costs,
        hide_index=True,
        width="stretch",
        column_config={"usd": st.column_config.NumberColumn("USD", format="$%.4f")},
    )
    st.caption(f"Total so far: ${costs.usd.sum():.4f}")

st.subheader("Saved shop rules")
rules = ledger.list_rules(db)
if rules.empty:
    st.caption("None yet. They're learned as statements are processed and as you fix categories.")
else:
    st.dataframe(rules, hide_index=True, width="stretch")
    key = st.selectbox("Forget a rule", [""] + list(rules.merchant_key))
    if key and st.button("Forget rule"):
        ledger.delete_rule(db, key)
        st.rerun()

st.subheader("Backups")
if st.button("Back up the database now"):
    st.success(f"Saved {ledger.backup(db, settings.backups_dir).name}")
