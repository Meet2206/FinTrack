"""Setup: is everything connected? Plus saved rules and backups."""

from __future__ import annotations

import streamlit as st

from finance import ledger
from finance.setup_check import run_checks
from ui_common import page

settings, db = page("Setup", "🛠️")
st.title("🛠️ Setup & housekeeping")

if settings.google_client_id:
    st.info("Google OAuth client ID is saved. Google sign-in or a service-account JSON is still required for sync.")
if settings.fintrack_spreadsheet_id:
    st.success("Single-workbook mode is configured for FinTrack.")
else:
    st.warning("To enable Google saving, add the FinTrack Sheet ID to config.yaml and provide Google authorization.")

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
        "Tests local parsing, Google spreadsheets, folders and .gitignore. "
        "Step-by-step setup is in Backend.md → Setup."
    )

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
