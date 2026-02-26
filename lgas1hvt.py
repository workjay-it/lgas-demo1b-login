import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="KWS | LGAS Management", layout="wide")

# Professional Dark Mode Styling (Fixes "White Boxes")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] {
        background-color: #1e2129;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        border: 1px solid #31333f;
    }
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    [data-testid="stMetricLabel"] { color: #808495 !important; }
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    .stButton>button { 
        width: 100%; 
        border-radius: 5px; 
        height: 3em; 
        background-color: #007bff; 
        color: white; 
        font-weight: bold; 
        border: none;
    }
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State
for key in ["authenticated", "user_role", "client_link", "last_refresh"]:
    if key not in st.session_state:
        st.session_state[key] = False if key == "authenticated" else ("Initializing..." if key == "last_refresh" else None)

# Supabase Connection
@st.cache_resource
def init_connection():
    return create_client(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])

supabase = init_connection()

# Data Loading Logic
@st.cache_data(ttl=60)
def load_data():
    ist = pytz.timezone('Asia/Kolkata')
    st.session_state["last_refresh"] = datetime.now(ist).strftime("%I:%M:%S %p")
    res = supabase.table("cylinders").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        for col in ["Last_Test_Date", "Next_Test_Due"]:
            if col in df.columns: df[col] = pd.to_datetime(df[col]).dt.date
    return df

