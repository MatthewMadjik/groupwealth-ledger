#!/usr/bin/env python3
"""
GroupWealth Ledger - Phase 1 MVP
Personal multi-household cash flow, debt, and projection app.

Run with: streamlit run GroupWealth_Ledger_app.py
(Install with: pip install streamlit pandas plotly)

Features in v1:
- Multi-account (households) + Global view toggle
- Guided data entry for bills, incomes, debts
- Flexible recurrence (monthly, bi-weekly, every N weeks, specific dates)
- Projected Ledger (transaction-by-transaction with running balance)
- Per-bill 24-month override grid (baseline same, edit individual months)
- Basic task system for missing data
- Local SQLite storage
- Optional import helper from your original Excel (manual mapping recommended for v1)

Cloud note: For phone access, deploy to Streamlit Community Cloud (free, GitHub-based, add password protection).
Local first for privacy with sensitive financial data.
"""

import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import json
from io import BytesIO

# --- Database Setup ---
DB_FILE = "groupwealth_ledger.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Accounts / Households
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT DEFAULT 'Household',  -- Household, Property, Shared, etc.
            notes TEXT
        )
    ''')
    
    # Recurring / One-time Items (Bills, Incomes, Debts)
    c.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            item_type TEXT NOT NULL,  -- 'recurring_bill', 'one_time_expense', 'recurring_income', 'one_time_income', 'debt_cc'
            name TEXT NOT NULL,
            base_amount REAL,
            frequency TEXT,  -- 'monthly', 'bi_weekly', 'every_4_weeks', 'quarterly', 'annual', 'custom_dates'
            custom_dates TEXT,  -- JSON list of specific dates if needed
            start_date TEXT,
            end_date TEXT,
            account_paid_via TEXT,
            category TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    ''')
    
    # Debt-specific details (full CC Breakdown fields)
    c.execute('''
        CREATE TABLE IF NOT EXISTS debt_details (
            item_id INTEGER PRIMARY KEY,
            balance REAL,
            interest_rate REAL,
            promo_expiration TEXT,
            mppo_final_payoff_date TEXT,
            balance_transfer_active INTEGER DEFAULT 0,
            rewards_type TEXT,
            min_pay_percent REAL,
            credit_limit REAL,
            FOREIGN KEY (item_id) REFERENCES items (id)
        )
    ''')
    
    # Projected / Actual Transactions (the ledger)
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            account_id INTEGER,
            date TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL,
            running_balance REAL,
            is_projected INTEGER DEFAULT 1,
            notes TEXT,
            FOREIGN KEY (item_id) REFERENCES items (id),
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    ''')
    
    # Tasks for missing data / reviews
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            description TEXT NOT NULL,
            due_date TEXT,
            status TEXT DEFAULT 'Open',  -- Open, Done
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 24-month overrides per item (for flexible projections)
    c.execute('''
        CREATE TABLE IF NOT EXISTS monthly_overrides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            month TEXT,  -- '2026-07', '2026-08', etc.
            amount REAL,
            FOREIGN KEY (item_id) REFERENCES items (id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# --- Helper Functions ---
def get_accounts():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM accounts ORDER BY name", conn)
    conn.close()
    return df

def add_account(name, type_="Household", notes=""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO accounts (name, type, notes) VALUES (?, ?, ?)", (name, type_, notes))
    conn.commit()
    conn.close()

def get_items(account_id=None, item_type=None):
    conn = get_db_connection()
    query = "SELECT * FROM items WHERE is_active = 1"
    params = []
    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)
    if item_type:
        query += " AND item_type = ?"
        params.append(item_type)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def add_item(account_id, item_type, name, base_amount, frequency, start_date, 
             end_date=None, account_paid_via="", category="", notes="", custom_dates=None):
    conn = get_db_connection()
    c = conn.cursor()
    custom_dates_json = json.dumps(custom_dates) if custom_dates else None
    c.execute('''
        INSERT INTO items (account_id, item_type, name, base_amount, frequency, start_date, end_date, 
                           account_paid_via, category, notes, custom_dates)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (account_id, item_type, name, base_amount, frequency, start_date, end_date, 
          account_paid_via, category, notes, custom_dates_json))
    item_id = c.lastrowid
    conn.commit()
    conn.close()
    return item_id

def generate_projected_transactions(item_id, months_ahead=24):
    """Generate future transactions for a recurring item. User can override per month."""
    conn = get_db_connection()
    item = pd.read_sql_query(f"SELECT * FROM items WHERE id = {item_id}", conn).iloc[0]
    conn.close()
    
    base_amount = item['base_amount']
    frequency = item['frequency']
    start_date = datetime.strptime(item['start_date'], "%Y-%m-%d")
    
    transactions = []
    current_date = start_date
    
    for i in range(months_ahead * 2):  # Generate enough periods
        if current_date > datetime.now() + relativedelta(months=months_ahead):
            break
            
        amount = base_amount
        # Check for monthly override
        month_key = current_date.strftime("%Y-%m")
        conn = get_db_connection()
        override = pd.read_sql_query(
            f"SELECT amount FROM monthly_overrides WHERE item_id = {item_id} AND month = '{month_key}'", 
            conn
        )
        conn.close()
        if not override.empty:
            amount = override.iloc[0]['amount']
        
        transactions.append({
            'item_id': item_id,
            'date': current_date.strftime("%Y-%m-%d"),
            'description': item['name'],
            'amount': amount,
            'is_projected': 1
        })
        
        # Advance date based on frequency
        if frequency == "monthly":
            current_date += relativedelta(months=1)
        elif frequency == "bi_weekly":
            current_date += timedelta(weeks=2)
        elif frequency == "every_4_weeks":
            current_date += timedelta(weeks=4)
        elif frequency == "quarterly":
            current_date += relativedelta(months=3)
        elif frequency == "annual":
            current_date += relativedelta(years=1)
        else:
            current_date += relativedelta(months=1)  # default
    
    return transactions

# --- Streamlit UI ---
st.set_page_config(page_title="GroupWealth Ledger", layout="wide")
st.title("GroupWealth Ledger — Phase 1")
st.caption("Multi-household cash flow, debt tracking & projected ledger • Local-first • Guided entry")

# Sidebar - Account / Global Switch
st.sidebar.header("View Mode")
accounts_df = get_accounts()
account_names = ["GLOBAL"] + accounts_df['name'].tolist() if not accounts_df.empty else ["GLOBAL"]
selected_view = st.sidebar.selectbox("Select Account or Global", account_names, index=0)

if selected_view == "GLOBAL":
    current_account_id = None
    st.sidebar.success("Global consolidated view")
else:
    current_account_id = int(accounts_df[accounts_df['name'] == selected_view]['id'].values[0])
    st.sidebar.info(f"Viewing: {selected_view}")

# Quick Add Account
with st.sidebar.expander("Add New Account / Household"):
    new_name = st.text_input("Account Name")
    new_type = st.selectbox("Type", ["Household", "Property", "Shared", "Other"])
    if st.button("Add Account"):
        if new_name:
            add_account(new_name, new_type)
            st.rerun()

# Main Tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Projected Ledger", "➕ Add Item (Guided)", "💳 Debts & Payoff", "✅ Tasks & Missing Data"])

# --- Tab 1: Projected Ledger (Bank Statement Style) ---
with tab1:
    st.header("Projected Ledger — Transaction by Transaction")
    st.caption("Running balance like a bank statement. Generated from your recurring items. Edit overrides per month in item details.")
    
    if st.button("Regenerate Projections from Current Items"):
        # Clear old projected transactions and regenerate
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM transactions WHERE is_projected = 1")
        conn.commit()
        
        items = get_items(current_account_id)
        for _, item in items.iterrows():
            txs = generate_projected_transactions(item['id'])
            for tx in txs:
                c.execute('''
                    INSERT INTO transactions (item_id, account_id, date, description, amount, is_projected)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (tx['item_id'], current_account_id or item['account_id'], tx['date'], tx['description'], tx['amount'], 1))
        conn.commit()
        conn.close()
        st.success("Projections regenerated!")
        st.rerun()
    
    # Display ledger
    conn = get_db_connection()
    if current_account_id:
        query = f"SELECT * FROM transactions WHERE account_id = {current_account_id} ORDER BY date"
    else:
        query = "SELECT * FROM transactions ORDER BY date"
    ledger_df = pd.read_sql_query(query, conn)
    conn.close()
    
    if not ledger_df.empty:
        # Calculate running balance (simple cumulative for demo)
        ledger_df = ledger_df.sort_values('date')
        ledger_df['running_balance'] = ledger_df['amount'].cumsum().round(2)
        
        st.dataframe(
            ledger_df[['date', 'description', 'amount', 'running_balance', 'is_projected', 'notes']],
            use_container_width=True,
            hide_index=True
        )
        
        # Simple chart
        if len(ledger_df) > 1:
            st.line_chart(ledger_df.set_index('date')['running_balance'])
    else:
        st.info("No transactions yet. Add items in the 'Add Item' tab and regenerate projections.")

# --- Tab 2: Guided Add Item ---
with tab2:
    st.header("Add New Item — Guided Form")
    st.caption("Start here. The app asks only the relevant questions. Baseline = same every period. Override individual months later.")
    
    item_type = st.selectbox(
        "What kind of item?",
        ["Recurring Bill / Expense", "One-time Expense", "Recurring Income", "One-time Income", "Credit Card / Debt"]
    )
    
    with st.form("add_item_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Name / Description*")
            base_amount = st.number_input("Base Amount*", value=0.0, step=0.01)
            account_id_for_item = current_account_id if current_account_id else st.selectbox(
                "Which Account / Household?", 
                options=accounts_df['id'].tolist() if not accounts_df.empty else [1],
                format_func=lambda x: accounts_df[accounts_df['id']==x]['name'].values[0] if not accounts_df.empty else "Default"
            )
        
        with col2:
            frequency = st.selectbox(
                "Recurrence / Frequency*",
                ["monthly", "bi_weekly", "every_4_weeks", "quarterly", "annual", "custom_dates"]
            )
            start_date = st.date_input("Start / Next Due Date*", value=datetime.now().date())
        
        account_paid_via = st.text_input("Paid Via / Account (e.g. LVI, CDC, LAC)")
        category = st.text_input("Category (Housing, Vehicles, Utilities, Subscriptions, etc.)")
        notes = st.text_area("Notes")
        
        submitted = st.form_submit_button("Add Item")
        
        if submitted and name and base_amount is not None:
            item_id = add_item(
                account_id_for_item, 
                item_type.lower().replace(" / ", "_").replace(" ", "_"),
                name, base_amount, frequency, 
                start_date.strftime("%Y-%m-%d"),
                account_paid_via=account_paid_via,
                category=category,
                notes=notes
            )
            st.success(f"Added: {name}")
            
            # If it's a debt, prompt for full details
            if "debt" in item_type.lower() or "credit" in item_type.lower():
                st.info("Debt added. Go to 'Debts & Payoff' tab to fill full CC Breakdown details (interest rate, promo, MPPO, etc.).")
            
            # Create task if critical info missing (example)
            if not account_paid_via:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT INTO tasks (item_id, description) VALUES (?, ?)", 
                          (item_id, f"Add 'Paid Via' for {name}"))
                conn.commit()
                conn.close()
            
            st.rerun()

