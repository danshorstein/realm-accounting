"""Balance Sheet dashboard."""

from __future__ import annotations

from decimal import Decimal

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from chart_of_accounts import subcategory_sort_key, FUND_NAMES, get_fund_name
from data_loader import get_trial_balance, get_transactions_for_account

TWO_PLACES = Decimal("0.00")


def render(df: pd.DataFrame, selected_fund: int | None, view_mode: str = "Detailed") -> None:
    st.header("Balance Sheet")

    tb = get_trial_balance(df, fund=selected_fund)

    if tb.empty:
        st.info("No balance sheet data found for the selected filters.")
        return

    # Convert Decimal columns to float for display
    display_tb = tb.copy()
    for col in ["Beginning Balance", "YTD Activity", "Ending Balance"]:
        display_tb[col] = display_tb[col].apply(float)

    # --- Summary metrics ---
    assets = display_tb[display_tb["Category"] == "Asset"]["Ending Balance"].sum()
    liabilities = display_tb[display_tb["Category"] == "Liability"]["Ending Balance"].sum()
    net_assets = display_tb[display_tb["Category"] == "Net Assets"]["Ending Balance"].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Assets", f"${assets:,.2f}")
    col2.metric("Total Liabilities", f"${abs(liabilities):,.2f}")
    col3.metric("Net Assets", f"${abs(net_assets):,.2f}")

    st.divider()

    # --- Net Assets composition chart (shown in both modes) ---
    st.subheader("Net Assets Composition")
    na_df = display_tb[display_tb["Category"] == "Net Assets"].copy()
    if not na_df.empty:
        na_summary = (
            na_df.groupby("Unified")["Ending Balance"]
            .sum()
            .reset_index()
        )
        na_summary["Ending Balance"] = na_summary["Ending Balance"].apply(abs)
        na_summary = na_summary[na_summary["Ending Balance"] > 0]

        if not na_summary.empty:
            fig = px.pie(
                na_summary,
                values="Ending Balance",
                names="Unified",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(margin=dict(t=30, l=0, r=0, b=0))
            st.plotly_chart(fig, use_container_width=True)

    # Executive Summary stops here (after KPIs + pie chart)
    if view_mode == "Executive Summary":
        if selected_fund is None:
            _render_fund_comparison(df)
        return

    st.divider()

    from dashboards.matrix_grid import render_matrix

    st.markdown("### Assets")
    render_matrix(display_tb, "Asset", selected_fund, height=350, value_col="Ending Balance")

    st.markdown("### Liabilities")
    render_matrix(display_tb, "Liability", selected_fund, height=350, value_col="Ending Balance")

    st.markdown("### Net Assets")
    render_matrix(display_tb, "Net Assets", selected_fund, height=350, value_col="Ending Balance")


def _render_fund_comparison(df: pd.DataFrame) -> None:
    """Stacked bar chart comparing Assets, Liabilities, Net Assets across all funds."""
    st.divider()
    with st.expander("Fund-by-Fund Balance Sheet Comparison", expanded=True):
        rows = []
        for fund_id in sorted(FUND_NAMES.keys()):
            tb = get_trial_balance(df, fund=fund_id)
            if tb.empty:
                continue
            for col in ["Beginning Balance", "YTD Activity", "Ending Balance"]:
                tb[col] = tb[col].apply(float)

            assets = tb[tb["Category"] == "Asset"]["Ending Balance"].sum()
            liabilities = abs(tb[tb["Category"] == "Liability"]["Ending Balance"].sum())
            net_assets = abs(tb[tb["Category"] == "Net Assets"]["Ending Balance"].sum())

            if assets == 0 and liabilities == 0 and net_assets == 0:
                continue

            rows.append(
                {
                    "Fund": get_fund_name(fund_id),
                    "Assets": assets,
                    "Liabilities": liabilities,
                    "Net Assets": net_assets,
                }
            )

        if not rows:
            st.info("No data available for fund comparison.")
            return

        fund_df = pd.DataFrame(rows)
        melted = fund_df.melt(
            id_vars=["Fund"],
            value_vars=["Assets", "Liabilities", "Net Assets"],
            var_name="Category",
            value_name="Amount",
        )

        fig = px.bar(
            melted,
            x="Fund",
            y="Amount",
            color="Category",
            barmode="group",
            labels={"Amount": "Amount ($)"},
            color_discrete_map={
                "Assets": "#3498db",
                "Liabilities": "#e74c3c",
                "Net Assets": "#2ecc71",
            },
        )
        fig.update_layout(yaxis_tickformat="$,.0f", legend_title="")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(
            fund_df.style.format(
                {"Assets": "${:,.2f}", "Liabilities": "${:,.2f}", "Net Assets": "${:,.2f}"}
            ),
            use_container_width=True,
            hide_index=True,
        )