# Secure Login
def login():
    st.markdown("<h1 style='text-align: center;'>KWS Industrial Portal</h1>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("### Secure Access")
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")
        if st.button("Sign In"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                profile = supabase.table("profiles").select("role, client_link").eq("id", res.user.id).single().execute()
                st.session_state.update({"authenticated": True, "user_role": profile.data["role"], "client_link": profile.data["client_link"]})
                st.rerun()
            except: st.error("Login Failed. Check credentials.")

if not st.session_state["authenticated"]:
    login()
else:
    # Sidebar
    st.sidebar.markdown(f"### KWS Logistics")
    st.sidebar.markdown(f"**User Role:** `{st.session_state['user_role'].upper()}`")
    
    menu = ["Dashboard", "Cylinder Finder"]
    if st.session_state["user_role"] == "admin":
        menu += ["Bulk Operations", "Return Audit Log"]
    choice = st.sidebar.radio("Main Menu", menu)
    
    if st.sidebar.button("Sign Out"):
        st.session_state["authenticated"] = False
        st.rerun()

    df = load_data()

    # --- PAGE: DASHBOARD ---
    if choice == "Dashboard":
        st.header("Cylinder Fleet Overview")
        
        # 1. Data Isolation & Batch Filtering
        display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
        
        if not display_df.empty:
            available_batches = ["All Active Batches"] + sorted(display_df["Batch_ID"].unique().astype(str).tolist())
            selected_batch = st.selectbox("Select Batch to Inspect", available_batches)
            
            if selected_batch != "All Active Batches":
                display_df = display_df[display_df["Batch_ID"] == selected_batch]

        # 2. Dynamic Metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Units in View", len(display_df))
        m2.metric("Status: Full", len(display_df[display_df["Status"] == "Full"]) if not display_df.empty else 0)
        m3.metric("Status: Damaged", len(display_df[display_df["Status"] == "Damaged"]) if not display_df.empty else 0)
        m4.metric("Status: Empty", len(display_df[display_df["Status"] == "Empty"]) if not display_df.empty else 0)
        
        # 3. Critical Alerts
        st.markdown("---")
        st.subheader("Critical Testing Alerts")
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        if not display_df.empty:
            alerts = display_df[(display_df["Next_Test_Due"] <= next_week) | (display_df["Overdue"] == True)]
            if not alerts.empty: 
                st.warning(f"Action Required: {len(alerts)} cylinders in this view require immediate testing.")
                st.dataframe(alerts, use_container_width=True, hide_index=True)
            else: 
                st.success("Compliance Check: All cylinders in this view are within their testing window.")
        
        # 4. Full Table
        st.markdown("---")
        st.subheader("Inventory Details")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- PAGE: CYLINDER FINDER ---
    elif choice == "Cylinder Finder":
        st.header("Search Individual Unit")
        search_id = st.text_input("Scan or Enter Cylinder ID").strip().upper()
        if search_id:
            res = df[df["Cylinder_ID"] == search_id]
            if not res.empty:
                st.success(f"Record identified for {search_id}")
                st.table(res.T)
            else: st.error("ID not found in master database.")

    # --- PAGE: BULK OPERATIONS ---
    elif choice == "Bulk Operations":
        st.header("Bulk Processing & Triage")
        
        # Triage Tool (For partial batch processing)
        st.subheader("Batch Triage (Process Truckloads)")
        with st.form("triage_form"):
            parent_batch = st.text_input("Target Batch ID (e.g., BATCH001)")
            scanned_subset = st.text_area("Scan the processed subset of IDs")
            col1, col2 = st.columns(2)
            with col1:
                outcome = st.selectbox("Assign Outcome", ["Passed/Full", "Damaged/Quarantine", "Maintenance Required"])
            with col2:
                action_date = st.date_input("Processing Date")
            
            if st.form_submit_button("Submit Results"):
                id_list = [i.strip().upper() for i in scanned_subset.replace(",", "\n").split("\n") if i.strip()]
                if id_list:
                    status_map = {"Passed/Full": "Full", "Damaged/Quarantine": "Damaged", "Maintenance Required": "Under Maintenance"}
                    supabase.table("cylinders").update({
                        "Status": status_map[outcome],
                        "Batch_ID": parent_batch,
                        "Condition_Notes": f"Triage Result: {outcome}",
                        "Last_Test_Date": str(action_date)
                    }).in_("Cylinder_ID", id_list).execute()
                    st.success(f"Yield Updated: {len(id_list)} units logged to {parent_batch}")
                    st.cache_data.clear()

        st.markdown("---")
        
        # Batch Reconciliation Report
        st.subheader("Batch Reconciliation Report (Shipment Performance)")
        if not df.empty and "Batch_ID" in df.columns:
            batch_df = df[df["Batch_ID"].notna() & (df["Batch_ID"] != "")]
            if not batch_df.empty:
                report = batch_df.groupby("Batch_ID").agg(
                    Total_Units=("Cylinder_ID", "count"),
                    Ready_Full=("Status", lambda x: (x == "Full").sum()),
                    Damaged_Units=("Status", lambda x: (x == "Damaged").sum()),
                    Still_Pending=("Status", lambda x: (x == "Empty").sum())
                ).reset_index()
                report["Pass_Rate_Percent"] = ((report["Ready_Full"] / report["Total_Units"]) * 100).round(1)
                st.dataframe(report, use_container_width=True, hide_index=True)

    # --- PAGE: RETURN AUDIT ---
    elif choice == "Return Audit Log":
        st.header("Gatekeeping Audit")
        scan_id = st.text_input("Scan ID upon arrival").strip().upper()
        if scan_id:
            with st.form("audit_form"):
                cond = st.selectbox("Arrival Physical Condition", ["Good", "Dented", "Leaking Valve", "Corroded"])
                notes = st.text_area("Observation Notes")
                if st.form_submit_button("Confirm Log-In"):
                    supabase.table("cylinders").update({
                        "Status": "Empty", 
                        "Condition_Notes": f"Arrival Audit: {cond} - {notes}"
                    }).eq("Cylinder_ID", scan_id).execute()
                    st.success(f"Cylinder {scan_id} checked into system as Empty.")
                    st.cache_data.clear()

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(f"<div style='text-align: center; color: gray;'>KWS LGAS Management | System Refreshed: {st.session_state['last_refresh']}</div>", unsafe_allow_html=True)




































