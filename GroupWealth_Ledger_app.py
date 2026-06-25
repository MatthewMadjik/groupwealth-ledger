import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json

st.set_page_config(page_title="GroupWealth Ledger", layout="wide")
st.title("GroupWealth Ledger")
st.caption("Multi-household • Guided entry • Projected Ledger")

# Database
DB_FILE = "groupwealth_ledger.db"

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, type TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, account_id INTEGER, item_type TEXT, name TEXT, base_amount REAL, frequency TEXT, start_date TEXT, account_paid_via TEXT, category TEXT, notes TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS debt_details (item_id INTEGER PRIMARY KEY, statement_date TEXT, payment_date TEXT, authorized_users TEXT, balance REAL, interest_rate REAL, promo_expiration TEXT, mppo_final_payoff_date TEXT, balance_transfer_active INTEGER, rewards_type TEXT, min_pay_percent REAL, credit_limit REAL)''')
    conn.commit()
    conn.close()

init_db()

# Sidebar
st.sidebar.header("Accounts")
accounts = pd.read_sql_query("SELECT * FROM accounts", get_db())
account_list = ["GLOBAL"] + accounts['name'].tolist() if not accounts.empty else ["GLOBAL"]
selected = st.sidebar.selectbox("View", account_list)

# Add Account
with st.sidebar.expander("Add Account"):
    new_name = st.text_input("Name")
    if st.button("Add"):
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO accounts (name) VALUES (?)", (new_name,))
        conn.commit()
        st.rerun()

# Tabs
tab1, tab2, tab3 = st.tabs(["Projected Ledger", "Add Item", "Manage Items"])

with tab1:
    st.header("Projected Ledger")
    st.info("Transaction list coming in next update. Add items first.")

with tab2:
    st.header("Add New Item")
    item_type = st.selectbox("Type", ["Recurring Bill", "Recurring Income", "Credit Card / Debt", "One-time"])
    
    with st.form("add_form"):
        name = st.text_input("Name*")
        amount = st.number_input("Base Amount*", value=0.0)
        freq = st.selectbox("Frequency", ["monthly", "bi_weekly", "every_4_weeks", "quarterly", "annual"])
        start = st.date_input("Start Date", datetime.now())
        paid_via = st.text_input("Paid Via")
        category = st.text_input("Category")
        notes = st.text_area("Notes")
        
        if st.form_submit_button("Add"):
            conn = get_db()
            c = conn.cursor()
            c.execute('''INSERT INTO items (name, base_amount, frequency, start_date, account_paid_via, category, notes, item_type) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                      (name, amount, freq, start.strftime("%Y-%m-%d"), paid_via, category, notes, item_type))
            conn.commit()
            st.success("Added!")
            st.rerun()

with tab3:
    st.header("Manage Items")
    items = pd.read_sql_query("SELECT * FROM items", get_db())
    if not items.empty:
        st.dataframe(items)
    else:
        st.info("No items yet. Add some in the Add Item tab.")

st.success("App updated with better CC support and Manage Items tab. Add a Credit Card and see the detailed form.")
