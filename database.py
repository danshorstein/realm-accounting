"""SQLite database management for JJC Financials."""

from __future__ import annotations

import json
import sqlite3
import pandas as pd
from decimal import Decimal
from pathlib import Path

DB_PATH = Path("data/finance.db")
SEED_PATH = Path("beginning_balances_seed.json")

def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    """Initialize database schema if it doesn't exist."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # We will store transactions as a dump from Pandas to SQL,
        # but we can enforce some schema rules or indices here if needed.
        # For Chart of Accounts / Beginning Balances, we'll create dedicated tables later.
        
        conn.commit()
        
    _seed_beginning_balances()

def _parse_amount(s: str) -> Decimal:
    """Parse amount string like '(436,375.02)' or '733,932.92' into Decimal."""
    s = s.strip()
    s = s.replace(",", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return Decimal(s)

def _seed_beginning_balances() -> None:
    """Read the JSON seed file and load beginning balances into SQLite if not present."""
    if not SEED_PATH.exists():
        return
        
    with get_connection() as conn:
        # Check if table has data
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM beginning_balances")
            if cur.fetchone()[0] > 0:
                return  # already seeded
        except sqlite3.OperationalError:
            pass # table doesn't exist
            
    with open(SEED_PATH) as f:
        data = json.load(f)
        
    lines = data["beginning_balances_raw"].strip().split("\n")
    rows = []
    
    # Skip header line
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        account_name = parts[0].strip()
        amount_str = parts[1].strip()

        account_code = account_name.split(" ")[0]
        account_desc = " ".join(account_name.split(" ")[1:])

        fund_str, core_str = account_code.split("-")
        
        rows.append({
            "Fund": int(fund_str),
            "Core": int(core_str),
            "Department": "",
            "Account": f"{account_code}-000",
            "Account Description": account_desc,
            "Date": "7/1/2025",
            "Reference": "",
            "Payee": "",
            "Description": "Beginning Balance",
            "Transaction Status": "",
            "Comment": "",
            "Project": "",
            "Transaction Type": "",
            "Debit": Decimal("0"),
            "Credit": Decimal("0"),
            "net": _parse_amount(amount_str),
        })
        
    df = pd.DataFrame(rows)
    # Convert Decimals down to float for sqlite storage since it doesn't natively support decimal types well
    # We will recast when pulling them back out
    df["net"] = df["net"].astype(float)
    df["Debit"] = df["Debit"].astype(float)
    df["Credit"] = df["Credit"].astype(float)

    with get_connection() as conn:
        df.to_sql("beginning_balances", conn, if_exists="replace", index=False)

def load_beginning_balances() -> pd.DataFrame:
    """Load the beginning balances from SQLite, restoring Decimals."""
    init_db() # Ensure DB is seeded
    
    with get_connection() as conn:
        try:
            df = pd.read_sql("SELECT * FROM beginning_balances", conn)
            
            # Restore 2-place Decimals
            TWO_PLACES = Decimal("0.00")
            df["net"] = df["net"].apply(lambda x: Decimal(str(x)).quantize(TWO_PLACES))
            df["Debit"] = df["Debit"].apply(lambda x: Decimal(str(x)).quantize(TWO_PLACES))
            df["Credit"] = df["Credit"].apply(lambda x: Decimal(str(x)).quantize(TWO_PLACES))
            
            return df
        except sqlite3.OperationalError:
            return pd.DataFrame()

def save_transactions(df: pd.DataFrame) -> None:
    """Save enriched transaction dataframe to the database, replacing old data."""
    with get_connection() as conn:
        # We replace the table entirely on a refresh for simplicity, 
        # acting as a robust cache rather than a complex incremental sync.
        df.to_sql("transactions", conn, if_exists="replace", index=False)

def load_transactions() -> pd.DataFrame | None:
    """Load transactions from the database, parsing dates correctly."""
    if not DB_PATH.exists():
        return None
        
    with get_connection() as conn:
        try:
            # We use parse_dates so pandas reconstructs the datetime objects
            df = pd.read_sql("SELECT * FROM transactions", conn, parse_dates=["Date"])
            # The Month period column is lost in sqlite stringification, 
            # so we reconstruct it here after reading.
            if not df.empty and "Date" in df.columns:
                df["Month"] = df["Date"].dt.to_period("M")
            return df
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return None
