import pandas as pd
from data_loader import get_latest_csv, load_and_combine
import streamlit as st

df = load_and_combine(get_latest_csv())

re_df = df[df["Category"].isin(["Revenue", "Expense"])]
pivot = pd.pivot_table(
    re_df, 
    values="net", 
    index=["Category", "Subcategory", "Account Description"], 
    columns="Fund Name", 
    aggfunc="sum",
    fill_value=0
)
pivot["Total"] = pivot.sum(axis=1)

print(pivot.head())
