import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="KWS | LGAS Management", layout="wide") 

# Custom CSS: FIXED for Dark Mode (Removes White Background from Metrics)
st.markdown("""
    <style>
    /* Main background to match Streamlit dark theme */
    .main { background-color: #0e1117; }
    
    /* Metric Cards: Now Dark Grey with Light Text */
    [data-testid="stMetric"] {
        background-color: #1e2129;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        border: 1px solid #31333f;
    }
    
    /* Ensure metric text is white/light */
    [data-testid="stMetricValue"] { color: #ffffff !important; }
    [data-testid="stMetricLabel"] { color: #808495 !important; }

    /* Sidebar Styling */
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    
    /* Button Styling */
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
    st.markdown("<h1 style='text-align: center;'>🏭 KWS Industrial Portal</h1>", unsafe_allow_html=True)
    with st.container():
        _, col, _ = st.columns([1, 1.5, 1])
        with col:
            email = st.text_input("Email")
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
                    st.error("Invalid credentials.")

# --- 3. MAIN INTERFACE ---
if not st.session_state["authenticated"]:
    login()
else:
    # Sidebar
    st.sidebar.markdown(f"### KWS Logistics")
    st.sidebar.markdown(f"**Role:** `{st.session_state['user_role'].upper()}`")
    
    menu = ["Dashboard", "Cylinder Finder"]
    if st.session_state["user_role"] == "admin":
        menu += ["Bulk Operations", " Return Audit Log"]
    
    choice = st.sidebar.radio("Main Menu", menu)
    
    if st.sidebar.button(" Sign Out"):
        st.session_state["authenticated"] = False
        st.rerun()

    df = load_data()

    # --- PAGE: DASHBOARD ---
    if choice == "Dashboard":
        st.header("Cylinder Fleet Overview")
        display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
        
        # Metrics with the new Dark Backgrounds
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Inventory", len(display_df))
        m2.metric("In Service (Full)", len(display_df[display_df["Status"] == "Full"]))
        m3.metric("Empty/Return", len(display_df[display_df["Status"] == "Empty"]))
        m4.metric("Under Testing", len(display_df[display_df["Status"] == "Under Testing"]))
        
        st.subheader("Inventory Details")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- PAGE: CYLINDER FINDER ---
    elif choice == "Cylinder Finder":
        st.header("Unit Search")
        search_id = st.text_input("Scan Cylinder ID").strip().upper()
        if search_id:
            res = df[df["Cylinder_ID"] == search_id]
            if not res.empty:
                st.write(res.T)
            else:
                st.error("Not found.")

    # --- PAGE: BULK OPERATIONS (For Gas Company Lots) ---
    elif choice == "Bulk Operations":
        st.header("Bulk Batch Processing")
        with st.form("bulk_form"):
            b_id = st.text_input("Batch ID")
            bulk_input = st.text_area("Paste IDs (One per line)")
            new_stat = st.selectbox("Status", ["Full", "Empty", "Under Testing"])
            if st.form_submit_button("Update Batch"):
                id_list = [i.strip().upper() for i in bulk_input.replace(",", "\n").split("\n") if i.strip()]
                if id_list:
                    supabase.table("cylinders").update({"Status": new_stat, "Batch_ID": b_id}).in_("Cylinder_ID", id_list).execute()
                    st.success("Batch Updated!")
                    st.cache_data.clear()

    # --- PAGE: RETURN AUDIT LOG ---
    elif choice == "Return Audit Log":
        st.header("Return Audit")
        scan_id = st.text_input("Scan ID to Audit").strip().upper()
        if scan_id:
            with st.form("audit_form"):
                cond = st.selectbox("Condition", ["Good", "Dented", "Leaking"])
                if st.form_submit_button("Log Return"):
                    supabase.table("cylinders").update({"Status": "Empty", "Condition_Notes": cond}).eq("Cylinder_ID", scan_id).execute()
                    st.success(f"Audit saved for {scan_id}")
                    st.cache_data.clear()

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(f"<p style='text-align: center; color: gray;'>KWS LGAS | Last Refresh: {st.session_state['last_refresh']}</p>", unsafe_allow_html=True)














