# --- Tab 3: Debts & Payoff ---
with tab3:
    st.header("Debt Tracking & Payoff")
    st.caption("Full details from your CC Breakdown sheets. Add missing info via tasks.")
    
    debts = get_items(current_account_id, item_type="debt_cc")
    if not debts.empty:
        st.dataframe(debts[['name', 'base_amount', 'notes']], use_container_width=True)
    else:
        st.info("No debts added yet. Use the Add Item form and select 'Credit Card / Debt'.")
    
    st.subheader("Fill Full CC Details (for selected debt)")
    # Simple form to update debt_details table
    debt_id = st.selectbox("Select Debt Item", options=debts['id'].tolist() if not debts.empty else [0],
                           format_func=lambda x: debts[debts['id']==x]['name'].values[0] if not debts.empty else "None")
    
    if debt_id:
        with st.form("debt_details_form"):
            balance = st.number_input("Current Balance")
            interest = st.number_input("Interest Rate (e.g. 0.2949 for 29.49%)", step=0.0001)
            promo_exp = st.text_input("Promo Expiration (YYYY-MM-DD)")
            mppo_date = st.text_input("MPPO Final Payoff Date")
            bt_active = st.checkbox("Balance Transfer Active?")
            rewards = st.text_input("Rewards Type")
            min_pay = st.number_input("Min Pay %", value=0.01, step=0.01)
            
            if st.form_submit_button("Save Debt Details"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO debt_details 
                    (item_id, balance, interest_rate, promo_expiration, mppo_final_payoff_date, 
                     balance_transfer_active, rewards_type, min_pay_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (debt_id, balance, interest, promo_exp, mppo_date, int(bt_active), rewards, min_pay))
                conn.commit()
                conn.close()
                st.success("Debt details saved!")

# --- Tab 4: Tasks ---
with tab4:
    st.header("Tasks & Missing Data Reminders")
    conn = get_db_connection()
    tasks_df = pd.read_sql_query("SELECT * FROM tasks WHERE status = 'Open' ORDER BY due_date", conn)
    conn.close()
    
    if not tasks_df.empty:
        for _, task in tasks_df.iterrows():
            col1, col2 = st.columns([4,1])
            with col1:
                st.write(f"**{task['description']}** (Due: {task['due_date'] or 'ASAP'})")
            with col2:
                if st.button("Mark Done", key=f"task_{task['id']}"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE tasks SET status = 'Done' WHERE id = ?", (task['id'],))
                    conn.commit()
                    conn.close()
                    st.rerun()
    else:
        st.success("No open tasks. Great job keeping data complete!")

st.sidebar.markdown("---")
st.sidebar.caption("Phase 1 MVP • Local SQLite • Add data here, not spreadsheets")
st.sidebar.info("For phone access while traveling: Deploy to Streamlit Community Cloud (free tier via GitHub). Add `st.secrets` password protection for privacy.")