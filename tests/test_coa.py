import pytest
from chart_of_accounts import classify_account

@pytest.mark.parametrize("core_account, expected_category, expected_subcategory", [
    # Assets - Cash
    (111020, "Asset", "Cash & Cash Equivalents"),  # 001-111020
    (211025, "Asset", "Cash & Cash Equivalents"),  # 002-211025
    
    # Assets - Receivables
    (112011, "Asset", "Accounts Receivable"),      # 001-112011
    (212052, "Asset", "Accounts Receivable"),      # 002-212052
    
    # Assets - Allowance (Special logic)
    (112000, "Asset", "Allowance for Doubtful Accounts"),
    (212000, "Asset", "Allowance for Doubtful Accounts"),
    
    # Assets - Prepaid & Fixed
    (114030, "Asset", "Prepaid Expenses"),
    (116010, "Asset", "Fixed Assets"),
    
    # Liabilities
    (124110, "Liability", "Accounts Payable & Accruals"),
    (225203, "Liability", "Deferred Revenue"),     # 002-225203
    (229120, "Liability", "Other Liabilities"),    # 002-229120
    
    # Net Assets - Principal Balance
    (100029, "Net Assets", "Fund Principal Balance"),
    (200029, "Net Assets", "Fund Principal Balance"),
    
    # Net Assets - Restricted/Endowment
    (180002, "Net Assets", "Restricted Funds"),
    (181001, "Net Assets", "Endowment Funds"),
    
    # Net Assets - School Special (90/91 mapping)
    (290011, "Net Assets", "Restricted Funds"),
    (291005, "Net Assets", "Endowment Funds"),
    
    # Revenue (2nd digit is 3)
    (132240, "Revenue", "Donations & Fundraising"), # Center Fund Gen Donations Rev
    (435110, "Revenue", "Donations & Fundraising"), # Cemetery Lot Sales Rev
    
    # Expense (2nd digit is 4)
    (142980, "Expense", "General & Administrative"), # Center Merchant Fees Exp
    (241164, "Expense", "Facilities & Maintenance"), # PS Repair & Supplies Exp
    
    # Edge Cases
    (159999, "Other", "Uncategorized"), # Unknown pattern (no 5 as 2nd digit)
    (999999, "Other", "Uncategorized"), # Unknown pattern
])
def test_classify_account(core_account, expected_category, expected_subcategory):
    category, subcategory = classify_account(core_account)
    assert category == expected_category
    assert subcategory == expected_subcategory
