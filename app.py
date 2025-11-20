import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Trade PnL Dashboard", layout="wide")
st.title("📈 Trade PnL Dashboard")

def load_data(uploaded_file):
    # Try to read Excel/CSV with correct engine
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
    # Normalize all column names: lower/underscores/strip spaces
    df.columns = [c.strip().replace(" ", "_").replace("-", "_").lower() for c in df.columns]
    return df

uploaded_file = st.file_uploader("Upload your trades file (.xlsx or .csv)", type=["xlsx", "csv"])

if uploaded_file:
    df = load_data(uploaded_file)
    if df is None:
        st.stop()
    st.write("**Columns detected:**", df.columns.tolist())
    st.dataframe(df.head())

    # Check for date column (common patterns)
    date_candidates = [col for col in df.columns if "date" in col]
    # User chooses if there are multiple
    if not date_candidates:
        st.error("No column containing 'date' found. Please verify your file.")
        st.stop()
    date_col = st.selectbox("Select the date column:", date_candidates)
    try:
        df[date_col] = pd.to_datetime(df[date_col])
    except Exception as e:
        st.error(f"Could not convert date column: {e}")
        st.stop()

    # Find key fields
    col_map = {}
    suggestions = {
        'symbol': ['symbol', 'ticker'],
        'action': ['action', 'side', 'trade_type'],
        'quantity': ['quantity', 'qty', 'shares'],
        'price': ['price', 'entry_price'],
        'net_amount': ['net_amount', 'value', 'amount', 'pnl']
    }
    for k, options in suggestions.items():
        for o in options:
            found = [c for c in df.columns if o in c]
            if found:
                col_map[k] = found[0]
                break

    # User override for each mandatory field
    for field in ['symbol', 'action', 'quantity', 'price', 'net_amount']:
        if field not in col_map:
            col_map[field] = st.selectbox(
                f"Select column for {field.replace('_', ' ').title()}:",
                df.columns.tolist()
            )

    # Deduplication logic - robust trade ID computation
    df['trade_id'] = df[date_col].astype(str) + '_' + \
                     df[col_map['symbol']].astype(str) + '_' + \
                     df[col_map['action']].astype(str) + '_' + \
                     df[col_map['quantity']].astype(str) + '_' + \
                     df[col_map['price']].astype(str)
    df = df.drop_duplicates(subset=['trade_id'])

    # Basic trade matching (Long only: match each Buy with next Sell of same qty)
    df = df.sort_values(date_col)
    trades = []
    g = df.groupby(col_map['symbol'])
    for sym, group in g:
        symbol_trades = group.copy()
        buys = symbol_trades[symbol_trades[col_map['action']].str.lower() == 'buy']
        sells = symbol_trades[symbol_trades[col_map['action']].str.lower() == 'sell']
        used_sells = set()
        for i, buy in buys.iterrows():
            candidates = sells[(abs(sells[col_map['quantity']]) == abs(buy[col_map['quantity']])) & (~sells.index.isin(used_sells))]
            if not candidates.empty:
                sell = candidates.iloc[0]
                pnl = float(sell[col_map['net_amount']]) + float(buy[col_map['net_amount']])
                trade = {
                    'Symbol': sym,
                    'Buy Date': buy[date_col],
                    'Sell Date': sell[date_col],
                    'Entry Price': buy[col_map['price']],
                    'Exit Price': sell[col_map['price']],
                    'Quantity': buy[col_map['quantity']],
                    'PnL': pnl,
                }
                trades.append(trade)
                used_sells.add(sell.name)

    if not trades:
        st.warning("No matched trades found for PnL calculation. Check your data.")
        st.stop()

    trades_df = pd.DataFrame(trades)

    st.subheader("Matched Trades")
    st.dataframe(trades_df)

    # PnL by day, week, month
    trades_df['Sell Date'] = pd.to_datetime(trades_df['Sell Date'])
    trades_df['YearMonth'] = trades_df['Sell Date'].dt.to_period('M').astype(str)
    trades_df['YearWeek'] = trades_df['Sell Date'].dt.strftime("%Y-W%U")
    st.subheader("Summary")
    st.write("**Daily PnL**")
    st.bar_chart(trades_df.groupby('Sell Date')['PnL'].sum())

    st.write("**Weekly PnL**")
    st.bar_chart(trades_df.groupby('YearWeek')['PnL'].sum())

    st.write("**Monthly PnL**")
    st.bar_chart(trades_df.groupby('YearMonth')['PnL'].sum())

    st.write("**PnL by Ticker**")
    st.bar_chart(trades_df.groupby('Symbol')['PnL'].sum())

    st.download_button("Download Detailed Trades", trades_df.to_csv(index=False), file_name="detailed_trades.csv", mime='text/csv')

else:
    st.info("Upload your trade data file (Excel/CSV) to begin.")
