from __future__ import annotations

import json
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode

def render_matrix(
    df: pd.DataFrame, 
    category: str, 
    selected_fund: int | None = None,
    height: int = 400,
    value_col: str = "net",
    pivot_by: str = "fund" # or "category"
) -> None:
    """Render an interactive drill-down matrix with Funds as columns."""
    
    # Filter by category
    cat_df = df[df["Category"] == category].copy()
    
    if selected_fund is not None and "Fund" in cat_df.columns:
        cat_df = cat_df[cat_df["Fund"] == selected_fund]
    elif selected_fund is not None and "Fund Name" in cat_df.columns:
        from chart_of_accounts import get_fund_name
        cat_df = cat_df[cat_df["Fund Name"] == get_fund_name(selected_fund)]

    if cat_df.empty:
        st.info(f"No {category} data found.")
        return

    if pivot_by == "category":
        index_cols = ["Fund Name", "L1", "L2", "L3", "Account Description"]
        columns_col = "Unified"
    else:
        index_cols = ["Unified", "L1", "L2", "L3", "Account Description"]
        columns_col = "Fund Name"

    # Pivot table
    pivot = pd.pivot_table(
        cat_df,
        values=value_col,
        index=index_cols,
        columns=columns_col,
        aggfunc="sum",
        fill_value=0
    ).reset_index()

    value_cols = [c for c in pivot.columns if c not in index_cols]
    value_cols = sorted(value_cols)
    
    # Calculate Total
    pivot["Total"] = pivot[value_cols].sum(axis=1)

    # Convert to float for AgGrid currency formatting
    for c in value_cols + ["Total"]:
        pivot[c] = pivot[c].astype(float)

    # Configure AgGrid
    # Create the dynamic path array for TreeData (removes empty lists)
    pivot["path"] = pivot.apply(
        lambda r: json.dumps([x for x in [r[c] for c in index_cols] if x and pd.notna(x) and x != ""]), 
        axis=1
    )

    gb = GridOptionsBuilder.from_dataframe(pivot)
    
    # Hide the raw hierarchy columns
    for col in index_cols:
        gb.configure_column(col, hide=True)
    gb.configure_column("path", hide=True)

    # Format the value columns
    for col in value_cols + ["Total"]:
        gb.configure_column(
            col, 
            header_name=col,
            type=["numericColumn", "numberColumnFilter", "customNumericFormat"], 
            precision=2, 
            aggFunc="sum",
            valueFormatter="x.toLocaleString('en-US', {style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2})"
        )

    # Configure the treeData and drill-down column
    gb.configure_grid_options(
        treeData=True,
        getDataPath=JsCode("function(data){ return JSON.parse(data.path); }"),
        autoGroupColumnDef={
            "headerName": "Subcategory / Account", 
            "minWidth": 350, 
            "cellRendererParams": {
                "suppressCount": True,
            }
        },
        groupDisplayType='singleColumn'
    )

    gridOptions = gb.build()

    AgGrid(
        pivot,
        gridOptions=gridOptions,
        enable_enterprise_modules=True,
        update_mode=GridUpdateMode.NO_UPDATE,
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
        height=height,
        theme="streamlit"
    )
