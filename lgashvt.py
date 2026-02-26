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
    st.header("📊 Fleet Intelligence & Batch Analytics")
    
    # 1. Fetch Fresh Data from both tables
    @st.cache_data(ttl=600) # Optional: Cache for 10 mins, cleared by intake
    def get_combined_data():
        b_res = supabase.table("batches").select("*").execute()
        c_res = supabase.table("cylinders").select("*").execute()
        
        b_df = pd.DataFrame(b_res.data)
        c_df = pd.DataFrame(c_res.data)
        
        # Merge: Keep all batches, attach cylinders where they exist
        # This ensures new batches with 0 cylinders appear in the list
        return pd.merge(b_df, c_df, left_on="batch_id", right_on="Batch_ID", how="left")

    full_df = get_combined_data()

    if full_df.empty:
        st.warning("No batch or cylinder data found.")
    else:
        # 2. Top Level Company Filter
        all_companies = ["All Companies"] + sorted([c for c in full_df["company"].dropna().unique()])
        target_company = st.selectbox("🏢 Select Company to View", all_companies)
        
        # Apply filter
        display_df = full_df if target_company == "All Companies" else full_df[full_df["company"] == target_company]

        # 3. High-Level Metrics
        # We count unique Batch IDs from the batches table side to see all trucks
        total_trucks = display_df["batch_id"].nunique()
        total_cylinders = display_df["Cylinder_ID"].count() # Doesn't count NaNs
        damaged_count = (display_df["Status"] == "Damaged").sum()

        m1, m2, m3 = st.columns(3)
        m1.metric("Trucks in Yard", total_trucks)
        m2.metric("Total Cylinders", total_cylinders)
        m3.metric("Damaged Found", damaged_count)

        st.markdown("---")

        # 4. Batch Performance Overview
        st.subheader(f"Batch Performance: {target_company}")
        
        # We group by batch details to see the status of each truckload
        summary = display_df.groupby(["batch_id", "company", "truck_number"]).agg(
            Total_Units=("Cylinder_ID", "count"),
            Ready=("Status", lambda x: (x == "Full").sum()),
            Damaged=("Status", lambda x: (x == "Damaged").sum()),
            Empty=("Status", lambda x: (x == "Empty").sum())
        ).reset_index()

        # Add a helpful status label for empty batches
        summary["Load_Status"] = summary["Total_Units"].apply(lambda x: "📦 Waiting for Unload" if x == 0 else "⚙️ In Progress")
        
        st.dataframe(summary, use_container_width=True, hide_index=True)

        # 5. Detailed Inspection (Toggle)
        with st.expander("🔍 Drill Down: Individual Cylinder Details"):
            batch_list = ["All Batches"] + sorted(display_df["batch_id"].unique().tolist())
            selected_b = st.selectbox("Filter details by Batch ID", batch_list)
            
            detail_view = display_df if selected_b == "All Batches" else display_df[display_df["batch_id"] == selected_b]
            
            # Drop the redundant Batch_ID column from the merge before displaying
            st.dataframe(detail_view.drop(columns=["Batch_ID"], errors="ignore"), use_container_width=True, hide_index=True)

        # 6. Safety Compliance (Across entire fleet)
        full_df["Next_Test_Due"] = pd.to_datetime(full_df["Next_Test_Due"], errors='coerce')
        today = datetime.now()
        alerts = full_df[full_df["Next_Test_Due"] <= (today + timedelta(days=7))]
        
        if not alerts.empty:
            st.error(f"🚨 Compliance Alert: {len(alerts)} units are overdue or expire within 7 days.")
            if st.button("View Compliance List"):
                st.write(alerts[["Cylinder_ID", "batch_id", "company", "Next_Test_Due"]])

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
                    
                    # 1. Clear cache to force fresh data fetch
                    st.cache_data.clear()
                    
                    # 2. Success message (Balloons removed)
                    st.success(f"✅ Batch {clean_batch_id} registered successfully.")
                    
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Please enter a Batch ID.")
            
# --- PAGE: SEARCH ---
elif choice == "Search Unit":
    sid = st.text_input("Search ID").upper()
    if sid:
        res = df[df["Cylinder_ID"] == sid]
        st.table(res)
































































