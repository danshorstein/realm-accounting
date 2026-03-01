"""Cash Flow / Trends dashboard."""

from __future__ import annotations

from decimal import Decimal

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from chart_of_accounts import FUND_NAMES, get_fund_name
from data_loader import get_monthly_variance

TWO_PLACES = Decimal("0.00")


def render(df: pd.DataFrame, selected_fund: int | None, view_mode: str = "Detailed") -> None:
    st.header("Cash Flow & Trends")

    # Filter to transactions only
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if selected_fund is not None:
        txn = txn[txn["Fund"] == selected_fund]

    if txn.empty:
        st.info("No transaction data found for the selected filters.")
        return

    # Get beginning cash balance
    beg = df[df["Description"] == "Beginning Balance"].copy()
    if selected_fund is not None:
        beg = beg[beg["Fund"] == selected_fund]

    cash_beg = beg[beg["Subcategory"] == "Cash & Cash Equivalents"]["net"].sum()
    cash_beg_float = float(cash_beg) if isinstance(cash_beg, Decimal) else float(cash_beg)

    txn["net_float"] = txn["net"].apply(lambda x: float(x) if isinstance(x, Decimal) else float(x))

    monthly = txn.groupby("Month").agg(
        inflows=("net_float", lambda x: x[x > 0].sum()),
        outflows=("net_float", lambda x: x[x < 0].sum()),
        net=("net_float", "sum"),
    ).reset_index()
    monthly["Month_str"] = monthly["Month"].astype(str)
    monthly = monthly.sort_values("Month")

    # --- Running cash balance (shown in both modes) ---
    st.subheader("Running Cash Balance")

    if not monthly.empty:
        monthly["cumulative_net"] = monthly["net"].cumsum()
        monthly["running_balance"] = cash_beg_float + monthly["cumulative_net"]

        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=monthly["Month_str"],
                y=monthly["running_balance"],
                mode="lines+markers",
                name="Cash Balance",
                line=dict(color="#3498db", width=3),
                marker=dict(size=8),
                fill="tozeroy",
                fillcolor="rgba(52,152,219,0.1)",
            )
        )
        if len(monthly) >= 3:
            monthly["rolling_avg"] = monthly["running_balance"].rolling(3).mean()
            fig2.add_trace(
                go.Scatter(
                    x=monthly["Month_str"],
                    y=monthly["rolling_avg"],
                    mode="lines",
                    name="3-Month Avg",
                    line=dict(color="#95a5a6", width=2, dash="dash"),
                )
            )
        fig2.update_layout(
            xaxis_title="Month",
            yaxis_title="Balance ($)",
            yaxis_tickformat="$,.0f",
            legend_title="",
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Executive Summary: running balance + fund comparison, then stop
    if view_mode == "Executive Summary":
        if selected_fund is None:
            _render_fund_comparison(df)
        return

    st.divider()

    # --- Monthly cash inflows vs outflows ---
    st.subheader("Monthly Cash Inflows vs Outflows")

    if not monthly.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=monthly["Month_str"],
                y=monthly["inflows"],
                name="Inflows",
                marker_color="#2ecc71",
            )
        )
        fig.add_trace(
            go.Bar(
                x=monthly["Month_str"],
                y=monthly["outflows"].abs(),
                name="Outflows",
                marker_color="#e74c3c",
            )
        )
        fig.update_layout(
            barmode="group",
            xaxis_title="Month",
            yaxis_title="Amount ($)",
            yaxis_tickformat="$,.0f",
            legend_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Monthly net activity with MoM % annotations ---
    st.subheader("Monthly Net Activity")

    if not monthly.empty:
        mv = get_monthly_variance(df, selected_fund).reset_index()
        mv["Month_str"] = mv["Month"].astype(str)

        colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in monthly["net"]]
        fig3 = go.Figure()
        fig3.add_trace(
            go.Bar(
                x=monthly["Month_str"],
                y=monthly["net"],
                marker_color=colors,
                name="Net Activity",
            )
        )

        # Add MoM % change annotations
        if not mv.empty and "Revenue MoM %" in mv.columns:
            for _, row in mv.iterrows():
                if pd.isna(row["Revenue MoM %"]):
                    continue
                fig3.add_annotation(
                    x=row["Month_str"],
                    y=0,
                    text=f"{row['Revenue MoM %']:+.0f}%",
                    showarrow=False,
                    yshift=14,
                    font=dict(size=10, color="#555"),
                )

        fig3.update_layout(
            xaxis_title="Month",
            yaxis_title="Net ($)",
            yaxis_tickformat="$,.0f",
        )
        st.plotly_chart(fig3, use_container_width=True)

    # --- Top largest transactions with filters ---
    st.subheader("Largest Transactions")

    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        month_options = ["All Months"] + sorted(txn["Month"].astype(str).unique().tolist())
        selected_month = st.selectbox("Filter by month", month_options, key="cf_month_filter")
    with filter_col2:
        direction = st.selectbox(
            "Filter by direction",
            ["All", "Inflows (positive)", "Outflows (negative)"],
            key="cf_direction_filter",
        )

    filtered_txn = txn.copy()
    if selected_month != "All Months":
        filtered_txn = filtered_txn[filtered_txn["Month"].astype(str) == selected_month]
    if direction == "Inflows (positive)":
        filtered_txn = filtered_txn[filtered_txn["net_float"] > 0]
    elif direction == "Outflows (negative)":
        filtered_txn = filtered_txn[filtered_txn["net_float"] < 0]

    filtered_txn["abs_net"] = filtered_txn["net_float"].abs()
    top_txn = filtered_txn.nlargest(15, "abs_net")[
        ["Date", "Account Description", "Payee", "Description", "net_float"]
    ].copy()
    top_txn.columns = ["Date", "Account", "Payee", "Description", "Amount"]
    top_txn["Date"] = top_txn["Date"].dt.strftime("%m/%d/%Y")

    st.dataframe(
        top_txn.style.format({"Amount": "${:,.2f}"}),
        use_container_width=True,
        hide_index=True,
    )

    # --- Fund comparison (All Funds mode) ---
    if selected_fund is None:
        _render_fund_comparison(df)


