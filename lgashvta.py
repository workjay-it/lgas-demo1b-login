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

# --- 1.5 LOGIN & ACCESS CONTROL ---
if 'role' not in st.session_state:
    st.session_state.role = None

def login():
    with st.container():
        st.subheader("🔑 Gas Logistics Portal Login")
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            # Credentials for different roles
            if user == "admin" and pwd == "admin123":
                st.session_state.role = "Admin"
            elif user == "gasco" and pwd == "gas2026":
                st.session_state.role = "Gas Company"
            elif user == "testco" and pwd == "test99":
                st.session_state.role = "Test Center"
            else:
                st.error("Invalid credentials")
            st.rerun()

if st.session_state.role is None:
    login()
    st.stop() # Prevents data loading until login

# --- 2. DATABASE CONNECTION & GLOBAL DATA ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])

supabase = init_connection()

@st.cache_data(ttl=300)
def get_unified_data():
    try:
        b_res = supabase.table("batches").select("*").execute()
        c_res = supabase.table("cylinders").select("*").execute()
        b_df = pd.DataFrame(b_res.data)
        c_df = pd.DataFrame(c_res.data)
        
        if b_df.empty: return pd.DataFrame()

        if "Batch_ID" in c_df.columns:
            c_df = c_df.rename(columns={"Batch_ID": "batch_id"})
        
        b_df["batch_id"] = b_df["batch_id"].astype(str).str.strip().str.upper()
        if not c_df.empty:
            c_df["batch_id"] = c_df["batch_id"].astype(str).str.strip().str.upper()
            
        return pd.merge(b_df, c_df, on="batch_id", how="left")
    except Exception as e:
        st.error(f"Database sync error: {e}")
        return pd.DataFrame()

full_df = get_unified_data()

# --- 3. DYNAMIC NAVIGATION ---
st.sidebar.title(f"👤 {st.session_state.role}")

# Default menu to prevent NameError
menu = ["Dashboard", "Search Unit"] 

if st.session_state.role == "Admin":
    full_menu = ["Dashboard", "Bulk Processing (Workers)", "Financial & Billing", "Truck Intake", "Search Unit", "Gas Co Upload"]
    st.sidebar.markdown("---")
    st.sidebar.subheader("🛠️ Admin Controls")
    dev_mode = st.sidebar.toggle("Developer Mode", value=True)
    menu = full_menu if dev_mode else ["Dashboard", "Search Unit"]

elif st.session_state.role == "Gas Company":
    menu = ["Dashboard", "Gas Co Upload", "Search Unit"]

elif st.session_state.role == "Test Center":
    menu = ["Dashboard", "Bulk Processing (Workers)", "Search Unit"]

choice = st.sidebar.radio("Navigation", menu)

if st.sidebar.button("Logout"):
    st.session_state.role = None
    st.rerun()
    
# --- PAGE: DASHBOARD ---
if choice == "Dashboard":
    st.header("Fleet Intelligence & Batch Analytics")

    if full_df.empty:
        st.warning("No data found.")
    else:
        # 1. ADMIN TOGGLE (View Scope)
        if st.session_state.role == "Admin":
            all_cos = ["All Companies"] + sorted([str(c) for c in full_df["company"].unique() if c])
            target_co = st.selectbox("View Scope", all_cos)
            display_df = full_df if target_co == "All Companies" else full_df[full_df["company"] == target_co]
        elif st.session_state.role == "Gas Company":
            target_co = st.session_state.get('company_link', "Indane")
            display_df = full_df[full_df["company"] == target_co]
            st.info(f"Secure View: {target_co}")
        else:
            display_df = full_df

        # 2. SUMMARY METRICS
        m1, m2, m3 = st.columns(3)
        m1.metric("Active Trucks", display_df["batch_id"].nunique())
        m2.metric("Total Cylinders", len(display_df))
        m3.metric("Damaged", (display_df["Status"].astype(str).str.upper() == "DAMAGED").sum())

        # 3. COMPLIANCE ALERTS (Concise & Scrollable)
        st.markdown("Compliance Alerts")
        if "Next_Test_Due" in display_df.columns:
            today = datetime.now().date()
            overdue = display_df[pd.to_datetime(display_df["Next_Test_Due"]).dt.date < today]
            
            if not overdue.empty:
                st.error(f"Critical: {len(overdue)} units have expired test dates.")
                with st.expander("View Overdue Units (Scrollable)"):
                    st.dataframe(
                        overdue[["Cylinder_ID", "Next_Test_Due", "company"]], 
                        height=200, 
                        use_container_width=True,
                        hide_index=True
                    )
            else:
                st.success("All units in this view are compliant.")

        # 4. EXPORT CENTER
        with st.expander("Filtered Data Export"):
            export_timeframe = st.radio("Timeframe:", ["All Data", "New (Last 7 Days)", "Historical"], horizontal=True)
            
            if "arrival_time" in display_df.columns:
                display_df["arrival_time"] = pd.to_datetime(display_df["arrival_time"])
                cutoff = datetime.now() - timedelta(days=7)
                if export_timeframe == "New (Last 7 Days)":
                    export_df = display_df[display_df["arrival_time"] >= cutoff]
                elif export_timeframe == "Historical":
                    export_df = display_df[display_df["arrival_time"] < cutoff]
                else:
                    export_df = display_df
            else:
                export_df = display_df

            st.download_button(
                label=f"Download CSV",
                data=export_df.to_csv(index=False).encode('utf-8'),
                file_name=f"report_{datetime.now().date()}.csv",
                mime="text/csv"
            )

        # 5. MASTER INVENTORY TOGGLE (New Feature)
        st.markdown("---")
        show_inventory = st.toggle("Show Master Inventory List", value=True)
        
        if show_inventory:
            st.subheader("📋 Master Inventory List")
            # Displays the full list only if the toggle is ON
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.info("Inventory list is hidden. Use the toggle above to view all records.")
            
