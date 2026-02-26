import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="Indsutrial Gas Management System", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] { background-color: #1e2129; padding: 20px; border-radius: 10px; border: 1px solid #31333f; }
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #007bff; color: white; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Connection
@st.cache_resource
def init_connection():
    return create_client(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])

supabase = init_connection()

# Data Loaders
def load_cylinders():
    res = supabase.table("cylinders").select("*").execute()
    return pd.DataFrame(res.data)

def load_batches():
    res = supabase.table("batches").select("*").execute()
    return pd.DataFrame(res.data)

# --- 3. MAIN INTERFACE ---
if "authenticated" not in st.session_state: st.session_state["authenticated"] = True # Simplified for setup

st.sidebar.markdown("### KWS Dense Logistics")
menu = ["Dashboard", "Truck Intake (New Batch)", "Bulk Processing", "Inventory Search"]
choice = st.sidebar.radio("Navigation", menu)

# --- PAGE: DASHBOARD ---
if choice == "Dashboard":
        st.header("Real-Time Fleet Intelligence")
        
        # 1. Fetch Data
        df = load_cylinders()
        
        if df.empty:
            st.info("The inventory is currently empty. Please import your 10-batch CSV into Supabase.")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Units", 0)
            m2.metric("Full", 0)
            m3.metric("Damaged", 0)
            m4.metric("Empty", 0)
        else:
            # 2. DATA CLEANING (Crucial to fix the TypeError)
            # Convert columns to datetime then to date objects for comparison
            for col in ["Next_Test_Due", "Last_Test_Date"]:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

            # Ensure 'Overdue' is treated as a boolean
            if "Overdue" in df.columns:
                df["Overdue"] = df["Overdue"].fillna(False).astype(bool)

            # 3. SECURITY & BATCH FILTERING
            # Filter by client link (if not admin)
            display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
            
            # Batch Selector Dropdown
            if "Batch_ID" in display_df.columns:
                unique_batches = display_df["Batch_ID"].dropna().unique().tolist()
                batch_options = ["All Active Batches"] + sorted([str(b) for b in unique_batches])
                
                selected_batch = st.selectbox("Filter Dashboard by Shipment/Batch", batch_options)
                
                if selected_batch != "All Active Batches":
                    display_df = display_df[display_df["Batch_ID"] == selected_batch]

            # 4. DYNAMIC METRICS
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Units in View", len(display_df))
            m2.metric("Available (Full)", len(display_df[display_df["Status"] == "Full"]))
            m3.metric("Quarantine (Damaged)", len(display_df[display_df["Status"] == "Damaged"]))
            m4.metric("Pending Test (Empty)", len(display_df[display_df["Status"] == "Empty"]))
            
            # 5. COMPLIANCE ALERTS (This logic is now safe from TypeErrors)
            st.markdown("---")
            st.subheader("Compliance & Safety Alerts")
            
            today = datetime.now().date()
            next_week = today + timedelta(days=7)
            
            # Filter for cylinders due within 7 days or already overdue
            alerts = display_df[
                (display_df["Next_Test_Due"] <= next_week) | 
                (display_df["Overdue"] == True)
            ]
            
            if not alerts.empty:
                st.warning(f"ACTION REQUIRED: {len(alerts)} units require inspection or testing.")
                st.dataframe(alerts, use_container_width=True, hide_index=True)
            else:
                st.success("SAFETY CHECK: All cylinders in this view are currently compliant.")

            # 6. INVENTORY DATA TABLE
            st.markdown("---")
            st.subheader("Inventory Details")
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    
# --- PAGE: TRUCK INTAKE ---
elif choice == "Truck Intake (New Batch)":
    st.header("Log Incoming Shipment")
    with st.form("truck_form"):
        col1, col2 = st.columns(2)
        with col1:
            b_id = st.text_input("New Batch ID (Unique)", placeholder="e.g., TRK-101")
            truck = st.text_input("Truck Plate Number")
        with col2:
            driver = st.text_input("Driver Name")
            company = st.text_input("Originating Gas Company")
        
        notes = st.text_area("Delivery Notes")
        
        if st.form_submit_button("Register Truck Arrival"):
            if b_id:
                supabase.table("batches").insert({
                    "batch_id": b_id, "truck_number": truck, 
                    "driver_name": driver, "origin_company": company, "delivery_notes": notes
                }).execute()
                st.success(f"Truckload {b_id} registered. You can now link cylinders to this ID.")
            else: st.error("Batch ID is required.")