def _render_fund_comparison(df: pd.DataFrame) -> None:
    """Render running cash balance per fund on the same axes."""
    st.divider()
    with st.expander("Fund-by-Fund Cash Balance Comparison", expanded=True):
        fig = go.Figure()
        any_data = False

        for fund_id in sorted(FUND_NAMES.keys()):
            fund_txn = df[
                (df["Description"] != "Beginning Balance") & (df["Fund"] == fund_id)
            ].copy()
            fund_beg = df[
                (df["Description"] == "Beginning Balance") & (df["Fund"] == fund_id)
            ].copy()

            if fund_txn.empty:
                continue

            fund_txn["net_float"] = fund_txn["net"].apply(
                lambda x: float(x) if isinstance(x, Decimal) else float(x)
            )
            cash_beg = fund_beg[fund_beg["Subcategory"] == "Cash & Cash Equivalents"]["net"].sum()
            cash_beg_float = float(cash_beg) if isinstance(cash_beg, Decimal) else float(cash_beg)

            monthly = (
                fund_txn.groupby("Month")["net_float"]
                .sum()
                .reset_index()
                .sort_values("Month")
            )
            monthly["running_balance"] = cash_beg_float + monthly["net_float"].cumsum()
            monthly["Month_str"] = monthly["Month"].astype(str)

            fig.add_trace(
                go.Scatter(
                    x=monthly["Month_str"],
                    y=monthly["running_balance"],
                    mode="lines+markers",
                    name=get_fund_name(fund_id),
                )
            )
            any_data = True

        if not any_data:
            st.info("No cash data available for fund comparison.")
            return

        fig.update_layout(
            xaxis_title="Month",
            yaxis_title="Cash Balance ($)",
            yaxis_tickformat="$,.0f",
            legend_title="Fund",
        )
        st.plotly_chart(fig, use_container_width=True)
