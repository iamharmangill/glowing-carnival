import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import calplot

st.set_page_config(page_title="Trade PnL Calendar Dashboard", layout="wide")
st.title("📈 Trade PnL Calendar Dashboard")

def load_data(uploaded_file):
    # Read Excel or CSV file
    try:
        if uploaded_file.name.endswith('.xlsx'):
            df = pd.read_excel(uploaded_file, engine='openpyxl')
        elif uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            st.error("Unsupported file type. Please upload .xlsx or .csv")
            return None
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return None
    # Normalize all column names for reliable access
    df.columns = [c.strip().replace(" ", "_").replace("-", "_").lower() for c in df.columns]
    return df

uploaded_file = st.file_uploader("Upload your trades file (.xlsx or .csv)", type=["xlsx", "csv"])

if uploaded_file:
    df = load_data(uploaded_file)
    if df is None:
        st.stop()
    st.write("**Columns detected:**", df.columns.tolist())
    st.dataframe(df.head())

    # Filter only real trades: 'activity_type' == 'trades'
    if 'activity_type' not in df.columns:
        st.error("Missing 'Activity Type' column; cannot filter trades.")
        st.stop()
    trades_df = df[df['activity_type'].str.lower() == 'trades'].copy()

    # Account selector
    acct_col = 'account_#' if 'account_#' in trades_df.columns else st.selectbox("Select your account column:", trades_df.columns.tolist())
    avail_accounts = sorted(trades_df[acct_col].dropna().unique().tolist())
    selected_account = st.selectbox("Show trades for account:", ['All'] + avail_accounts)
    if selected_account != 'All':
        trades_df = trades_df[trades_df[acct_col] == selected_account]

    # Parse date column
    date_col = 'transaction_date'
    trades_df[date_col] = pd.to_datetime(trades_df[date_col])

    # Actions: Make sure they're string, lowercase, and just buy/sell
    trades_df['action'] = trades_df['action'].astype(str).str.lower().str.strip()
    trades_df = trades_df[trades_df['action'].isin(['buy', 'sell'])]

    # Deduplicate by trade id
    trades_df['trade_id'] = trades_df[date_col].astype(str) + '_' + trades_df['symbol'].astype(str) + '_' + trades_df['action'].astype(str) + '_' + trades_df['quantity'].astype(str) + '_' + trades_df['price'].astype(str)
    trades_df = trades_df.drop_duplicates('trade_id')

    # Match buy/sell by symbol/account
    group_keys = ['symbol']
    if acct_col:
        group_keys.append(acct_col)
    trades_df = trades_df.sort_values(date_col)
    grouped = trades_df.groupby(group_keys)

    trades_summary = []
    for name, group in grouped:
        buys = group[group['action'] == 'buy']
        sells = group[group['action'] == 'sell']
        used_sells = set()
        for i, buy in buys.iterrows():
            candidates = sells[
                (abs(sells['quantity']) == abs(buy['quantity'])) & 
                (~sells.index.isin(used_sells))
            ]
            if not candidates.empty:
                sell = candidates.iloc[0]
                pnl = float(sell['net_amount']) + float(buy['net_amount'])
                entry_date, exit_date = buy[date_col], sell[date_col]
                result = {
                    'Account': buy[acct_col],
                    'Symbol': buy['symbol'],
                    'Buy Date': entry_date,
                    'Sell Date': exit_date,
                    'Entry Price': buy['price'],
                    'Exit Price': sell['price'],
                    'Quantity': buy['quantity'],
                    'PnL': pnl,
                }
                trades_summary.append(result)
                used_sells.add(sell.name)

    if not trades_summary:
        st.warning("No matched Buy/Sell trade pairs found. Check that your file includes trades with both actions.")
        st.dataframe(trades_df)
        st.stop()

    trades_final = pd.DataFrame(trades_summary)
    st.subheader("Matched Trades")
    st.dataframe(trades_final)

    # Calendar heatmap for daily PnL
    trades_final['Sell Date'] = pd.to_datetime(trades_final['Sell Date'])
    calendar_pnl = trades_final.groupby(trades_final['Sell Date'].dt.date)['PnL'].sum()
    calendar_pnl.index = pd.to_datetime(calendar_pnl.index)

    st.subheader("Calendar Heatmap: Daily PnL")
    fig, ax = calplot.calplot(calendar_pnl, cmap='RdYlGn', colorbar=True, suptitle='Daily PnL Calendar')
    st.pyplot(fig)

    # Weekly bar chart
    trades_final['YearWeek'] = trades_final['Sell Date'].dt.strftime("%Y-W%U")
    st.subheader("Weekly PnL (Bar Chart)")
    st.bar_chart(trades_final.groupby('YearWeek')['PnL'].sum())

    # Monthly bar chart
    trades_final['YearMonth'] = trades_final['Sell Date'].dt.to_period('M').astype(str)
    st.subheader("Monthly PnL (Bar Chart)")
    st.bar_chart(trades_final.groupby('YearMonth')['PnL'].sum())

    st.write("**PnL by Ticker**")
    st.bar_chart(trades_final.groupby('Symbol')['PnL'].sum())

    st.write("**PnL by Account**")
    st.bar_chart(trades_final.groupby('Account')['PnL'].sum())

    st.download_button(
        "Download Detailed Trades",
        trades_final.to_csv(index=False), file_name="detailed_trades.csv", mime='text/csv')

else:
    st.info("Upload your trade data file (Excel/CSV) to begin.")
