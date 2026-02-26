import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="Domestic Gas Logistics Portal", layout="wide")

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
        # 1. NEW: Top Level Company Filter
        all_companies = ["All Companies"] + sorted([c for c in df["Customer_Name"].dropna().unique()])
        target_company = st.selectbox("Select Company to View", all_companies)
        
        # Apply the filter
        if target_company != "All Companies":
            filtered_df = df[df["Customer_Name"] == target_company]
        else:
            filtered_df = df

        # 2. HIGH-LEVEL METRICS
        c1, c2, c3 = st.columns(3)
        c1.metric(f"Total Units ({target_company})", len(filtered_df))
        c2.metric("Damaged Units", len(filtered_df[filtered_df["Status"] == "Damaged"]))
        c3.metric("Ready to Dispatch", len(filtered_df[filtered_df["Status"] == "Full"]))

        st.markdown("---")

        # 3. BATCH PERFORMANCE OVERVIEW (The Table you liked)
        st.subheader(f"Batch Performance Overview: {target_company}")
        
        batch_summary = filtered_df.groupby("Batch_ID").agg(
            Total_Units=("Cylinder_ID", "count"),
            Full=("Status", lambda x: (x == "Full").sum()),
            Damaged=("Status", lambda x: (x == "Damaged").sum()),
            Empty_Pending=("Status", lambda x: (x == "Empty").sum())
        ).reset_index()
        
        st.dataframe(batch_summary, use_container_width=True, hide_index=True)

        # 4. THE TOGGLE (Drill-Down Section)
        st.subheader("Detailed Inspection")
        show_details = st.toggle("Show Individual Cylinder Details", value=False)
        
        if show_details:
            # Filters the drill-down to only the batches belonging to the selected company
            unique_batches = ["All Active Batches"] + sorted(filtered_df["Batch_ID"].unique().tolist())
            selected_batch = st.selectbox("Inspect Specific Batch", unique_batches)
            
            final_display = filtered_df if selected_batch == "All Active Batches" else filtered_df[filtered_df["Batch_ID"] == selected_batch]
            st.dataframe(final_display, use_container_width=True, hide_index=True)

# 5. SAFETY ALERTS (Fixed for Data Types)
        st.markdown("---")
        
        # Ensure the column is converted to datetime format first
        df["Next_Test_Due"] = pd.to_datetime(df["Next_Test_Due"], errors='coerce')
        
        today = datetime.now()
        next_week = today + timedelta(days=7)
        
        # Filter for dates that are today or in the past (Expired) 
        # OR within the next 7 days (Expiring Soon)
        alerts = df[df["Next_Test_Due"] <= next_week]
        
        if not alerts.empty:
            st.error(f"🚨 Compliance Alert: {len(alerts)} Units requiring immediate re-testing.")
            with st.expander("View Expired/Due Units"):
                # Format the date for display so it looks clean
                display_alerts = alerts[["Cylinder_ID", "Customer_Name", "Batch_ID", "Next_Test_Due"]].copy()
                display_alerts["Next_Test_Due"] = display_alerts["Next_Test_Due"].dt.strftime('%Y-%m-%d')
                st.dataframe(display_alerts, use_container_width=True, hide_index=True)
        else:
            st.success("All units are currently within test-date compliance.")

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

# --- PAGE: TRUCK INTAKE ---
elif choice == "Truck Intake":
    st.header("🚚 New Truck Arrival")
    st.info("Register incoming shipments here. All Batch IDs and Truck Plates will be auto-formatted to uppercase.")
    
    # 1. Define standard clients
    companies = ["Indane", "Bharat Gas", "HP Gas", "Industrial Solutions", "LPG Hub Hyderabad"]
    
    # 2. Registration Form
    with st.form("truck_entry", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            # User input for Batch ID
            new_batch = st.text_input("New Batch ID (e.g., BATCH017)")
            # Selection for existing company
            selected_company = st.selectbox("Company Name", companies)
            
        with col2:
            truck_no = st.text_input("Truck Plate Number")
            driver = st.text_input("Driver Name")
            
        # Optional: Manual timestamp adjustment (defaults to now)
        arrival_dt = st.datetime_input("Arrival Date & Time", value=datetime.now())
            
        if st.form_submit_button("Confirm Arrival"):
            # --- DATA CLEANING LOGIC ---
            # .strip() removes accidental spaces, .upper() makes it BATCH017
            clean_batch_id = new_batch.strip().upper()
            clean_truck_no = truck_no.strip().upper()
            clean_driver = driver.strip().title() # Capitalizes first letter of names
            
            if clean_batch_id and clean_truck_no:
                try:
                    # 3. Database Insertion
                    supabase.table("batches").insert({
                        "batch_id": clean_batch_id,
                        "company": selected_company,
                        "truck_number": clean_truck_no,
                        "driver_name": clean_driver,
                        "arrival_time": str(arrival_dt)
                    }).execute()
                    
                    # 4. CRITICAL: Clear cache so Dashboard sees the new data
                    st.cache_data.clear()
                    
                    st.success(f"✅ Success! Batch {clean_batch_id} for {selected_company} registered.")
                    st.balloons() # Visual feedback for a successful arrival
                    
                except Exception as e:
                    st.error(f"Database Error: {e}")
            else:
                st.warning("Please provide both a Batch ID and a Truck Plate Number.")

    # 5. RECENT ACTIVITY PREVIEW
    st.markdown("---")
    st.subheader("Last 5 Registered Trucks")
    try:
        recent_res = supabase.table("batches").select("*").order("created_at", desc=True).limit(5).execute()
        if recent_res.data:
            recent_df = pd.DataFrame(recent_res.data)
            # Only show relevant columns for the gate clerk
            st.table(recent_df[["batch_id", "company", "truck_number", "driver_name"]])
    except:
        st.info("Arrival log will appear here once trucks are registered.")
            
# --- PAGE: SEARCH ---
elif choice == "Search Unit":
    sid = st.text_input("Search ID").upper()
    if sid:
        res = df[df["Cylinder_ID"] == sid]
        st.table(res)





























































