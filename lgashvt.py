import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
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
        # Standardize naming immediately upon load
        if "Batch_ID" in df.columns:
            df = df.rename(columns={"Batch_ID": "batch_id"})
            
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

    # 1. DATA FETCHING & UNIFICATION
    @st.cache_data(ttl=300)
    def get_unified_data():
        # Fetch fresh rows from Supabase
        b_res = supabase.table("batches").select("*").execute()
        c_res = supabase.table("cylinders").select("*").execute()
        
        b_df = pd.DataFrame(b_res.data)
        c_df = pd.DataFrame(c_res.data)
        
        # Safety check: If either table is missing, we can't show a summary
        if b_df.empty:
            return pd.DataFrame()

        # --- THE BULLETPROOF FIX ---
        # 1. Standardize cylinder column name
        if "Batch_ID" in c_df.columns:
            c_df = c_df.rename(columns={"Batch_ID": "batch_id"})
            
        # 2. STRIP & CONVERT: Remove any invisible characters and force string type
        b_df["batch_id"] = b_df["batch_id"].astype(str).str.strip().str.upper()
        
        if not c_df.empty:
            c_df["batch_id"] = c_df["batch_id"].astype(str).str.strip().str.upper()
        else:
            # Create an empty cylinder ID column so the merge doesn't fail
            c_df = pd.DataFrame(columns=["batch_id", "Cylinder_ID", "Status", "Next_Test_Due"])

        # 3. MERGE: 'left' join ensures we see the truck even if cylinders aren't found
        merged = pd.merge(b_df, c_df, on="batch_id", how="left")
        
        # 4. FIX DATES for the Alert logic
        if "Next_Test_Due" in merged.columns:
            merged["Next_Test_Due"] = pd.to_datetime(merged["Next_Test_Due"], errors='coerce')
            
        return merged

    full_df = get_unified_data()

    if full_df.empty:
        st.warning("No batches found. Check your 'Truck Intake' or Supabase 'batches' table.")
    else:
        # 2. TOP LEVEL FILTER
        all_companies = ["All Companies"] + sorted([str(c) for c in full_df["company"].unique() if c])
        target_company = st.selectbox("Select Company to View", all_companies)
        
        display_df = full_df if target_company == "All Companies" else full_df[full_df["company"] == target_company]

        # 3. HIGH-LEVEL METRICS
        m1, m2, m3 = st.columns(3)
        m1.metric("Trucks in Yard", display_df["batch_id"].nunique())
        # Use Cylinder_ID to count actual units, excluding empty join rows
        m2.metric("Total Cylinders", display_df["Cylinder_ID"].count())
        m3.metric("Damaged Found", (display_df["Status"] == "Damaged").sum())

        st.markdown("---")

        # 4. BATCH PERFORMANCE OVERVIEW
        st.subheader(f"Batch Performance: {target_company}")
        
        # We group by these 3 columns to build the summary table
        summary = display_df.groupby(["batch_id", "company", "truck_number"]).agg(
            Total_Units=("Cylinder_ID", "count"),
            Ready=("Status", lambda x: (x == "Full").sum()),
            Damaged=("Status", lambda x: (x == "Damaged").sum()),
            Empty=("Status", lambda x: (x == "Empty").sum())
        ).reset_index()

        summary["Load_Status"] = summary["Total_Units"].apply(
            lambda x: "📦 Waiting for Unload" if x == 0 else "⚙️ In Progress"
        )
        
        st.dataframe(summary, use_container_width=True, hide_index=True)

        # 5. DETAILED DRILL-DOWN
        with st.expander("Individual Cylinder Details"):
            # Hide the empty join rows (trucks with no cylinders) in this view
            detail_view = display_df.dropna(subset=["Cylinder_ID"])
            if not detail_view.empty:
                st.dataframe(detail_view, use_container_width=True, hide_index=True)
            else:
                st.info("No individual cylinder records found.")

        # 6. SAFETY COMPLIANCE ALERTS
        st.markdown("---")
        today = datetime.now()
        # Filter for cylinders needing re-test in the next 7 days
        alerts = full_df[full_df["Next_Test_Due"] <= (today + timedelta(days=7))].dropna(subset=["Cylinder_ID"])
        
        if not alerts.empty:
            st.error(f"🚨 Compliance Alert: {len(alerts)} units require re-testing.")
            with st.expander("View Expired/Due Units"):
                alert_table = alerts[["Cylinder_ID", "batch_id", "Next_Test_Due"]].copy()
                alert_table["Next_Test_Due"] = alert_table["Next_Test_Due"].dt.date
                st.table(alert_table)
    