# --- PAGE: BULK PROCESSING (Worker View) ---
elif choice == "Bulk Processing":
    st.header("Production Line Triage")
    batches_df = load_batches()
    
    if batches_df.empty:
        st.warning("No active batches found.")
    else:
        selected_b = st.selectbox("Select Batch to Process", batches_df["batch_id"].tolist())
        all_cyls = load_cylinders()
        batch_cyls = all_cyls[all_cyls["Batch_ID"] == selected_b].copy()
        
        if not batch_cyls.empty:
            st.subheader(f"Technical Checklist: {selected_b}")
            
            edited_df = st.data_editor(
                batch_cyls[["Cylinder_ID", "Status", "Condition_Notes"]],
                column_config={
                    "Status": st.column_config.SelectboxColumn("Result", options=["Full", "Damaged", "Under Maintenance"]),
                    "Condition_Notes": st.column_config.SelectboxColumn("Damage Type", options=[
                        "Good / No Repair", "Valve Leak (Minor)", "Valve Replacement", 
                        "Body Dent Repair", "Re-painting Required", "Foot Ring Straightening", "Condemned"
                    ]),
                    "Cylinder_ID": st.column_config.TextColumn("Cylinder ID", disabled=True),
                },
                hide_index=True, use_container_width=True, key="worker_triage"
            )

            if st.button("Submit Production Data"):
                for index, row in edited_df.iterrows():
                    supabase.table("cylinders").update({
                        "Status": row["Status"],
                        "Condition_Notes": row["Condition_Notes"],
                        "Last_Test_Date": str(datetime.now().date())
                    }).eq("Cylinder_ID", row["Cylinder_ID"]).execute()
                st.success(f"Production data for {selected_b} synced to cloud.")
                st.cache_data.clear()

# --- PAGE: FINANCIAL & BILLING (Office View) ---
elif choice == "Financial & Billing":
    st.header("Batch Reconciliation & Financials")
    
    # Financial Configuration (Rate Card)
    RATE_CARD = {
        "Good / No Repair": 0,
        "Valve Leak (Minor)": 150,
        "Valve Replacement": 450,
        "Body Dent Repair": 300,
        "Re-painting Required": 200,
        "Foot Ring Straightening": 250,
        "Condemned": 0
    }

    df = load_cylinders()
    if not df.empty:
        unique_batches = df["Batch_ID"].dropna().unique().tolist()
        target_b = st.selectbox("Select Batch for Billing", unique_batches)
        
        batch_data = df[df["Batch_ID"] == target_b]
        
        # Financial Calculations
        batch_data["Cost"] = batch_data["Condition_Notes"].map(RATE_CARD).fillna(0)
        total_bill = batch_data["Cost"].sum()
        
        # Display Financial Dashboard
        col1, col2, col3 = st.columns(3)
        col1.metric("Batch Size", len(batch_data))
        col2.metric("Billable Repairs", len(batch_data[batch_data["Cost"] > 0]))
        col3.metric("Total Invoice Value", f"₹{total_bill:,.2f}")
        
        st.markdown("---")
        st.subheader("Line-Item Breakdown")
        
        # Show specific costs per cylinder for the client
        st.dataframe(
            batch_data[["Cylinder_ID", "Condition_Notes", "Cost"]][batch_data["Cost"] > 0],
            use_container_width=True, hide_index=True
        )
        
        if st.button("Generate Digital Receipt (CSV)"):
            csv = batch_data[["Cylinder_ID", "Condition_Notes", "Cost"]].to_csv(index=False)
            st.download_button("Download CSV for Client", csv, f"Billing_{target_b}.csv", "text/csv")
            
# --- PAGE: SEARCH ---
elif choice == "Inventory Search":
    st.header("Unit Traceability")
    sid = st.text_input("Scan any Cylinder ID").strip().upper()
    if sid:
        df = load_cylinders()
        res = df[df["Cylinder_ID"] == sid]
        if not res.empty:
            st.write("### Cylinder History")
            st.table(res.T)
            
            # Show Parent Batch Info
            batch_id = res.iloc[0]["Batch_ID"]
            b_info = load_batches()
            parent = b_info[b_info["batch_id"] == batch_id]
            if not parent.empty:
                st.write("### Transport Source")
                st.dataframe(parent, hide_index=True)
















































