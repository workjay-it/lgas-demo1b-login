import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="KWS | LGAS Management", layout="wide", page_icon="🏭")

# Custom CSS for the "Professional Dashboard" look
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e1e4e8; }
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; font-weight: bold; }
    .stDataFrame { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State
for key in ["authenticated", "user_role", "client_link", "last_refresh"]:
    if key not in st.session_state:
        st.session_state[key] = False if key == "authenticated" else ("Initializing..." if key == "last_refresh" else None)

# Supabase Connection
@st.cache_resource
def init_connection():
    URL = st.secrets["connections"]["supabase"]["url"]
    KEY = st.secrets["connections"]["supabase"]["key"]
    return create_client(URL, KEY)

supabase = init_connection()

# --- 2. DATA LOGIC ---
@st.cache_data(ttl=60)
def load_data():
    ist = pytz.timezone('Asia/Kolkata')
    st.session_state["last_refresh"] = datetime.now(ist).strftime("%I:%M:%S %p")
    res = supabase.table("cylinders").select("*").execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        for col in ["Last_Test_Date", "Next_Test_Due"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date
    return df

def login():
    st.markdown("<h1 style='text-align: center; color: #1a2a3a;'>🏭 KWS Industrial Portal</h1>", unsafe_allow_html=True)
    with st.container():
        _, col, _ = st.columns([1, 1.5, 1])
        with col:
            st.markdown("### Secure Login")
            email = st.text_input("Email/Username")
            pwd = st.text_input("Password", type="password")
            if st.button("Sign In"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                    profile = supabase.table("profiles").select("role, client_link").eq("id", res.user.id).single().execute()
                    st.session_state.update({
                        "authenticated": True, 
                        "user_role": profile.data["role"], 
                        "client_link": profile.data["client_link"]
                    })
                    st.rerun()
                except:
                    st.error("Invalid credentials. Please try again.")

# --- 3. MAIN INTERFACE ---
if not st.session_state["authenticated"]:
    login()
else:
    # Sidebar
    st.sidebar.markdown(f"### 🏭 KWS Logistics")
    st.sidebar.markdown(f"**User:** `{st.session_state['user_role'].upper()}`")
    
    menu = ["📊 Dashboard", "🔎 Cylinder Finder"]
    if st.session_state["user_role"] == "admin":
        menu += ["📦 Bulk Operations", "📋 Return Audit Log"]
    
    choice = st.sidebar.radio("Main Menu", menu)
    
    if st.sidebar.button("🔓 Sign Out"):
        st.session_state["authenticated"] = False
        st.rerun()

    df = load_data()

    # --- PAGE: DASHBOARD ---
    if choice == "📊 Dashboard":
        st.header("Cylinder Fleet Overview")
        # Isolation Logic
        display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Inventory", len(display_df))
        m2.metric("Status: Full", len(display_df[display_df["Status"] == "Full"]))
        m3.metric("Status: Empty", len(display_df[display_df["Status"] == "Empty"]))
        m4.metric("Under Testing", len(display_df[display_df["Status"] == "Under Testing"]))
        
        st.subheader("Inventory Details")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- PAGE: CYLINDER FINDER ---
    elif choice == "🔎 Cylinder Finder":
        st.header("Search Individual Unit")
        search_id = st.text_input("Scan or Enter Cylinder ID").strip().upper()
        if search_id:
            res = df[df["Cylinder_ID"] == search_id]
            if not res.empty:
                st.success(f"Record found for {search_id}")
                st.write(res.T) # Transposed view for better readability
            else:
                st.error("Cylinder ID not found in system.")

    # --- PAGE: BULK OPERATIONS (Scanner Optimized) ---
    elif choice == "📦 Bulk Operations":
        st.header("High-Volume Batch Processing")
        st.info("Scanner Ready: Paste a list of IDs from your scanner into the box below.")
        
        with st.form("bulk_form"):
            b_id = st.text_input("Batch Reference ID")
            bulk_input = st.text_area("Cylinder IDs (One per line or comma-separated)")
            new_stat = st.selectbox("Assign New Status", ["Full", "Empty", "Under Testing", "Ready for Dispatch"])
            
            if st.form_submit_button("🚀 Execute Batch Update"):
                id_list = [i.strip().upper() for i in bulk_input.replace(",", "\n").split("\n") if i.strip()]
                if id_list:
                    try:
                        supabase.table("cylinders").update({
                            "Status": new_stat, 
                            "Batch_ID": b_id,
                            "Last_Test_Date": str(datetime.now().date())
                        }).in_("Cylinder_ID", id_list).execute()
                        st.success(f"Successfully updated {len(id_list)} cylinders.")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Input area is empty.")

    # --- PAGE: RETURN AUDIT LOG ---
    elif choice == "📋 Return Audit Log":
        st.header("Quality Control: Incoming Returns")
        scan_id = st.text_input("Scan Cylinder to Audit").strip().upper()
        if scan_id:
            with st.form("audit_form"):
                cond = st.selectbox("Physical Condition", ["Good", "Dented", "Valve Leak", "Rusted", "Expired"])
                notes = st.text_area("Audit Notes")
                if st.form_submit_button("Log Audit & Mark Empty"):
                    try:
                        supabase.table("cylinders").update({
                            "Status": "Empty",
                            "Condition_Notes": f"{cond}: {notes}"
                        }).eq("Cylinder_ID", scan_id).execute()
                        st.success(f"Audit saved for {scan_id}")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(f"""
        <div style="text-align: center; color: gray; font-size: 0.85em;">
            KWS LGAS Management v2.1 | <b>Last Refresh:</b> {st.session_state['last_refresh']} IST
        </div>
    """, unsafe_allow_html=True)
















































