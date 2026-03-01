"""Data loading and transformation pipeline for JJC financial data."""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal

import pandas as pd

from chart_of_accounts import classify_account, get_fund_name, get_hierarchy
from database import load_beginning_balances, load_transactions, save_transactions, save_sync_time
from realm_client import (
    Config,
    build_export_filter,
    download_export_csv,
    get_config,
    get_credentials,
    login,
)

TWO_PLACES = Decimal("0.00")

LEDGER_COLUMNS = [
    "Fund",
    "Core",
    "Department",
    "Account",
    "Account Description",
    "Date",
    "Reference",
    "Payee",
    "Description",
    "Transaction Status",
    "Comment",
    "Project",
    "Transaction Type",
    "Debit",
    "Credit",
    "net",
]


def load_csv(path: str) -> pd.DataFrame:
    """Load and clean a ledger export CSV."""
    df = pd.read_csv(path)
    df["Debit"] = df["Debit"].fillna(0)
    df["Credit"] = df["Credit"].fillna(0)
    df["Debit"] = (
        df["Debit"].astype(str).str.replace(",", "", regex=False).apply(Decimal)
    )
    df["Credit"] = (
        df["Credit"].astype(str).str.replace(",", "", regex=False).apply(Decimal)
    )
    df["net"] = (df["Debit"] - df["Credit"]).apply(lambda x: x.quantize(TWO_PLACES))
    return df


def enrich_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add classification columns to a dataframe with Fund and Core columns."""
    df = df.copy()

    # Ensure Fund and Core are integers
    df["Fund"] = pd.to_numeric(df["Fund"], errors="coerce").fillna(0).astype(int)
    df["Core"] = pd.to_numeric(df["Core"], errors="coerce").fillna(0).astype(int)

    # Add fund name
    df["Fund Name"] = df["Fund"].apply(get_fund_name)

    # Add category and subcategory
    classifications = df["Core"].apply(classify_account)
    df["Category"] = classifications.apply(lambda x: x[0])
    df["Subcategory"] = classifications.apply(lambda x: x[1])

    # Add multi-level hierarchy
    hierarchies = df["Core"].apply(get_hierarchy)
    df["L1"] = hierarchies.apply(lambda x: x[0])
    df["L2"] = hierarchies.apply(lambda x: x[1])
    df["L3"] = hierarchies.apply(lambda x: x[2])

    from chart_of_accounts import get_unified_category
    df["Unified"] = df.apply(lambda row: get_unified_category(row["L1"], row["L2"], row["Category"]), axis=1)

    # Parse dates
    df["Date"] = pd.to_datetime(df["Date"], format="mixed", errors="coerce")

    # Add month column for trend analysis
    df["Month"] = df["Date"].dt.to_period("M")
    
    return df


def get_latest_csv(data_dir: str = "data") -> str | None:
    """Find the most recent CSV file in the data directory."""
    if not os.path.isdir(data_dir):
        return None
    csvs = [f for f in os.listdir(data_dir) if f.endswith(".csv")]
    if not csvs:
        return None
    # Sort by modification time, newest first
    csvs.sort(key=lambda f: os.path.getmtime(os.path.join(data_dir, f)), reverse=True)
    return os.path.join(data_dir, csvs[0])


def refresh_data(
    begin: str = "07/01/2025",
    end: str | None = None,
    include_open: bool = True,
) -> pd.DataFrame:
    """Full pipeline: login, download, parse, classify, combine with beginning balances.

    Returns an enriched DataFrame ready for dashboard consumption.
    """
    if end is None:
        end = datetime.today().strftime("%m/%d/%Y")

    cfg = get_config()
    username, password = get_credentials()

    session = login(cfg, username, password)

    filt = build_export_filter(begin, end, include_open=include_open)
    out_file = os.path.join(
        "data",
        f"LedgerInquiry_Export_{begin.replace('/', '-')}_to_{end.replace('/', '-')}.csv",
    )
    os.makedirs("data", exist_ok=True)
    download_export_csv(session, cfg, filt, out_file)

    # Load, enrich, and save to database
    enriched_df = load_and_combine(out_file)
    save_transactions(enriched_df)
    save_sync_time()
    
    return enriched_df


def load_and_combine(csv_path: str) -> pd.DataFrame:
    """Load a CSV and combine with beginning balances, returning enriched data."""
    # Load transaction data
    txn_df = load_csv(csv_path)

    # Load beginning balances
    bb_df = load_beginning_balances()

    # Combine
    combined = pd.concat([bb_df, txn_df], ignore_index=True)

    # Enrich with classifications
    combined = enrich_dataframe(combined)

    return combined


def load_cached_data() -> pd.DataFrame | None:
    csv_path = get_latest_csv()
    if csv_path is None:
        return None
    return load_and_combine(csv_path)


# ---- Aggregation helpers ----


def get_trial_balance(df: pd.DataFrame, fund: int | None = None) -> pd.DataFrame:
    """Compute trial balance: beginning balance + YTD activity = ending balance.

    Groups by Account and Account Description.
    """
    if fund is not None:
        df = df[df["Fund"] == fund]

    # Split beginning balances vs transactions
    beg = df[df["Description"] == "Beginning Balance"]
    txn = df[df["Description"] != "Beginning Balance"]

    beg_summary = (
        beg.groupby(["Fund Name", "Account", "Account Description", "Category", "Subcategory", "L1", "L2", "L3", "Unified"])["net"]
        .sum()
        .reset_index()
        .rename(columns={"net": "Beginning Balance"})
    )

    txn_summary = (
        txn.groupby(["Fund Name", "Account", "Account Description", "Category", "Subcategory", "L1", "L2", "L3", "Unified"])["net"]
        .sum()
        .reset_index()
        .rename(columns={"net": "YTD Activity"})
    )

    tb = pd.merge(beg_summary, txn_summary, how="outer", on=["Fund Name", "Account", "Account Description", "Category", "Subcategory", "L1", "L2", "L3", "Unified"])
    tb["Beginning Balance"] = tb["Beginning Balance"].fillna(Decimal("0")).apply(
        lambda x: x if isinstance(x, Decimal) else Decimal(str(x))
    )
    tb["YTD Activity"] = tb["YTD Activity"].fillna(Decimal("0")).apply(
        lambda x: x if isinstance(x, Decimal) else Decimal(str(x))
    )
    tb["Ending Balance"] = (tb["Beginning Balance"] + tb["YTD Activity"]).apply(
        lambda x: x.quantize(TWO_PLACES)
    )

    return tb.sort_values(["Category", "Unified", "L1", "L2", "L3", "Account"])


def get_monthly_summary(
    df: pd.DataFrame, fund: int | None = None
) -> pd.DataFrame:
    """Aggregate transactions by month (excluding beginning balances)."""
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if fund is not None:
        txn = txn[txn["Fund"] == fund]

    monthly = (
        txn.groupby(["Month", "Category"])["net"]
        .sum()
        .reset_index()
    )
    return monthly


def get_income_statement(
    df: pd.DataFrame, fund: int | None = None
) -> pd.DataFrame:
    """Revenue and expense rollup (excluding beginning balances)."""
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if fund is not None:
        txn = txn[txn["Fund"] == fund]

    # Filter to revenue and expense accounts
    is_re = txn["Category"].isin(["Revenue", "Expense"])
    re_df = txn[is_re]

    summary = (
        re_df.groupby(["Category", "Subcategory", "Account", "Account Description"])["net"]
        .sum()
        .reset_index()
    )
    summary["net"] = summary["net"].apply(
        lambda x: x.quantize(TWO_PLACES) if isinstance(x, Decimal) else Decimal(str(x)).quantize(TWO_PLACES)
    )

    return summary.sort_values(["Category", "Account"])


def get_all_funds_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with income statement totals for every fund.

    Columns: Fund, Fund Name, Revenue, Expenses, Net Income
    """
    from chart_of_accounts import get_fund_name, FUND_NAMES

    rows = []
    for fund_id in sorted(FUND_NAMES.keys()):
        is_df = get_income_statement(df, fund=fund_id)
        if is_df.empty:
            continue
        revenue = float(
            is_df[is_df["Category"] == "Revenue"]["net"].apply(
                lambda x: x if isinstance(x, Decimal) else Decimal(str(x))
            ).sum()
        )
        expenses = float(
            is_df[is_df["Category"] == "Expense"]["net"].apply(
                lambda x: x if isinstance(x, Decimal) else Decimal(str(x))
            ).sum()
        )
        # Revenue net is typically negative in double-entry; flip for display
        revenue_display = abs(revenue)
        expenses_display = abs(expenses)
        net = revenue_display - expenses_display
        rows.append(
            {
                "Fund": fund_id,
                "Fund Name": get_fund_name(fund_id),
                "Revenue": revenue_display,
                "Expenses": expenses_display,
                "Net Income": net,
            }
        )
    return pd.DataFrame(rows)


