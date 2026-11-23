"""Web app: Upload page (home).

Start it with:  streamlit run app.py --server.address localhost
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from finance import ledger, pdf_tools, pipeline
from finance.suggestions import suggestions_for_frame
from finance.sync import SyncError, sync
from ui_common import page

settings, db = page("Upload", "💸")

st.title("💸 Upload a statement")
st.caption(
    "Drop your bank or credit card statement PDF. It's read, checked against the bank's own "
    "balances, and sorted into categories. Nothing goes to Google Sheets until you sync."
)

files = st.file_uploader("Statement PDF(s)", type="pdf", accept_multiple_files=True)
col1, col2 = st.columns([2, 1])
password = col1.text_input(
    "Password (only if the PDF is locked)",
    type="password",
    help="Many banks lock emailed statements, e.g. with your date of birth. "
    "The PDF is unlocked on this computer; the password is never sent anywhere.",
)
remember = col2.checkbox("Remember this password", value=bool(password), disabled=not password)
name = col2.text_input("Save it as", value="mybank", disabled=not (password and remember))

if files and st.button("Process ▶", type="primary"):
    if password and remember:
        pdf_tools.save_password(name, password)
    for uploaded in files:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / uploaded.name
            path.write_bytes(uploaded.getvalue())
            with st.status(f"Reading **{uploaded.name}**… (usually 1–2 minutes)", expanded=False) as box:
                result = pipeline.process_statement(path, settings, db, password or None)
                box.update(
                    label=f"{uploaded.name}: {result.status}",
                    state="error" if result.status == "failed" else "complete",
                )
        if result.status == "failed":
            st.error(f"**{uploaded.name}**: {result.message}")
        elif result.status == "mismatch":
            st.warning(f"**{uploaded.name}**: {result.message}")
            for issue in result.issues:
                st.write("•", issue)
            st.page_link("pages/4_Statements.py", label="Check it on the Statements page →")
        else:
            st.success(f"**{uploaded.name}**: {result.message}")

        if result.status != "failed" and result.statement_id:
            rows = ledger.transactions_frame(db, statement_id=result.statement_id)
            if not rows.empty:
                view = rows.copy()
                view["Money out"] = view.amount.clip(lower=0)
                view["Money in"] = (-view.amount).clip(lower=0)
                view["Net"] = view.amount
                category_totals = (
                    view.groupby("category", dropna=False)
                    .agg(
                        **{
                            "Money out": ("Money out", "sum"),
                            "Money in": ("Money in", "sum"),
                            "Net": ("Net", "sum"),
                            "Transactions": ("id", "count"),
                        }
                    )
                    .reset_index()
                    .rename(columns={"category": "Category"})
                )
                st.subheader("Finances by category")
                st.dataframe(category_totals, hide_index=True, width="stretch")
                suggestions = suggestions_for_frame(view, settings.currency)
                if suggestions:
                    st.subheader("💡 Money suggestions")
                    st.caption("These are local estimates based only on this statement—not financial advice.")
                    for suggestion in suggestions:
                        st.info(f"**{suggestion['title']}**\n\n{suggestion['text']}")
                st.subheader("All transactions")
                st.dataframe(
                    view[
                        [
                            "txn_date",
                            "merchant",
                            "description",
                            "Money out",
                            "Money in",
                            "Net",
                            "category",
                            "confidence",
                        ]
                    ].rename(
                        columns={
                            "txn_date": "Date",
                            "merchant": "Merchant",
                            "description": "Description",
                            "category": "Category",
                            "confidence": "Confidence",
                        }
                    ),
                    hide_index=True,
                    width="stretch",
                    height=420,
                )
        if result.status != "failed" and result.sorted_by:
            s = result.sorted_by
            st.caption(f"Sorted by saved rules: {s['rule']} · keywords: {s['keyword']} · AI: {s['ai']}")
        if result.status != "failed" and result.to_review:
            st.page_link("pages/1_Review.py", label=f"Review {result.to_review} row(s) →", icon="👀")
        if result.status == "ready" and settings.auto_sync and settings.sheets and not result.to_review:
            try:
                sync_result = sync(db, settings)
                st.success(f"Google Sheets updated automatically: {sync_result.message}")
            except SyncError as e:
                st.warning(f"Processed locally, but Google Sheets sync needs setup: {e}")

with st.expander("How does this work?"):
    st.markdown("""
1. **Read**: the local parser extracts transactions from the PDF.
2. **Check**: the app replays every row from the opening balance and compares with the bank's
   printed balance. If anything's off, it points at the exact row and holds everything back.
3. **Sort**: saved merchant rules, keywords, and local heuristics assign categories.
4. **Suggest**: the app highlights recurring charges, concentrated spending, and possible set-asides.
5. **Review**: you approve uncertain rows. Your choices become rules.
6. **Sync**: the sidebar button copies approved rows into the FinTrack Google Sheet, one tab per month.
""")
