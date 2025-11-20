import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(page_title="Trade PnL Wall Calendar", layout="wide")
st.title("📈 Trade PnL Wall Calendar Dashboard")

def load_data(uploaded_file):
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
    df.columns = [c.strip().replace(" ", "_").replace("-", "_").lower() for c in df.columns]
    return df

def calendar_table(trades_df, target_month, target_year):
    # Calendar grid prep
    monthrange = calendar.monthrange(target_year, target_month)
    first_wday, num_days = monthrange
    days_in_month = [datetime(target_year, target_month, day) for day in range(1, num_days + 1)]
    weeks = []
    week = [None]*first_wday
    for day_dt in days_in_month:
        week.append(day_dt)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week: weeks.append(week + [None]*(7-len(week)))

    # Daily summaries
    pnl_by_day = trades_df.groupby(trades_df['sell_date'].dt.date)['PnL'].sum()
    count_by_day = trades_df.groupby(trades_df['sell_date'].dt.date).size()
    details_by_day = trades_df.groupby(trades_df['sell_date'].dt.date).apply(lambda x: x.to_dict('records'))

    table_vals, cell_colors, cell_hovers = [], [], []
    for week in weeks:
        row_vals, row_colors, row_hovers = [], [], []
        for day in week:
            if day:
                dte = day.date()
                pnl = pnl_by_day.get(dte, 0.0)
                cnt = count_by_day.get(dte, 0)
                details = details_by_day.get(dte, [])
                text = f"<b>{day.day}</b><br>PnL: ${pnl:.2f}<br>Trades: {cnt}"
                # Color logic
                if cnt == 0:
                    color = "#F7F7F7"
                elif pnl > 0:
                    color = "#C6EFCE"  # green
                elif pnl < 0:
                    color = "#FFC7CE"  # red
                else:
                    color = "#D9D9D9"  # neutral
                if details:
                    hover = "Trades:<br>" + "<br>".join([f"{t['Symbol']}: ${t['PnL']:.2f}" for t in details])
                else:
                    hover = f"No Trades"
            else:
                text, color, hover = "", "#FFFFFF", ""
            row_vals.append(text)
            row_colors.append(color)
            row_hovers.append(hover)
        table_vals.append(row_vals)
        cell_colors.append(row_colors)
        cell_hovers.append(row_hovers)

    fig = go.Figure(data=[go.Table(
        header=dict(values=["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
                    fill_color='lightgray', align='center'),
        cells=dict(values=list(zip(*table_vals)),
                   fill_color=cell_colors,
                   align='center',
                   font=dict(color='black', size=12),
                   height=50,
                   hovertext=list(zip(*cell_hovers)),
                   hoverinfo='text'
                  )
    )])
    fig.update_layout(margin=dict(l=15, r=15, b=15, t=30), height=80*len(table_vals)+80)
    return fig

uploaded_file = st.file_uploader("Upload your trades file (.xlsx or .csv)", type=["xlsx", "csv"])

if uploaded_file:
    df = load_data(uploaded_file)
    if df is None:
        st.stop()
    st.write("**Columns detected:**", df.columns.tolist())
    st.dataframe(df.head())

    # Filter trades only
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

    # Prepare columns and match buy/sell
    date_col = 'transaction_date'
    trades_df[date_col] = pd.to_datetime(trades_df[date_col])
    trades_df['action'] = trades_df['action'].astype(str).str.lower().str.strip()
    trades_df = trades_df[trades_df['action'].isin(['buy', 'sell'])]
    trades_df['trade_id'] = trades_df[date_col].astype(str) + '_' + \
                            trades_df['symbol'].astype(str) + '_' + \
                            trades_df['action'].astype(str) + '_' + \
                            trades_df['quantity'].astype(str) + '_' + \
                            trades_df['price'].astype(str)
    trades_df = trades_df.drop_duplicates('trade_id')

    # Match logic (Matches the most basic: Buy→Sell same qty, per symbol/account)
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

    # Calendar navigation
    trades_final['sell_date'] = pd.to_datetime(trades_final['Sell Date'])
    months = sorted(trades_final['sell_date'].dt.to_period('M').unique())
    if months:
        default_period = months[-1]
        default_month = default_period.month
        default_year = default_period.year
    else:
        today = datetime.today()
        default_month = today.month
        default_year = today.year

    # Month/year selector
    sel_year = st.selectbox("Year", sorted(list(set([d.year for d in trades_final['sell_date']]))), index=0 if default_year not in [d.year for d in trades_final['sell_date']] else sorted(list(set([d.year for d in trades_final['sell_date']]))).index(default_year))
    sel_month = st.selectbox("Month", list(range(1,13)), format_func=lambda m: calendar.month_name[m], index=default_month-1)

    st.subheader(f"PnL Calendar: {calendar.month_name[sel_month]} {sel_year}")
    calendar_fig = calendar_table(trades_final, sel_month, sel_year)
    st.plotly_chart(calendar_fig, use_container_width=True)

    # Summary bar charts
    trades_final['YearWeek'] = trades_final['sell_date'].dt.strftime("%Y-W%U")
    trades_final['YearMonth'] = trades_final['sell_date'].dt.to_period('M').astype(str)
    st.subheader("Weekly PnL (Bar Chart)")
    st.bar_chart(trades_final.groupby('YearWeek')['PnL'].sum())
    st.subheader("Monthly PnL (Bar Chart)")
    st.bar_chart(trades_final.groupby('YearMonth')['PnL'].sum())
    st.write("**PnL by Ticker**")
    st.bar_chart(trades_final.groupby('Symbol')['PnL'].sum())
    st.write("**PnL by Account**")
    st.bar_chart(trades_final.groupby('Account')['PnL'].sum())

    st.download_button("Download Detailed Trades", trades_final.to_csv(index=False), file_name="detailed_trades.csv", mime='text/csv')
else:
    st.info("Upload your trade data file (Excel/CSV) to begin.")
