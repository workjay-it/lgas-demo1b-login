import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="KWS | Dense Logistics Portal", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    [data-testid="stMetric"] { background-color: #1e2129; padding: 20px; border-radius: 10px; border: 1px solid #31333f; }
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; background-color: #007bff; color: white; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])

supabase = init_connection()

@st.cache_data(ttl=60)
def load_cylinders():
    res = supabase.table("cylinders").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        # Crucial: Fix the Date types to avoid TypeErrors
        for col in ["Next_Test_Due", "Last_Test_Date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    return df

def load_batches():
    res = supabase.table("batches").select("*").execute()
    return pd.DataFrame(res.data)

# --- 3. NAVIGATION ---
st.sidebar.title("KWS Logistics Hub")
menu = ["Dashboard", "Bulk Processing (Workers)", "Financial & Billing", "Truck Intake", "Search Unit"]
choice = st.sidebar.radio("Navigation", menu)

# Global Data Load
df = load_cylinders()

# --- PAGE: DASHBOARD ---
if choice == "Dashboard":
    st.header("Fleet Intelligence & Batch Analytics")
    
    if df.empty:
        st.warning("No data found. Please import your 10-batch CSV to Supabase.")
    else:
        # 1. BATCH SUMMARY TABLE (The New Primary View)
        st.subheader("Batch Performance Overview")
        
        # Calculate stats for every batch automatically
        batch_summary = df.groupby("Batch_ID").agg(
            Total_Units=("Cylinder_ID", "count"),
            Full=("Status", lambda x: (x == "Full").sum()),
            Damaged=("Status", lambda x: (x == "Damaged").sum()),
            Empty_Pending=("Status", lambda x: (x == "Empty").sum())
        ).reset_index()
        
        st.dataframe(batch_summary, use_container_width=True, hide_index=True)

        st.markdown("---")

        # 2. DRILL-DOWN SECTION
        st.subheader("Detailed Inspection")
        
        # Toggle to show/hide the big list
        show_details = st.toggle("Show Individual Cylinder Details", value=False)
        
        if show_details:
            # Dropdown to pick which batch to inspect
            unique_batches = ["All Units"] + sorted(df["Batch_ID"].dropna().unique().tolist())
            selected_batch = st.selectbox("Select Batch to Inspect", unique_batches)
            
            display_df = df if selected_batch == "All Units" else df[df["Batch_ID"] == selected_batch]
            
            # Show Metrics for just this selection
            c1, c2, c3 = st.columns(3)
            c1.metric("Selected Units", len(display_df))
            c2.metric("Damaged in Selection", len(display_df[display_df["Status"] == "Damaged"]))
            c3.metric("Available Full", len(display_df[display_df["Status"] == "Full"]))
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("Toggle 'Show Individual Cylinder Details' above to see specific serial numbers and test dates.")

        # 3. SAFETY ALERTS (Only shows if there is a crisis)
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        alerts = df[df["Next_Test_Due"] <= next_week]
        
        if not alerts.empty:
            st.markdown("---")
            st.error(f"Compliance Alert: {len(alerts)} Units requiring immediate re-testing.")
            with st.expander("View Expired/Due Units"):
                st.dataframe(alerts[["Cylinder_ID", "Batch_ID", "Next_Test_Due", "Status"]], use_container_width=True)

# --- PAGE: BULK PROCESSING ---
elif choice == "Bulk Processing (Workers)":
    st.header("Production Line Triage")
    batches_df = load_batches()
    
    if batches_df.empty:
        st.warning("Register a Batch in 'Truck Intake' first.")
    else:
        selected_b = st.selectbox("Select Batch to Work On", batches_df["batch_id"].tolist())
        batch_cyls = df[df["Batch_ID"] == selected_b].copy()
        
        if batch_cyls.empty:
            st.info("No cylinders linked to this batch yet.")
        else:
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
                hide_index=True, use_container_width=True, key="worker_editor"
            )

            if st.button("Submit Production Data"):
                for _, row in edited_df.iterrows():
                    supabase.table("cylinders").update({
                        "Status": row["Status"],
                        "Condition_Notes": row["Condition_Notes"],
                        "Last_Test_Date": str(datetime.now().date())
                    }).eq("Cylinder_ID", row["Cylinder_ID"]).execute()
                st.success("Cloud Updated Successfully!")
                st.cache_data.clear()

# --- PAGE: FINANCIAL & BILLING ---
elif choice == "Financial & Billing":
    st.header("Batch Billing & Cost Analysis")
    RATE_CARD = {
        "Good / No Repair": 0, "Valve Leak (Minor)": 150, "Valve Replacement": 450,
        "Body Dent Repair": 300, "Re-painting Required": 200, "Foot Ring Straightening": 250, "Condemned": 0
    }
    
    if not df.empty:
        target_b = st.selectbox("Select Batch for Billing", df["Batch_ID"].unique())
        batch_data = df[df["Batch_ID"] == target_b].copy()
        batch_data["Cost"] = batch_data["Condition_Notes"].map(RATE_CARD).fillna(0)
        
        c1, c2 = st.columns(2)
        c1.metric("Batch Total Units", len(batch_data))
        c2.metric("Total Repair Bill", f"₹{batch_data['Cost'].sum():,.2f}")
        
        st.dataframe(batch_data[batch_data["Cost"] > 0][["Cylinder_ID", "Condition_Notes", "Cost"]], use_container_width=True)

# --- PAGE: TRUCK INTAKE (Enhanced) ---
elif choice == "Truck Intake":
    st.header("New Batch Registration")
    st.info("Use this form to log a new truck arrival before processing cylinders.")
    
    with st.form("new_batch", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            b_id = st.text_input("Batch ID (e.g., BATCH011)")
            truck = st.text_input("Truck Plate Number")
            
        with col2:
            driver = st.text_input("Driver Name")
            # Automatically defaults to current time
            arrival_dt = st.datetime_input("Arrival Date & Time", value=datetime.now())
        
        submit_batch = st.form_submit_button("Register Arrival")
        
        if submit_batch:
            if b_id and truck:
                try:
                    supabase.table("batches").insert({
                        "batch_id": b_id, 
                        "truck_number": truck, 
                        "driver_name": driver,
                        "arrival_time": str(arrival_dt) # New Field
                    }).execute()
                    st.success(f"✅ Batch {b_id} registered. You can now process units in 'Bulk Processing'.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter at least a Batch ID and Truck Plate.")
                
# --- PAGE: SEARCH ---
elif choice == "Search Unit":
    sid = st.text_input("Search ID").upper()
    if sid:
        res = df[df["Cylinder_ID"] == sid]
        st.table(res)




















































