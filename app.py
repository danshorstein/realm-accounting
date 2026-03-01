"""JJC Financial Dashboards - Streamlit Application."""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from chart_of_accounts import FUND_NAMES
from data_loader import load_cached_data, refresh_data

from dashboards import income_statement, balance_sheet, cash_flow, budget_vs_actuals, ai_insights

st.set_page_config(
    page_title="JJC Financial Dashboards",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Sidebar ---
with st.sidebar:
    st.title("JJC Financials")
    st.caption("Jacksonville Jewish Center")

    st.divider()

    # Fund selector
    fund_options = {"All Funds": None}
    fund_options.update({f"{k:03d} - {v}": k for k, v in FUND_NAMES.items()})
    selected_fund_label = st.selectbox("Fund", options=list(fund_options.keys()))
    selected_fund = fund_options[selected_fund_label]

    st.divider()

    # View mode toggle
    view_mode = st.radio(
        "View Mode",
        options=["Executive Summary", "Detailed"],
        index=1,
        help=(
            "Executive Summary: high-level KPIs and charts only.\n\n"
            "Detailed: full account tables, drill-downs, and all charts."
        ),
    )
    st.session_state["view_mode"] = view_mode

    st.divider()

    st.subheader("Filter Period")
    
    # We will compute the min/max dates once the dataframe is loaded
    # But we can reserve the space here
    date_container = st.empty()

    st.divider()

    # Data management
    st.subheader("Data")

    if st.button("Refresh Data from OnRealm", type="primary", use_container_width=True):
        with st.spinner("Logging in and downloading data..."):
            try:
                df = refresh_data()
                st.session_state["data"] = df
                st.success("Data refreshed!")
            except Exception as e:
                st.error(f"Error: {e}")

    st.caption(
        "Loads latest transactions from OnRealm. "
        "Requires credentials in .env file."
    )

# --- Load data ---
if "data" not in st.session_state:
    df = load_cached_data()
    if df is not None:
        st.session_state["data"] = df

if "data" not in st.session_state:
    st.warning(
        "No data loaded. Either:\n\n"
        "1. Click **Refresh Data from OnRealm** in the sidebar (requires .env credentials)\n"
        "2. Place a previously downloaded CSV in the `data/` directory"
    )
    st.stop()

df = st.session_state["data"]

with date_container.container():
    # Only filter transactions (leave beginning balances alone)
    txns = df[df["Description"] != "Beginning Balance"].copy()
    
    if not txns.empty:
        # Add Fiscal Year and Period to dataframe for filtering
        txns["FY"] = txns["Date"].dt.year + (txns["Date"].dt.month >= 7).astype(int)
        
        # Map months to periods (July = 1, June = 12)
        def get_period(month):
            return month - 6 if month >= 7 else month + 6
        txns["Period"] = txns["Date"].dt.month.apply(get_period)

        col1, col2 = st.columns(2)
        
        # FY Dropdown
        fys = sorted(txns["FY"].dropna().unique(), reverse=True)
        selected_fy_str = col1.selectbox("Fiscal Year", options=["All Time"] + [f"FY {int(y)}" for y in fys])
        
        if selected_fy_str != "All Time":
            selected_fy = int(selected_fy_str.split(" ")[1])
            
            # Period Dropdown (only show periods available in the selected FY)
            fy_txns = txns[txns["FY"] == selected_fy]
            periods = sorted(fy_txns["Period"].unique())
            period_labels = {p: f"Period {p} ({pd.Timestamp(year=2000, month=(p+6) if p <= 6 else (p-6), day=1).strftime('%B')})" for p in periods}
            
            selected_period_label = col2.selectbox("Up To Period", options=["Full Year"] + [period_labels[p] for p in periods], index=len(periods))
            
            # Filter the dataframe
            if selected_period_label == "Full Year":
                # Include all Beg Balances + all txns up to end of this FY
                mask = (df["Description"] == "Beginning Balance") | (
                    (df["Date"].dt.year + (df["Date"].dt.month >= 7).astype(int)) <= selected_fy
                )
            else:
                # Include all Beg Balances + all txns up to this FY and Period
                selected_period = int(selected_period_label.split(" ")[1])
                
                # We need to compute an absolute sorting order to filter "up to" this point
                df["_FY"] = df["Date"].dt.year + (df["Date"].dt.month >= 7).astype(int)
                df["_Period"] = df["Date"].dt.month.apply(get_period)
                
                # Txns that are prior FYs, OR (current FY AND period <= selected)
                mask = (df["Description"] == "Beginning Balance") | (df["_FY"] < selected_fy) | ((df["_FY"] == selected_fy) & (df["_Period"] <= selected_period))
                df = df[mask].copy()
                
                if "_FY" in df.columns:
                    df = df.drop(columns=["_FY", "_Period"])
        else:
            # All Time = No change to df
            pass

# --- Dashboard tabs ---
tab_pl, tab_bs, tab_cf, tab_bva, tab_ai = st.tabs([
    "Income Statement",
    "Balance Sheet",
    "Cash Flow & Trends",
    "Budget vs Actuals",
    "AI Insights",
])

with tab_pl:
    income_statement.render(df, selected_fund, view_mode=view_mode)

with tab_bs:
    balance_sheet.render(df, selected_fund, view_mode=view_mode)

with tab_cf:
    cash_flow.render(df, selected_fund, view_mode=view_mode)

with tab_bva:
    budget_vs_actuals.render(df, selected_fund)

with tab_ai:
    ai_insights.render(df, selected_fund)
