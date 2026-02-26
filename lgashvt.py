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
        
        # 1. Load Data
        df = load_cylinders()
        
        if df.empty:
            st.info("The inventory is currently empty. Please import your 10-batch CSV into Supabase.")
            # Default empty metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Units", 0)
            m2.metric("Full", 0)
            m3.metric("Damaged", 0)
            m4.metric("Empty", 0)
        else:
            # 2. Batch Selector Logic
            # We filter based on your Customer_Name (Security) and then by Batch
            display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
            
            # Check if Batch_ID column exists to build the dropdown
            if "Batch_ID" in display_df.columns:
                unique_batches = display_df["Batch_ID"].dropna().unique().tolist()
                batch_options = ["All Active Batches"] + sorted([str(b) for b in unique_batches])
                
                selected_batch = st.selectbox("Filter Dashboard by Shipment/Batch", batch_options)
                
                if selected_batch != "All Active Batches":
                    display_df = display_df[display_df["Batch_ID"] == selected_batch]

            # 3. Dynamic Metrics (Updates based on the dropdown above)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Units in View", len(display_df))
            m2.metric("Available (Full)", len(display_df[display_df["Status"] == "Full"]))
            m3.metric("Quarantine (Damaged)", len(display_df[display_df["Status"] == "Damaged"]))
            m4.metric("Pending Test (Empty)", len(display_df[display_df["Status"] == "Empty"]))
            
            # 4. Critical Compliance Alerts
            st.markdown("---")
            st.subheader("Compliance Alerts")
            today = datetime.now().date()
            next_week = today + timedelta(days=7)
            
            alerts = display_df[(display_df["Next_Test_Due"] <= next_week) | (display_df["Overdue"] == True)]
            
            if not alerts.empty:
                st.warning(f"Found {len(alerts)} cylinders requiring immediate testing/inspection.")
                st.dataframe(alerts, use_container_width=True, hide_index=True)
            else:
                st.success("All cylinders in this view are currently compliant.")

            # 5. Full Data View
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

# --- PAGE: BULK PROCESSING ---
elif choice == "Bulk Processing":
    st.header("Production Line Triage")
    batches_df = load_batches()
    
    if batches_df.empty:
        st.warning("No active batches found. Please register a Truck Intake first.")
    else:
        with st.form("triage_form"):
            selected_b = st.selectbox("Select Batch to Process", batches_df["batch_id"].tolist())
            scanned_ids = st.text_area("Scan IDs (Hardware scanner dump)")
            new_status = st.selectbox("Assign Result", ["Full", "Damaged", "Under Maintenance"])
            
            if st.form_submit_button("Update Production Status"):
                id_list = [i.strip().upper() for i in scanned_ids.replace(",", "\n").split("\n") if i.strip()]
                if id_list:
                    supabase.table("cylinders").update({
                        "Status": new_status,
                        "Batch_ID": selected_b,
                        "Last_Test_Date": str(datetime.now().date())
                    }).in_("Cylinder_ID", id_list).execute()
                    st.success(f"Batch {selected_b} updated with {len(id_list)} units.")

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









































