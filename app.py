import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

st.set_page_config(page_title="Trade PnL Dashboard", layout="wide")

st.title("📈 Trade PnL Dashboard")

# Helper: parse and normalize uploaded file
@st.cache_data(show_spinner=False)
def load_data(uploaded_file):
    df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]
    # Minimal normalization; expand as needed to match your broker export
    df['Transaction_Date'] = pd.to_datetime(df['Transaction_Date'])
    return df

# File upload and deduplication logic
uploaded_file = st.file_uploader("Upload your trade file (.xlsx or .csv)", type=["xlsx", "csv"])

if uploaded_file:
    df = load_data(uploaded_file)
    # Unique identifier: Transaction_Date + Symbol + Action + Quantity + Price
    df['trade_id'] = df.apply(
        lambda r: f"{r['Transaction_Date']}_{r['Symbol']}_{r['Action']}_{r['Quantity']}_{r['Price']}", axis=1)
    # Simulate loading 'existing trades' with session state (could be a DB in production)
    if 'all_trades' not in st.session_state:
        st.session_state['all_trades'] = pd.DataFrame(columns=df.columns)
    old_trades = st.session_state['all_trades']

    # Deduplicate: add only new trades
    new_trades = df[~df['trade_id'].isin(old_trades['trade_id'])]
    st.session_state['all_trades'] = pd.concat([old_trades, new_trades], ignore_index=True).drop_duplicates('trade_id')

    st.success(f"{len(new_trades)} new trades added. Total tracked: {len(st.session_state['all_trades'])}")

    display_df = st.session_state['all_trades'].copy()

    # Match buy/sell for PnL computation (expand as needed)
    trades = []
    display_df = display_df.sort_values('Transaction_Date')
    by_symbol = display_df.groupby('Symbol')

    for sym, group in by_symbol:
        buys = group[group['Action'].str.lower() == 'buy']
        sells = group[group['Action'].str.lower() == 'sell']
        for i, buy in buys.iterrows():
            match = sells[sells['Quantity'].abs() == buy['Quantity'].abs()]
            if not match.empty:
                sell = match.iloc[0]
                pnl = sell['Net_Amount'] + buy['Net_Amount']
                trades.append({
                    'Symbol': sym,
                    'BuyDate': buy['Transaction_Date'],
                    'SellDate': sell['Transaction_Date'],
                    'Entry': buy['Price'],
                    'Exit': sell['Price'],
                    'Quantity': buy['Quantity'],
                    'PnL': pnl
                })
                sells = sells.drop(match.index[0])
    pnl_df = pd.DataFrame(trades)

    st.subheader("Trade Summary Table")
    st.dataframe(pnl_df, use_container_width=True)

    # Dashboard views
    if not pnl_df.empty:
        pnl_df['SellDate'] = pd.to_datetime(pnl_df['SellDate'])
        pnl_df['YearMonth'] = pnl_df['SellDate'].dt.to_period('M')
        pnl_df['YearWeek'] = pnl_df['SellDate'].dt.isocalendar().week

        with st.expander("Daily/Weekly/Monthly PnL"):
            st.line_chart(data=pnl_df.groupby('SellDate')['PnL'].sum())
            st.bar_chart(data=pnl_df.groupby('YearWeek')['PnL'].sum())
            st.bar_chart(data=pnl_df.groupby('YearMonth')['PnL'].sum())

        st.subheader("Ticker PnL")
        st.bar_chart(pnl_df.groupby('Symbol')['PnL'].sum())

        st.download_button("Download Processed Data", pnl_df.to_csv(index=False), file_name="processed_trades.csv",
                           mime='text/csv')
else:
    st.info("Upload your Excel/CSV trade data to get started.")
