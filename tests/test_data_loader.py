import pytest
import pandas as pd
from decimal import Decimal
from data_loader import get_trial_balance

@pytest.fixture
def sample_transactions():
    """Provides a sample dataframe of enriched transactions and beginning balances."""
    # Simplified dataframe that has enough to test get_trial_balance
    return pd.DataFrame([
        {
            "Fund": 1,
            "Account": "001-111020-000",
            "Account Description": "Main Checking",
            "Category": "Asset",
            "Subcategory": "Cash & Cash Equivalents",
            "Description": "Beginning Balance",
            "net": Decimal("1000.50")
        },
        {
            "Fund": 1,
            "Account": "001-111020-000",
            "Account Description": "Main Checking",
            "Category": "Asset",
            "Subcategory": "Cash & Cash Equivalents",
            "Description": "Deposit Transfer",
            "net": Decimal("500.00")
        },
        {
            "Fund": 1,
            "Account": "001-610000-000",
            "Account Description": "Supplies Expense",
            "Category": "Expense",
            "Subcategory": "Expense",
            "Description": "Office Max",
            "net": Decimal("150.25")
        }
    ])

def test_get_trial_balance_math(sample_transactions):
    tb = get_trial_balance(sample_transactions)
    
    # Check Checking Account
    checking = tb[tb["Account"] == "001-111020-000"].iloc[0]
    assert checking["Beginning Balance"] == Decimal("1000.50")
    assert checking["YTD Activity"] == Decimal("500.00")
    assert checking["Ending Balance"] == Decimal("1500.50")
    
    # Check Expense Account (No Beginning Balance)
    expense = tb[tb["Account"] == "001-610000-000"].iloc[0]
    assert expense["Beginning Balance"] == Decimal("0.00")
    assert expense["YTD Activity"] == Decimal("150.25")
    assert expense["Ending Balance"] == Decimal("150.25")
    
def test_get_trial_balance_fund_filter(sample_transactions):
    tb = get_trial_balance(sample_transactions, fund=2)
    assert len(tb) == 0  # No records for fund 2 in the sample
