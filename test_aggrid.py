import pandas as pd
from data_loader import get_latest_csv, load_and_combine
import streamlit as st

st.set_page_config(layout="wide")
st.title("AgGrid Grouping Test")

from dashboards.matrix_grid import render_matrix

df = load_and_combine(get_latest_csv())
render_matrix(df, "Expense", selected_fund=1)
