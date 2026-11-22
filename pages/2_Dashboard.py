"""Dashboard: spending vs. set aside, monthly chart, top shops, subscriptions, alerts."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from finance import alerts, ledger, summary
from finance.config import EMOJI, SET_ASIDE, SPENDING
from ui_common import money, page

settings, db = page("Dashboard", "📊")
st.title("📊 Dashboard")

overview = ledger.monthly_overview(db)
if overview.empty:
    st.info("No reviewed transactions yet. Upload a statement first.")
    st.stop()

months = list(overview.month.sort_values(ascending=False))
month = st.selectbox("Month", months, format_func=lambda m: pd.Period(m, "M").strftime("%B %Y"))
row = overview.set_index("month").loc[month]
prev = str(pd.Period(month, "M") - 1)
prev_row = overview.set_index("month").loc[prev] if prev in set(overview.month) else None

c1, c2, c3, c4 = st.columns(4)
delta = None
if prev_row is not None and prev_row.spending > 0:
    delta = f"{(row.spending / prev_row.spending - 1) * 100:+.0f}% vs {pd.Period(prev, 'M'):%b}"
c1.metric("Spent", money(row.spending), delta=delta, delta_color="inverse")
c2.metric("Set aside", money(row.set_aside), help="Investments + Savings")
c3.metric("Money in", money(row.money_in))
c4.metric(
    "Savings rate",
    f"{row.set_aside / row.money_in:.0%}" if row.money_in > 0 else "–",
    help="Set aside ÷ money in",
)

totals = ledger.category_totals(db)
chart_data = totals[totals.category.isin(SPENDING + SET_ASIDE)].copy()
chart_data["category"] = chart_data.category.map(lambda c: f"{EMOJI[c]} {c}")
st.subheader("Month by month")
fig = px.bar(
    chart_data.sort_values("month"),
    x="month",
    y="total",
    color="category",
    labels={"month": "", "total": "", "category": ""},
)
fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.15))
st.plotly_chart(fig, width="stretch")

left, right = st.columns(2)
with left:
    st.subheader(f"{pd.Period(month, 'M'):%B}: by category")
    this_month = totals[totals.month == month].set_index("category")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Category": f"{EMOJI[c]} {c}",
                    "Total": this_month.total.get(c, 0.0),
                    "Transactions": int(this_month.transactions.get(c, 0)),
                }
                for c in SPENDING + SET_ASIDE
            ]
        ),
        hide_index=True,
        width="stretch",
        column_config={"Total": st.column_config.NumberColumn(format="%.2f")},
    )
with right:
    st.subheader("Top shops")
    st.dataframe(
        ledger.top_shops(db, month),
        hide_index=True,
        width="stretch",
        column_config={"total": st.column_config.NumberColumn("Total", format="%.2f")},
    )

st.subheader("🔁 Subscriptions spotted")
subs = alerts.recurring(ledger.spending_frame(db))
if subs.empty:
    st.caption("None yet. Needs at least 3 monthly charges from the same shop.")
else:
    st.dataframe(
        subs[["shop", "category", "amount", "previous", "last_charged"]],
        hide_index=True,
        width="stretch",
        column_config={
            "amount": st.column_config.NumberColumn("Latest", format="%.2f"),
            "previous": st.column_config.NumberColumn("Before", format="%.2f"),
        },
    )
    st.caption(f"About {money(subs.amount.sum())} a month in total.")

st.subheader("⚠️ Alerts")
open_alerts = ledger.open_alerts(db)
if open_alerts.empty:
    st.caption("No open alerts 😌")
for a in open_alerts.itertuples():
    col_msg, col_btn = st.columns([6, 1])
    col_msg.write(f"**{a.kind.replace('_', ' ').capitalize()}**: {a.message}")
    if col_btn.button("Dismiss", key=f"dismiss-{a.id}"):
        ledger.dismiss_alert(db, a.id)
        st.rerun()

with st.expander("📝 Monthly summary text"):
    st.code(summary.monthly_summary(db, month), language=None)