def get_transactions_for_account(
    df: pd.DataFrame, fund: int | None, account_code: str
) -> pd.DataFrame:
    """Return individual transactions for an account code, excluding beginning balances."""
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if fund is not None:
        txn = txn[txn["Fund"] == fund]
    txn = txn[txn["Account"] == account_code].copy()
    txn["net_float"] = txn["net"].apply(
        lambda x: float(x) if isinstance(x, Decimal) else float(x)
    )
    cols = ["Date", "Payee", "Description", "Transaction Type", "net_float"]
    available = [c for c in cols if c in txn.columns]
    result = txn[available].rename(columns={"net_float": "Amount"})
    return result.sort_values("Date", ascending=False)


def get_monthly_variance(
    df: pd.DataFrame, fund: int | None = None
) -> pd.DataFrame:
    """Compute monthly revenue, expenses, net, and month-over-month % change.

    Returns a DataFrame indexed by Month (Period) with columns:
        Revenue, Expenses, Net, Revenue MoM %, Expense MoM %
    """
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if fund is not None:
        txn = txn[txn["Fund"] == fund]

    is_re = txn["Category"].isin(["Revenue", "Expense"])
    re_txn = txn[is_re].copy()

    re_txn["net_float"] = re_txn["net"].apply(
        lambda x: float(x) if isinstance(x, Decimal) else float(x)
    )

    monthly = (
        re_txn.groupby(["Month", "Category"])["net_float"]
        .sum()
        .unstack(fill_value=0.0)
    )

    if "Revenue" not in monthly.columns:
        monthly["Revenue"] = 0.0
    if "Expense" not in monthly.columns:
        monthly["Expense"] = 0.0

    # Revenue net is typically negative in double-entry; flip for display
    monthly["Revenue"] = monthly["Revenue"].abs()
    monthly["Expenses"] = monthly["Expense"].abs()
    monthly["Net"] = monthly["Revenue"] - monthly["Expenses"]

    monthly["Revenue MoM %"] = monthly["Revenue"].pct_change() * 100
    monthly["Expense MoM %"] = monthly["Expenses"].pct_change() * 100

    return monthly[["Revenue", "Expenses", "Net", "Revenue MoM %", "Expense MoM %"]].sort_index()
