import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from supabase import create_client, Client

# --- 1. INITIALIZE & CONNECTION ---
st.set_page_config(page_title="Gas Industrial Operations Portal", layout="wide")

# Initialize Session State variables
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "last_refresh" not in st.session_state:
    st.session_state["last_refresh"] = "Initializing..."

# Supabase Setup
URL = st.secrets["connections"]["supabase"]["url"]
KEY = st.secrets["connections"]["supabase"]["key"]

@st.cache_resource
def init_connection():
    return create_client(URL, KEY)

supabase = init_connection()

# --- 2. DATA LOADING ---
@st.cache_data(ttl=60)
def load_data():
    # Update timestamp
    ist = pytz.timezone('Asia/Kolkata')
    st.session_state["last_refresh"] = datetime.now(ist).strftime("%I:%M:%S %p")
    
    # Fetch Data
    res = supabase.table("cylinders").select("*").execute()
    df = pd.DataFrame(res.data)
    
    if not df.empty:
        # Standardize date formats
        for col in ["Last_Test_Date", "Next_Test_Due"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date
    return df

# --- 3. AUTHENTICATION ---
def login():
    st.title("Gas Management Industrial Portal")
    with st.container():
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            try:
                res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user_id = res.user.id
                
                # Fetch role from profiles table
                profile = supabase.table("profiles").select("role, client_link").eq("id", user_id).single().execute()
                
                st.session_state["user_role"] = profile.data["role"]
                st.session_state["client_link"] = profile.data["client_link"]
                st.session_state["authenticated"] = True
                st.rerun()
            except Exception as e:
                st.error("Invalid credentials. Please try again.")

# --- 4. MAIN APP LOGIC ---
if not st.session_state["authenticated"]:
    login()
else:
    # --- 5. SIDEBAR ---
    st.sidebar.title("🏭 Operations")
    df_main = load_data()
    
    # Filter menu based on role
    menu = ["Dashboard", "Cylinder Finder"]
    if st.session_state["user_role"] == "admin":
        menu += ["Bulk Operations", "Return Audit Log"]
    
    page = st.sidebar.radio("Navigation", menu)
    
    if st.sidebar.button("Logout"):
        st.session_state["authenticated"] = False
        st.rerun()

    # --- 6. PAGE: DASHBOARD ---
    if page == "Dashboard":
        st.title("Fleet Dashboard")
        
        # Apply data isolation for private users
        if st.session_state["user_role"] != "admin":
            df_display = df_main[df_main["Customer_Name"] == st.session_state["client_link"]]
        else:
            df_display = df_main

        c1, c2, c3 = st.columns(3)
        c1.metric("Total Cylinders", len(df_display))
        c2.metric("Due for Testing", len(df_display[df_display["Status"] == "Under Testing"]))
        c3.metric("Ready/Full", len(df_display[df_display["Status"] == "Full"]))
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    # --- 7. PAGE: BULK OPERATIONS (For High Volume) ---
    elif page == "Bulk Operations":
        st.title("Bulk Batch Processing")
        st.info("Scanner Ready: Paste multiple IDs below.")
        
        with st.form("bulk_update"):
            batch_id = st.text_input("Batch Reference (Optional)")
            ids_input = st.text_area("Cylinder IDs (One per line or comma-separated)")
            new_status = st.selectbox("Update Status To", ["Full", "Empty", "Under Testing", "Scrapped"])
            
            if st.form_submit_button("Execute Bulk Update"):
                # Clean the input string into a list
                clean_ids = [x.strip().upper() for x in ids_input.replace(",", "\n").split("\n") if x.strip()]
                
                if clean_ids:
                    try:
                        supabase.table("cylinders").update({
                            "Status": new_status,
                            "Last_Test_Date": str(datetime.now().date())
                        }).in_("Cylinder_ID", clean_ids).execute()
                        
                        st.success(f"Updated {len(clean_ids)} cylinders successfully!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Please enter at least one Cylinder ID.")

    # --- 8. PAGE: RETURN AUDIT LOG ---
    elif page == "Return Audit Log":
        st.title("Return Condition Audit")
        c_id = st.text_input("🔍 Scan Cylinder to Audit").upper()
        
        if c_id:
            with st.form("audit_form"):
                condition = st.selectbox("Physical State", ["Good", "Dented", "Valve Leak", "Rusted"])
                notes = st.text_area("Internal Notes")
                if st.form_submit_button("Log Audit"):
                    supabase.table("cylinders").update({
                        "Status": "Empty",
                        "Condition_Notes": notes
                    }).eq("Cylinder_ID", c_id).execute()
                    st.success(f"Audit recorded for {c_id}")
                    st.cache_data.clear()

    # --- 9. FOOTER ---
    st.markdown("---")
    st.markdown(f"""
        <div style="text-align: center; color: grey; font-size: 0.8em;">
            Developed for KWS Pvt Ltd | <b>Last Refresh:</b> {st.session_state['last_refresh']} IST
        </div>
    """, unsafe_allow_html=True)



























































