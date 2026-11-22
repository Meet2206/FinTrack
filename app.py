"""Web app: Upload page (home).

Start it with:  streamlit run app.py --server.address localhost
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from finance import pdf_tools, pipeline
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
            if result.sorted_by:
                s = result.sorted_by
                st.caption(f"Sorted by saved rules: {s['rule']} · keywords: {s['keyword']} · AI: {s['ai']}")
            if result.to_review:
                st.page_link("pages/1_Review.py", label=f"Review {result.to_review} row(s) →", icon="👀")

with st.expander("How does this work?"):
    st.markdown("""
1. **Read**: Claude reads the PDF a few pages at a time and copies out every transaction.
2. **Check**: the app replays every row from the opening balance and compares with the bank's
   printed balance. If anything's off, it points at the exact row and holds everything back.
3. **Sort**: shops it has seen before are sorted instantly by saved rules, and new ones by the AI.
4. **Review**: you approve the few rows the AI wasn't sure about. Your choices become rules.
5. **Sync**: the sidebar button copies everything into your 5 Google Sheets, one tab per month.
""")
