"""GenAI Insights panel - uses Claude API to analyze financial data."""

from __future__ import annotations

import os
from decimal import Decimal

import streamlit as st
import pandas as pd

TWO_PLACES = Decimal("0.00")


def _summarize_for_prompt(df: pd.DataFrame, selected_fund: int | None) -> str:
    """Build a concise financial summary string for the AI prompt."""
    txn = df[df["Description"] != "Beginning Balance"].copy()
    if selected_fund is not None:
        txn = txn[txn["Fund"] == selected_fund]
        fund_label = df[df["Fund"] == selected_fund]["Fund Name"].iloc[0] if not df[df["Fund"] == selected_fund].empty else f"Fund {selected_fund}"
    else:
        fund_label = "All Funds (Consolidated)"

    # Key metrics
    revenue = txn[txn["Category"] == "Revenue"]["net"].sum()
    expenses = txn[txn["Category"] == "Expense"]["net"].sum()
    rev_float = float(abs(revenue))
    exp_float = float(abs(expenses))
    net_income = rev_float - exp_float

    # Monthly trend
    monthly = txn.groupby("Month")["net"].sum().reset_index()
    monthly["net_float"] = monthly["net"].apply(lambda x: float(x))
    monthly_lines = []
    for _, row in monthly.iterrows():
        monthly_lines.append(f"  {row['Month']}: ${row['net_float']:,.2f}")

    # Top expense accounts
    exp_df = txn[txn["Category"] == "Expense"]
    if not exp_df.empty:
        top_exp = (
            exp_df.groupby("Account Description")["net"]
            .sum()
            .apply(lambda x: float(abs(x)))
            .sort_values(ascending=False)
            .head(10)
        )
        expense_lines = [f"  {name}: ${amt:,.2f}" for name, amt in top_exp.items()]
    else:
        expense_lines = ["  No expense data"]

    # Cash position
    beg = df[df["Description"] == "Beginning Balance"]
    if selected_fund is not None:
        beg = beg[beg["Fund"] == selected_fund]
    cash_beg = float(beg[beg["Subcategory"] == "Cash & Cash Equivalents"]["net"].sum())

    summary = f"""Financial Summary for {fund_label}
Fiscal Year: July 2025 - Present
Organization: Jacksonville Jewish Center (nonprofit)

KEY METRICS:
- Total Revenue YTD: ${rev_float:,.2f}
- Total Expenses YTD: ${exp_float:,.2f}
- Net Income: ${net_income:,.2f}
- Beginning Cash Position: ${cash_beg:,.2f}

MONTHLY NET ACTIVITY:
{chr(10).join(monthly_lines) if monthly_lines else '  No monthly data'}

TOP 10 EXPENSE CATEGORIES:
{chr(10).join(expense_lines)}
"""
    return summary


def render(df: pd.DataFrame, selected_fund: int | None) -> None:
    """Render the AI Insights panel."""
    st.header("AI Financial Insights")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    if not api_key:
        st.warning(
            "Add `ANTHROPIC_API_KEY` to your `.env` file to enable AI-powered insights. "
            "Get an API key at https://console.anthropic.com/"
        )
        st.info(
            "When enabled, this panel will analyze your financial data and provide:\n\n"
            "- Key observations and trends\n"
            "- Unusual variances or anomalies\n"
            "- Cash flow concerns or opportunities\n"
            "- Comparison to typical nonprofit benchmarks\n"
            "- Actionable recommendations"
        )
        return

    summary = _summarize_for_prompt(df, selected_fund)

    if st.button("Generate AI Insights", type="primary"):
        with st.spinner("Analyzing financial data..."):
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)

                message = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=1500,
                    messages=[
                        {
                            "role": "user",
                            "content": f"""You are a nonprofit financial analyst. Analyze the following financial data and provide actionable insights. Be specific, reference actual numbers, and flag anything unusual. Format with clear headers and bullet points.

{summary}

Provide:
1. KEY OBSERVATIONS (3-5 bullet points on the overall financial health)
2. NOTABLE TRENDS (what's changing month over month)
3. AREAS OF CONCERN (anything that looks unusual or risky)
4. RECOMMENDATIONS (2-3 actionable suggestions)

Keep it concise and practical for a nonprofit board treasurer.""",
                        }
                    ],
                )

                st.markdown(message.content[0].text)

            except ImportError:
                st.error(
                    "The `anthropic` package is not installed. "
                    "Run: `pip install anthropic`"
                )
            except Exception as e:
                st.error(f"Error generating insights: {e}")

    st.caption(
        "AI insights are generated using Claude and should be reviewed by "
        "qualified financial professionals before making decisions."
    )