# --- PAGE: FINANCIAL & BILLING ---
elif choice == "Financial & Billing":
    st.header("Batch Billing & Cost Analysis")
    RATE_CARD = {
        "Good / No Repair": 0, "Valve Leak (Minor)": 150, "Valve Replacement": 450,
        "Body Dent Repair": 300, "Re-painting Required": 200, "Foot Ring Straightening": 250, "Condemned": 0
    }
    
    if not full_df.empty:
        target_b = st.selectbox("Select Batch for Billing", sorted(full_df["batch_id"].unique().tolist()))
        batch_data = full_df[full_df["batch_id"] == target_b].dropna(subset=["Cylinder_ID"]).copy()
        batch_data["Cost"] = batch_data["Condition_Notes"].map(RATE_CARD).fillna(0)
        
        st.metric("Total Repair Bill", f"₹{batch_data['Cost'].sum():,.2f}")
        st.dataframe(batch_data[batch_data["Cost"] > 0][["Cylinder_ID", "Condition_Notes", "Cost"]], 
                     use_container_width=True, hide_index=True)
        
        # Download Bill as CSV
        st.download_button(label="📥 Download Bill (CSV)", 
                          data=batch_data.to_csv(index=False).encode('utf-8'),
                          file_name=f"bill_{target_b}.csv")

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
                    st.success(f"Batch {clean_batch_id} registered.")
                except Exception as e:
                    st.error(f"Error: {e}")

# --- PAGE: SEARCH ---
elif choice == "Search Unit":
    st.header("Search Inventory")
    col1, col2 = st.columns([1, 3])
    with col1:
        search_type = st.selectbox("Search By", ["Cylinder ID", "Batch ID", "Truck Plate"])
    with col2:
        query = st.text_input(f"Enter {search_type}").strip().upper()

    if query and not full_df.empty:
        if search_type == "Cylinder ID":
            results = full_df[full_df["Cylinder_ID"].astype(str).str.upper().str.contains(query, na=False)]
        elif search_type == "Batch ID":
            results = full_df[full_df["batch_id"].astype(str).str.upper().str.contains(query, na=False)]
        else:
            results = full_df[full_df["truck_number"].astype(str).str.upper().str.contains(query, na=False)]

        if not results.empty:
            st.dataframe(results, use_container_width=True, hide_index=True)
        else:
            st.info("No records found.")

# --- PAGE: GAS CO UPLOAD ---
elif choice == "Gas Co Upload":
    st.header("📤 Add Cylinder Manifest")
    tab1, tab2, tab3 = st.tabs(["📄 CSV Bulk Upload", "⌨️ Manual Entry", "📸 Scan Barcode"])

    with tab1:
        uploaded_file = st.file_uploader("Upload Company CSV Manifest", type="csv")
        if uploaded_file:
            upload_df = pd.read_csv(uploaded_file)
            if st.button("🚀 Confirm CSV Upload"):
                try:
                    upload_df["batch_id"] = upload_df["batch_id"].astype(str).str.strip().str.upper()
                    supabase.table("cylinders").insert(upload_df.to_dict(orient='records')).execute()
                    st.success("Successfully uploaded!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Error: {e}")

    with tab2:
        with st.form("manual_entry"):
            c1, c2 = st.columns(2)
            cid = c1.text_input("Cylinder ID")
            bid = c2.text_input("Batch ID")
            t_due = st.date_input("Test Due Date")
            if st.form_submit_button("Add Single Cylinder"):
                supabase.table("cylinders").insert({"Cylinder_ID": cid.upper(), "batch_id": bid.upper(), "Next_Test_Due": str(t_due), "Status": "Empty"}).execute()
                st.success("Added!")
                st.cache_data.clear()

    with tab3:
        img_file = st.camera_input("Take a photo of the barcode")
        if img_file:
            scanned_id = st.text_input("Verified ID from Photo").strip().upper()
            scanned_batch = st.text_input("Assign to Batch").strip().upper()
            if st.button("Confirm Scanned Entry"):
                supabase.table("cylinders").insert({"Cylinder_ID": scanned_id, "batch_id": scanned_batch, "Status": "Empty"}).execute()
                st.success("Scanned unit registered!")
                st.cache_data.clear()
























































