# --- PAGE: BULK PROCESSING ---
elif choice == "Bulk Processing (Workers)":
    st.header("Production Line Triage")
    batches_df = load_batches()
    
    if batches_df.empty:
        st.warning("Register a Batch in 'Truck Intake' first.")
    else:
        selected_b = st.selectbox("Select Batch to Work On", batches_df["batch_id"].tolist())
        # FIXED: Changed 'Batch_ID' to 'batch_id'
        batch_cyls = df[df["batch_id"] == selected_b].copy()
        
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
                st.rerun()

# --- PAGE: FINANCIAL & BILLING ---
elif choice == "Financial & Billing":
    st.header("Batch Billing & Cost Analysis")
    RATE_CARD = {
        "Good / No Repair": 0, "Valve Leak (Minor)": 150, "Valve Replacement": 450,
        "Body Dent Repair": 300, "Re-painting Required": 200, "Foot Ring Straightening": 250, "Condemned": 0
    }
    
    if not df.empty:
        # FIXED: Changed 'Batch_ID' to 'batch_id'
        target_b = st.selectbox("Select Batch for Billing", df["batch_id"].unique())
        batch_data = df[df["batch_id"] == target_b].copy()
        batch_data["Cost"] = batch_data["Condition_Notes"].map(RATE_CARD).fillna(0)
        
        c1, c2 = st.columns(2)
        c1.metric("Batch Total Units", len(batch_data))
        c2.metric("Total Repair Bill", f"₹{batch_data['Cost'].sum():,.2f}")
        
        st.dataframe(batch_data[batch_data["Cost"] > 0][["Cylinder_ID", "Condition_Notes", "Cost"]], use_container_width=True, hide_index=True)

# --- PAGE: TRUCK INTAKE ---
elif choice == "Truck Intake":
    st.header("New Truck Arrival")
    companies = ["Indane", "Bharat Gas", "HP Gas", "Industrial Solutions", "LPG Hub Hyderabad"]
    
    with st.form("truck_entry", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_batch = st.text_input("New Batch ID (e.g., BATCH017)")
            selected_company = st.selectbox("Company Name", companies)
        with col2:
            truck_no = st.text_input("Truck Plate Number")
            driver = st.text_input("Driver Name")
            
        if st.form_submit_button("Confirm Arrival"):
            clean_batch_id = new_batch.strip().upper()
            if clean_batch_id:
                try:
                    supabase.table("batches").insert({
                        "batch_id": clean_batch_id,
                        "company": selected_company,
                        "truck_number": truck_no.strip().upper(),
                        "driver_name": driver.strip().title(),
                        "arrival_time": str(datetime.now())
                    }).execute()
                    st.cache_data.clear()
                    st.success(f"Batch {clean_batch_id} registered successfully.")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a Batch ID.")

# --- PAGE: SEARCH ---
elif choice == "Search Unit":
    st.header("🔍 Search Cylinder")
    sid = st.text_input("Enter Cylinder ID").upper()
    if sid:
        res = df[df["Cylinder_ID"] == sid]
        if not res.empty:
            st.table(res)
        else:
            st.info("No cylinder found with that ID.")










































































