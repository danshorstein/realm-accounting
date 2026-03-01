# OnRealm Financial Dashboard

An automated, open-source Streamlit dashboard that connects directly to your [OnRealm](https://onrealm.org/) church or synagogue management system to generate beautiful, interactive financial statements.

## Features

* **Direct Integration:** Uses an automated headless scraper to securely log into your OnRealm account and download your custom `LedgerInquiry` export grid. No manual CSV wrangling required.
* **Local SQLite Database:** Ingests the exported ledger directly into a lightning-fast local SQLite database (`data/finance.db`), ensuring historical data persists.
* **Interactive Financial Statements:** 
  * **Income Statement (P&L)**
  * **Balance Sheet**
  * **Cash Flow (Coming Soon)**
* **Matrix Grouping:** Automatically pivots your accounts into distinct Columns based on your Organization's Funds (e.g., Operating Fund, Education Fund, Cemetery Fund). 
* **Drill-Down Capabilities:** Built with `streamlit-aggrid` to allow financial committees or board members to click and expand rolled-up subcategories (like "Payroll & Benefits") down into individual ledger line-items, and then view specific transactions.

---

## Getting Started

### Prerequisites
* Python 3.10+
* A user account on your organization's OnRealm with `Reporting/Export` permissions.
* For the scraper to work cleanly, go into OnRealm's Ledger Inquiry and save a Custom View where **Columns = All Available Columns**.

### 1. Installation
Clone the repository and install the required dependencies:
```bash
git clone https://github.com/your-username/onrealm-financials.git
cd onrealm-financials
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration
The application relies on extracting your organization's sensitive data OUT of the code and into local un-tracked configuration files.

#### Environment Variables (`.env`)
Copy the template file to create your local `.env`:
```bash
cp .env.example .env
```
Edit `.env` and fill in your details:
* `REALM_SITE_ID`: The tenant ID for your OnRealm instance (found in your URL, e.g. `auth.ministrylogin.com/service/authenticate/TenantId`).
* `REALM_USERNAME`: Your login email.
* `REALM_PASSWORD`: Your login password.

#### Chart of Accounts Mapping (`coa_mapping.json`)
Copy the example JSON to create your live configuration:
```bash
cp coa_mapping.example.json coa_mapping.json
```
Edit `coa_mapping.json` to define:
1. `funds`: Map the prefix digit of your accounts to logical Fund names.
2. `revenue_expense_mappings`: A dictionary mapping your 6-digit core account numbers to semantic roll-up categories (e.g., `Payroll`, `Facilities`, `Donations`).

#### Beginning Balances (`beginning_balances_seed.json`)
Streamlit cannot calculate an accurate Balance Sheet entirely from historical ledger strings if it doesn't know what the ledger looked like on Day 1. 

Copy the template:
```bash
cp beginning_balances_seed.example.json beginning_balances_seed.json
```
Replace the generated numbers with your *actual* Trial Balance from the beginning of your current fiscal year.

### 3. Run the Dashboard
Start the local Streamlit server:
```bash
streamlit run app.py
```
1. Click the **"Refresh Data from OnRealm"** button in the sidebar. 
2. The headless scraper will log in, export your ledger, update the local SQLite database, and reroute you to the Income Statement.

## Privacy & Security

This repository uses a strict `.gitignore` to ensure your sensitive financial data is never accidentally published to GitHub. **Never** remove the following lines from `.gitignore`:
```
.env
data/
*.csv
beginning_balances_seed.json
coa_mapping.json
```

## Contributing

Pull requests are welcome! If you find edge-cases in how OnRealm exports specific journal entries or voided checks, please feel free to open an Issue or submit a PR adapting the Pandas logic in `data_loader.py`.
