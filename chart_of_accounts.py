"""Account classification logic for JJC chart of accounts.

Account format: FFF-CCCCCC (3-digit fund, 6-digit core account number)
Full format in ledger: FFF-CCCCCC-DDD (with department suffix)
"""

from __future__ import annotations

import json
from pathlib import Path

# Load configuration from JSON
COA_CONFIG_PATH = Path("coa_mapping.json")
with open(COA_CONFIG_PATH) as f:
    COA_CONFIG = json.load(f)

FUND_NAMES = {int(k): v for k, v in COA_CONFIG["funds"].items()}


def get_fund_name(fund: int) -> str:
    return FUND_NAMES.get(fund, f"Fund {fund:03d}")


def classify_account(core: int) -> tuple[str, str]:
    """Classify a core account number into (category, subcategory).

    Args:
        core: The 6-digit core account number (e.g., 111020, 224110)

    Returns:
        Tuple of (category, subcategory) for financial statement placement.
        Categories: Asset, Liability, Net Assets, Revenue, Expense
    """
    # Normalize: first digit (or two) determines the main category
    # Account numbering pattern from the beginning balances:
    #   1xxxxx = Balance sheet (assets, net assets, some liabilities via fund code)
    #   2xxxxx = Balance sheet (liabilities for schools, net assets for schools)
    #   3xxxxx = Sisterhood balance sheet
    #   4xxxxx = Cemetery balance sheet / Revenue accounts
    #   5xxxxx = Men's Club / Expense accounts

    # The leading digits follow a pattern relative to the fund.
    # Within each fund, the "core" account's second+third digits classify:
    #   x11xxx = Cash
    #   x12xxx = Receivables / Allowances
    #   x14xxx = Prepaid
    #   x16xxx = Fixed Assets
    #   x17xxx = Investments
    #   x18xxx = Other Receivables
    #   x19xxx = Other Receivables
    #   x24xxx = Payables / Accruals (liabilities)
    #   x25xxx = Deferred Revenue (liabilities)
    #   x29xxx = Clearing / Other liabilities
    #   x00xxx = Fund Principal Balance (net assets)
    #   x80xxx = Restricted Funds (net assets)
    #   x81xxx = Endowment Funds (net assets)
    #   x90xxx = School restricted funds (net assets)
    #   x91xxx = School endowment funds (net assets)

    # Extract the "local" account digits (strip the fund prefix digit)
    # For fund 001: core 111020 -> local 11020, core 180002 -> local 80002
    # For fund 002: core 211020 -> local 11020, core 291016 -> local 91016
    # The first digit of core matches the fund number, rest is classification

    # Get digits after the fund prefix
    core_str = str(core).zfill(6)
    fund_prefix = core_str[0]
    local = core_str[1:]  # 5 digits after fund prefix

    local_prefix2 = local[:2]  # first 2 digits of local
    local_prefix3 = local[:3]  # first 3 digits of local

    # Assets including Cash, Receivables, Prepaid, Fixed
    if local_prefix2 in COA_CONFIG["asset_mappings"]:
        # Special handling for Allowance
        if local_prefix2 == "12":
            if "allow" in str(core).lower() or local_prefix3 == "120":
                # Ensure we don't accidentally map Accounts Receivable like 112011 to Allowance
                if str(core).endswith("000"):
                    return ("Asset", COA_CONFIG["special"]["120"])
        return ("Asset", COA_CONFIG["asset_mappings"][local_prefix2])

    # Liabilities
    if local_prefix2 in COA_CONFIG["liability_mappings"]:
        return ("Liability", COA_CONFIG["liability_mappings"][local_prefix2])

    # Net Assets
    if local_prefix2 in COA_CONFIG["net_asset_mappings"]:
        return ("Net Assets", COA_CONFIG["net_asset_mappings"][local_prefix2])

    # Dictionary of heuristically assigned subcategories for known Rev/Exp accounts
    REVENUE_EXPENSE_MAP = COA_CONFIG.get("revenue_expense_mappings", {})

    # Revenue (2nd digit of core account is 3)
    if local[0] == "3":
        return ("Revenue", REVENUE_EXPENSE_MAP.get(str(core).zfill(6), "Revenue"))

    # Expense (2nd digit of core account is 4)
    if local[0] == "4":
        return ("Expense", REVENUE_EXPENSE_MAP.get(str(core).zfill(6), "Expense"))

    # Fallback
    return ("Other", "Uncategorized")


def classify_account_from_code(account_code: str) -> tuple[str, str, str]:
    """Classify from a full account code like '001-111020' or '001-111020-000'.

    Returns:
        Tuple of (fund_name, category, subcategory)
    """
    parts = account_code.split("-")
    fund = int(parts[0])
    core = int(parts[1]) if len(parts) > 1 else 0
    fund_name = get_fund_name(fund)
    category, subcategory = classify_account(core)
    return fund_name, category, subcategory


MULTI_LEVEL_MAP = COA_CONFIG.get("multi_level_mapping", {})

def get_hierarchy(core: int) -> tuple[str, str, str | None]:
    """Returns a padded 3-level hierarchy (L1, L2, L3) for a given account.
    If the account isn't in the multi-level map, falls back to Category/Subcategory.
    """
    # Try the explicit manual mappings from user CSV first
    core_str = str(core).zfill(6)
    if core_str in MULTI_LEVEL_MAP:
        h = MULTI_LEVEL_MAP[core_str]
        
        # Pad to exactly 3 levels
        l1 = h[0] if len(h) > 0 else "Uncategorized"
        l2 = h[1] if len(h) > 1 else ""
        l3 = h[2] if len(h) > 2 else ""
        return l1, l2, l3
        
    # Fallback to the programmatic Category/Subcategory
    cat, subcat = classify_account(core)
    return cat, subcat, ""


def get_unified_category(l1: str, l2: str, category: str) -> str:
    """Map fund-specific L1/L2 groupings into unified cross-fund buckets."""
    combined = f"{l1} {l2}".lower()
    
    if category == "Revenue":
        if "endowment" in combined:
            return "Endowment Fund Revenue"
        elif "program" in combined or "tuition" in combined or "membership" in combined:
            return "Program Revenue"
        elif "campaign" in combined or "private funding" in combined or "fundrais" in combined or "donation" in combined:
            return "Fundraising Revenue"
        elif "misc" in combined:
            return "Misc Revenue"
        elif "grant" in combined:
            return "Grants"
        else:
            return "Other"
            
    elif category == "Expense":
        if "program" in combined:
            return "Program Expenses"
        elif "staffing" in combined or "salar" in combined:
            return "Salaries"
        elif "maint" in combined:
            return "Maint & Security"
        elif "admin" in combined:
            return "Admin"
        elif "g&a" in combined or "general" in combined:
            return "G&A"
        else:
            return "Other"
            
    return l1


# Balance sheet ordering for display
BALANCE_SHEET_ORDER = COA_CONFIG["balance_sheet_order"]


def subcategory_sort_key(subcategory: str) -> int:
    return BALANCE_SHEET_ORDER.get(subcategory, 99)
