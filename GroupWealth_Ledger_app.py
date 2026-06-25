import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="GroupWealth Ledger", layout="wide")
st.title("GroupWealth Ledger")
st.caption("Multi-household cash flow • Guided entry • Projected ledger")

# DB
conn = sqlite3.connect("ledger.db", check_same_thread=False)
conn.row_factory = sqlite3.Row

# Init tables
conn.execute('''CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE)''')
conn.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, account_id INTEGER, type TEXT, name TEXT, amount REAL, frequency TEXT, start_date TEXT, paid_via TEXT, category TEXT, notes TEXT)''')
conn.execute('''CREATE TABLE IF NOT EXISTS cc_details (item_id INTEGER PRIMARY KEY, statement_date TEXT, payment_date TEXT, authorized_users TEXT, balance REAL, interest_rate REAL, promo_expiration TEXT, mppo_date TEXT, bt_active INTEGER, rewards TEXT)''')

st.sidebar.header("Accounts")
accounts = pd.read_sql("SELECT * FROM accounts", conn)
account_list = ["GLOBAL"] + accounts['name'].tolist() if not accounts.empty else ["GLOBAL"]
view = st.sidebar.selectbox("View", account_list)

# Add account
with st.sidebar.expander("Add Account"):
    name = st.text_input("Name")
    if st.button("Add"):
        conn.execute("INSERT OR IGNORE INTO accounts (name) VALUES (?)", (name,))
        conn.commit()
        st.rerun()

tab1, tab2, tab3 = st.tabs(["Ledger", "Add Item", "Manage"])

with tab1:
    st.header("Projected Ledger")
    st.info("Full transaction ledger coming soon. Add items first.")

with tab2:
    st.header("Add New Item")
    itype = st.selectbox("Type", ["Bill", "Income", "Credit Card"])
    
    with st.form("add"):
        name = st.text_input("Name*")
        amount = st.number_input("Amount*", value=0.0)
        freq = st.selectbox("Frequency", ["monthly", "bi_weekly", "every_4_weeks", "quarterly"])
        start = st.date_input("Start Date")
        paid_via = st.text_input("Paid Via")
        category = st.text_input("Category")
        notes = st.text_area("Notes")
        
        if itype == "Credit Card":
            st.subheader("Credit Card Details")
            statement_date = st.text_input("Statement Date")
            payment_date = st.text_input("Payment Date")
            auth_users = st.text_input("Authorized Users")
            balance = st.number_input("Current Balance")
            interest = st.number_input("Interest Rate", value=0.0)
            promo = st.text_input("Promo Expiration")
            mppo = st.text_input("MPPO Final Payoff")
            bt = st.checkbox("Balance Transfer Active")
            rewards = st.text_input("Rewards")
        
        if st.form_submit_button("Save"):
            c = conn.cursor()
            c.execute("INSERT INTO items (type, name, amount, frequency, start_date, paid_via, category, notes) VALUES (?,?,?,?,?,?,?,?)",
                      (itype, name, amount, freq, start.strftime("%Y-%m-%d"), paid_via, category, notes))
            item_id = c.lastrowid
            if itype == "Credit Card":
                c.execute("INSERT INTO cc_details (item_id, statement_date, payment_date, authorized_users, balance, interest_rate, promo_expiration, mppo_date, bt_active, rewards) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (item_id, statement_date, payment_date, auth_users, balance, interest, promo, mppo, int(bt), rewards))
            conn.commit()
            st.success("Saved!")
            st.rerun()

with tab3:
    st.header("Manage Items")
    items = pd.read_sql("SELECT * FROM items", conn)
    st.dataframe(items)
    st.info("Edit/delete coming in next update.")

st.success("Detailed CC form added. Try adding a Credit Card.")
conn.close()
