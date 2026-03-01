"""Budget vs Actuals dashboard (placeholder - Phase 2)."""

from __future__ import annotations

import streamlit as st
import pandas as pd


def render(df: pd.DataFrame, selected_fund: int | None) -> None:
    st.header("Budget vs Actuals")

    st.info(
        "Budget data is not yet configured. Once budget data is available "
        "(from OnRealm export or manual upload), this dashboard will show:\n\n"
        "- **Budget vs Actual** comparison by account\n"
        "- **Variance analysis** ($ and %)\n"
        "- **Waterfall chart** showing largest variances\n"
        "- **Monthly burn rate** vs budget pace\n\n"
        "To get started, export budget data from OnRealm or prepare a CSV with "
        "columns: `Account`, `Budget Amount`."
    )

    # Placeholder for future CSV upload
    uploaded = st.file_uploader(
        "Upload budget CSV (optional)",
        type=["csv"],
        help="CSV with columns: Account, Budget Amount",
    )

    if uploaded is not None:
        st.warning("Budget upload processing coming soon.")
