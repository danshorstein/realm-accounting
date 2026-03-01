"""Income Statement (P&L) dashboard."""

from __future__ import annotations

from decimal import Decimal

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from data_loader import get_all_funds_summary, get_transactions_for_account, get_monthly_variance

TWO_PLACES = Decimal("0.00")


def render(df: pd.DataFrame, selected_fund: int | None, view_mode: str = "Detailed") -> None:
    st.header("Income Statement (P&L)")

    # Filter to transactions only (no beginning balances)
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if selected_fund is not None:
        txn = txn[txn["Fund"] == selected_fund]

    # Filter to revenue and expense accounts
    re_mask = txn["Category"].isin(["Revenue", "Expense"])
    re_df = txn[re_mask].copy()

    if re_df.empty:
        st.info("No revenue or expense transactions found for the selected filters.")
        return

    # --- Summary metrics with MoM deltas ---
    revenue_total = re_df[re_df["Category"] == "Revenue"]["net"].sum()
    expense_total = re_df[re_df["Category"] == "Expense"]["net"].sum()
    revenue_display = float(abs(revenue_total))
    expense_display = float(abs(expense_total))
    net_income = revenue_display - expense_display

    # Compute MoM deltas from last two months
    mv = get_monthly_variance(df, selected_fund)
    revenue_delta = None
    expense_delta = None
    if len(mv) >= 2:
        last = mv.iloc[-1]
        prev = mv.iloc[-2]
        revenue_delta = f"{last['Revenue MoM %']:+.1f}% vs prior month" if not pd.isna(last["Revenue MoM %"]) else None
        expense_delta = f"{last['Expense MoM %']:+.1f}% vs prior month" if not pd.isna(last["Expense MoM %"]) else None

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Revenue", f"${revenue_display:,.2f}", delta=revenue_delta)
    col2.metric("Total Expenses", f"${expense_display:,.2f}", delta=expense_delta, delta_color="inverse")
    col3.metric(
        "Net Income",
        f"${net_income:,.2f}",
        delta=f"{'Surplus' if net_income >= 0 else 'Deficit'}",
        delta_color="normal" if net_income >= 0 else "inverse",
    )

    st.divider()

    # --- Monthly Revenue vs Expenses bar chart ---
    st.subheader("Monthly Revenue vs Expenses")

    monthly = (
        re_df.groupby(["Month", "Category"])["net"]
        .sum()
        .reset_index()
    )
    monthly["Amount"] = monthly["net"].apply(lambda x: float(abs(x)))
    monthly["Month_str"] = monthly["Month"].astype(str)

    if not monthly.empty:
        fig = px.bar(
            monthly,
            x="Month_str",
            y="Amount",
            color="Category",
            barmode="group",
            labels={"Month_str": "Month", "Amount": "Amount ($)"},
            color_discrete_map={"Revenue": "#2ecc71", "Expense": "#e74c3c"},
        )
        fig.update_layout(
            xaxis_title="Month",
            yaxis_title="Amount ($)",
            yaxis_tickformat="$,.0f",
            legend_title="",
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- YTD Cumulative Net Income trend line ---
    if not mv.empty:
        st.subheader("YTD Cumulative Net Income")
        mv_plot = mv.copy().reset_index()
        mv_plot["Month_str"] = mv_plot["Month"].astype(str)
        mv_plot["Cumulative Net"] = mv_plot["Net"].cumsum()

        fig_ytd = go.Figure()
        fig_ytd.add_trace(
            go.Scatter(
                x=mv_plot["Month_str"],
                y=mv_plot["Cumulative Net"],
                mode="lines+markers",
                name="Cumulative Net Income",
                line=dict(color="#3498db", width=3),
                fill="tozeroy",
                fillcolor="rgba(52,152,219,0.15)",
            )
        )
        fig_ytd.add_hline(y=0, line_dash="dash", line_color="gray", line_width=1)
        fig_ytd.update_layout(
            yaxis_tickformat="$,.0f",
            xaxis_title="Month",
            yaxis_title="Cumulative Net ($)",
            showlegend=False,
        )
        st.plotly_chart(fig_ytd, use_container_width=True)

    # Executive Summary stops here
    if view_mode == "Executive Summary":
        # Fund comparison chart (All Funds only)
        if selected_fund is None:
            _render_fund_comparison(df)
        return

    # --- Detail tables (Detailed mode only) ---
    st.divider()
    st.subheader("Account Detail")
    
    pivot_mode = st.radio("Matrix Layout", options=["Funds as Columns", "Categories as Columns"], horizontal=True)
    pivot_by = "category" if pivot_mode == "Categories as Columns" else "fund"

    detail = (
        re_df.groupby(["Category", "Unified", "L1", "L2", "L3", "Account", "Account Description"])["net"]
        .sum()
        .reset_index()
    )
    detail["Amount"] = detail["net"].apply(lambda x: float(abs(x)))
    detail = detail.sort_values(["Category", "Amount"], ascending=[True, False])

    from dashboards.matrix_grid import render_matrix

    st.markdown("**Revenue**")
    render_matrix(df, "Revenue", selected_fund, height=300, pivot_by=pivot_by)

    st.markdown("**Expenses**")
    render_matrix(df, "Expense", selected_fund, height=500, pivot_by=pivot_by)

    exp_detail = detail[detail["Category"] == "Expense"]

    # --- Expense breakdown treemap ---
    if not exp_detail.empty:
        st.subheader("Expense Breakdown")
        top_expenses = exp_detail.head(15)
        fig2 = px.treemap(
            top_expenses,
            path=["Unified", "L1", "Account Description"],
            values="Amount",
            color="Amount",
            color_continuous_scale="Reds",
        )
        fig2.update_layout(margin=dict(t=30, l=0, r=0, b=0))
        st.plotly_chart(fig2, use_container_width=True)

    # --- Fund comparison (All Funds mode) ---
    if selected_fund is None:
        _render_fund_comparison(df)


def _render_fund_comparison(df: pd.DataFrame) -> None:
    """Render a grouped bar chart comparing Revenue/Expenses across all funds."""
    st.divider()
    with st.expander("Fund-by-Fund Comparison", expanded=True):
        fund_summary = get_all_funds_summary(df)
        if fund_summary.empty:
            st.info("No fund data available for comparison.")
            return

        # Melt for grouped bar
        melted = fund_summary.melt(
            id_vars=["Fund Name"],
            value_vars=["Revenue", "Expenses", "Net Income"],
            var_name="Metric",
            value_name="Amount",
        )

        fig = px.bar(
            melted,
            x="Fund Name",
            y="Amount",
            color="Metric",
            barmode="group",
            labels={"Amount": "Amount ($)", "Fund Name": "Fund"},
            color_discrete_map={
                "Revenue": "#2ecc71",
                "Expenses": "#e74c3c",
                "Net Income": "#3498db",
            },
        )
        fig.update_layout(yaxis_tickformat="$,.0f", legend_title="")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            fund_summary.style.format(
                {"Revenue": "${:,.2f}", "Expenses": "${:,.2f}", "Net Income": "${:,.2f}"}
            ),
            use_container_width=True,
            hide_index=True,
        )
