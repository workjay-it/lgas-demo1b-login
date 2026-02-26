import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client

# --- 1. SETTINGS & STYLING ---
st.set_page_config(page_title="KWS | LGAS Management", layout="wide", page_icon="🏭")

# Custom CSS to mimic the "Demo" look
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    [data-testid="stSidebar"] { background-color: #1a2a3a; color: white; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

# Initialize Session State
for key in ["authenticated", "user_role", "client_link", "last_refresh"]:
    if key not in st.session_state:
        st.session_state[key] = False if key == "authenticated" else ("Initializing..." if key == "last_refresh" else None)

# Supabase Setup
URL, KEY = st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"]
supabase = create_client(URL, KEY)

# --- 2. LOGIC: DATA & AUTH ---
@st.cache_data(ttl=60)
def load_data():
    ist = pytz.timezone('Asia/Kolkata')
    st.session_state["last_refresh"] = datetime.now(ist).strftime("%I:%M:%S %p")
    res = supabase.table("cylinders").select("*").execute()
    return pd.DataFrame(res.data)

def login():
    st.markdown("<h1 style='text-align: center;'>🏭 KWS Portal</h1>", unsafe_allow_html=True)
    with st.container():
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            email = st.text_input("Username/Email")
            pwd = st.text_input("Password", type="password")
            if st.button("Sign In"):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pwd})
                    profile = supabase.table("profiles").select("role, client_link").eq("id", res.user.id).single().execute()
                    st.session_state.update({"authenticated": True, "user_role": profile.data["role"], "client_link": profile.data["client_link"]})
                    st.rerun()
                except: st.error("Login Failed")

# --- 3. THE INTERFACE ---
if not st.session_state["authenticated"]:
    login()
else:
    # Sidebar Navigation with Icons
    st.sidebar.image("https://via.placeholder.com/150x50.png?text=KWS+LOGISTICS", use_container_width=True) # Replace with actual logo URL
    st.sidebar.markdown(f"**Welcome, {st.session_state['user_role'].upper()}**")
    
    menu = ["📊 Dashboard", "🔎 Cylinder Finder", "📦 Bulk Operations", "📋 Return Audit Log"]
    choice = st.sidebar.radio("Main Menu", menu)
    
    if st.sidebar.button("🔓 Sign Out"):
        st.session_state["authenticated"] = False
        st.rerun()

    df = load_data()

    # --- PAGE: DASHBOARD ---
    if choice == "📊 Dashboard":
        st.header("Cylinder Fleet Overview")
        # Filter for Private Users
        display_df = df if st.session_state["user_role"] == "admin" else df[df["Customer_Name"] == st.session_state["client_link"]]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Units", len(display_df))
        m2.metric("In Service (Full)", len(display_df[display_df["Status"] == "Full"]))
        m3.metric("Empty/Return", len(display_df[display_df["Status"] == "Empty"]))
        m4.metric("Under Testing", len(display_df[display_df["Status"] == "Under Testing"]))
        
        st.subheader("Inventory Data Table")
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    # --- PAGE: BULK OPERATIONS ---
    elif choice == "📦 Bulk Operations":
        st.header("Batch Management")
        with st.expander("🛠️ Processing Instructions", expanded=True):
            st.write("1. Enter Batch ID. 2. Scan all cylinders into text area. 3. Select Status. 4. Execute.")
        
        with st.form("bulk_form"):
            b_id = st.text_input("Batch Reference Number")
            bulk_ids = st.text_area("Scan IDs (Paste multiple barcodes here)")
            new_stat = st.selectbox("New Status", ["Full", "Empty", "Under Testing", "Ready for Dispatch"])
            if st.form_submit_button("Update Batch"):
                id_list = [i.strip().upper() for i in bulk_ids.replace(",", "\n").split("\n") if i.strip()]
                supabase.table("cylinders").update({"Status": new_stat, "Batch_ID": b_id}).in_("Cylinder_ID", id_list).execute()
                st.success(f"Batch {b_id} Updated!")
                st.cache_data.clear()

    # --- PAGE: RETURN AUDIT ---
    elif choice == "📋 Return Audit Log":
        st.header("Quality Control Audit")
        c_id = st.text_input("Scan/Enter Cylinder ID").upper()
        if c_id:
            with st.form("audit"):
                cond = st.selectbox("Condition", ["Pristine", "Dented", "Valve Leak", "Rusted"])
                st.form_submit_button("Log Audit") # Logic to update DB

    # --- FOOTER ---
    st.markdown("---")
    st.markdown(f"<p style='text-align: center; color: gray;'>KWS LGAS v2.1 | Refreshed: {st.session_state['last_refresh']}</p>", unsafe_allow_html=True)



























































