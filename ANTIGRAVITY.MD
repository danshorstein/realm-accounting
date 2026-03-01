# JJC Financials - Codebase Documentation

## Overview
A Streamlit-based dashboard application for visualizing financial data (Income Statement, Balance Sheet, Cash Flow, Budget vs Actuals) for the Jacksonville Jewish Center (JJC). Data is sourced from OnRealm (a church/synagogue management system) via an automated CSV export process.

## Architecture & Core Modules
- **`app.py`**: The Streamlit entry point. Configures the UI layout, sidebar toggles, and coordinates the rendering of the different dashboard tabs.
- **`data_loader.py`**: The core data pipeline. It cleans the downloaded OnRealm CSV, merges it with the beginning balances, and enriches it with account classifications (Category, Subcategory) and monthly periods for trend analysis. Uses `pandas` heavily.
- **`realm_client.py`**: A custom web scraping client that uses `requests` to log into OnRealm, bypass cookie/OAuth gates using regex HTML parsing, and download the LedgerInquiry grid export as a CSV file.
- **`chart_of_accounts.py`**: Contains the mapping rules for categorizing the 6-digit core account numbers (e.g., `111020`) into financial categories (Asset, Liability, Net Assets, Revenue, Expense) and associating them with specific Funds (Center, Schools, Sisterhood, etc.).
- **`beginning_balances.py`**: Contains a hardcoded string of the trial balance as of June 30, 2025, parsed into a DataFrame to serve as the baseline for the balance sheet.
- **`dashboards/`**: Presentation layer components for the financial statements:
  - `income_statement.py`: P&L details with MoM metrics and Plotly charts.
  - `balance_sheet.py`: Assets, Liabilities, and Net Assets with drill-down expanders.
  - `cash_flow.py`: Cash metrics and runway analysis.
  - `budget_vs_actuals.py`: Currently a placeholder awaiting budget data integration.
  - `ai_insights.py`: Integrates with the Anthropic Claude API to generate qualitative financial insights from the data.

## Key Technical Details
- **Accuracy**: Calculates all currencies using Python's `decimal.Decimal` (quantized to 2 decimal places) to eliminate floating-point precision errors before converting to floats for plotting.
- **View Modes**: The UI implements physical data drill-downs (Executive Summary vs. Detailed views) to provide both high-level KPIs and granular account-level transactions.
- **Colab Compatibility**: `scripts/realm_colab_export.py` is included to allow running the OnRealm export step identically in a Google Colab notebook environment.

## Ongoing Work / Missing Features
- **Budget Integration**: The system needs a source for budget data (Google Sheets or CSV) to populate the `budget_vs_actuals` dashboard.
- **Data Persistence**: Data is currently cached via Streamlit's `session_state` and stored locally as CSVs in the `data/` directory.

### explicit TODOs from Project Owner
- **Year-End Rollover**: Add a script to download the trial balance for a time period ending at each new year-end, pull those balances down, and turn them into the new beginning balances.
- **Budget Discovery**: Ask the accounting folks (or look further in OnRealm) to find where the canonical budget info is located to pull it into the dashboard.

## LLM Tips
- If modifying calculation logic in `data_loader.py`, ensure you maintain the `Decimal` types until the very end of the line, passing `float()` only to `streamlit` or `plotly` which require native floats.
- If classifying a new account type, refer to the digit checking logic in `chart_of_accounts.py` -> `classify_account()`.
