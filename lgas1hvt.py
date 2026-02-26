import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client 

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 1. SETTINGS & CONNECTION ---
st.set_page_config(page_title="KWS LGAS Management", layout="wide")

# Fetch credentials directly from st.secrets
URL = st.secrets["connections"]["supabase"]["url"]
KEY = st.secrets["connections"]["supabase"]["key"]

# Initialize the Supabase client directly
@st.cache_resource
def init_connection():
    return create_client(URL, KEY)

supabase = init_connection()

# Initialize Session State
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_role" not in st.session_state:
    st.session_state["user_role"] = None
if "bulk_ids_val" not in st.session_state:
    st.session_state.bulk_ids_val = ""
if "batch_search_val" not in st.session_state:
    st.session_state.batch_search_val = ""

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 2. LOGIN & REGISTRATION PAGE ---
def login_page():
    st.title("🔐 KWS Cylinder Portal")
    
    # Create tabs for Login and Register
    tab1, tab2 = st.tabs(["Login", "Register New Company"])

    with tab1:
        with st.container(border=True):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login", use_container_width=True, type="primary"):
                try:
                    # Auth with Supabase
                    auth_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    user_id = auth_res.user.id
                    
                    # Fetch profile details
                    prof_res = supabase.table("profiles").select("*").eq("id", user_id).single().execute()
                    
                    st.session_state["authenticated"] = True
                    st.session_state["user_role"] = prof_res.data["role"]
                    st.session_state["client_link"] = prof_res.data["client_link"]
                    st.session_state["full_name"] = prof_res.data.get("full_name", "User")
                    st.rerun()
                except Exception as e:
                    st.error("Login failed. Please check your credentials.")

    with tab2:
        st.subheader("Create Company Account")
        with st.container(border=True):
            new_email = st.text_input("Company Email", key="reg_email")
            new_password = st.text_input("Set Password", type="password", key="reg_pass")
            full_name = st.text_input("Contact Person Name", key="reg_name")
            company_name = st.text_input("Company Name (Exact name for data linking)", key="reg_company")
            
            st.info("Note: New accounts are set to 'private_user' by default for security.")
            
            if st.button("Create Account", use_container_width=True):
                if not new_email or not new_password or not company_name:
                    st.warning("Please fill in all fields.")
                else:
                    try:
                        # 1. Sign up user in Supabase Auth (Internal table)
                        auth_res = supabase.auth.sign_up({
                            "email": new_email, 
                            "password": new_password
                        })
                        
                        if auth_res.user:
                            # 2. Create the profile in your public 'profiles' table
                            supabase.table("profiles").insert({
                                "id": auth_res.user.id,
                                "full_name": full_name,
                                "client_link": company_name,
                                "role": "private_user" # Default safety role
                            }).execute()
                            
                            st.success("✅ Account created! You can now switch to the Login tab.")
                    except Exception as e:
                        st.error(f"Registration failed: {e}")

# Logout Function (Keep this as is)
def logout():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# Authentication Gatekeeper
if not st.session_state["authenticated"]:
    login_page()
    st.stop()
    
#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 3. SIDEBAR NAVIGATION ---
role = st.session_state["user_role"]
st.sidebar.title(f"👋 {st.session_state['full_name']}")
st.sidebar.write(f"**Role:** {role.upper() if role else 'N/A'}")

if role == "admin":
    menu = ["Dashboard", "Cylinder Finder", "Bulk Operations", "Inventory Management"]
elif role == "bulk_user":
    menu = ["Dashboard", "Cylinder Finder", "Bulk Operations"]
else:
    menu = ["Dashboard", "Cylinder Finder"]

page = st.sidebar.selectbox("Navigate", menu)
st.sidebar.divider()
if st.sidebar.button("Logout", use_container_width=True):
    logout()

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 4. DATA LOADING ---
@st.cache_data(ttl=60)
def load_cylinders():
    query = supabase.table("cylinders").select("*")
    if role != "admin":
        query = query.eq("Customer_Name", st.session_state["client_link"])
    res = query.execute()
    return pd.DataFrame(res.data)

df_main = load_cylinders()

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 5. DASHBOARD ---
if page == "Dashboard":
    st.title("📊 Fleet Overview")
    if not df_main.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Cylinders", len(df_main))
        col2.metric("In Testing (Empty)", len(df_main[df_main["Status"] == "Empty"]) if "Status" in df_main.columns else 0)
        if "Overdue" in df_main.columns:
            col3.metric("Overdue Units", len(df_main[df_main["Overdue"] == True]))
        st.dataframe(df_main, use_container_width=True, hide_index=True)
    else:
        st.info("No cylinders found.")

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 6. BULK OPERATIONS ---
elif page == "Bulk Operations":
    st.title("🚛 Bulk Management & Reconciliation")
    TARGET_TABLE = "TEST_cylinders" 
    
    with st.container(border=True):
        c_id, c_btn = st.columns([3, 1])
        batch_lookup = c_id.text_input("Search Batch ID", value=st.session_state.batch_search_val)
        
        batch_data = pd.DataFrame()
        if batch_lookup:
            query = supabase.table(TARGET_TABLE).select("*").eq("Batch_ID", batch_lookup)
            if role != "admin":
                query = query.eq("Customer_Name", st.session_state["client_link"])
            res = query.execute()
            batch_data = pd.DataFrame(res.data)
            
            if not batch_data.empty:
                if c_btn.button("🔍 Pull Pending IDs"):
                    remaining = batch_data[batch_data["Status"] != "Full"]
                    ids = remaining["Cylinder_ID"].tolist() if not remaining.empty else batch_data["Cylinder_ID"].tolist()
                    st.session_state.bulk_ids_val = "\n".join(map(str, ids))
                    st.session_state.batch_search_val = batch_lookup
                    st.session_state["confirm_batch"] = batch_lookup
                    st.rerun()

    st.divider()

    with st.expander("📝 Process Updates", expanded=True):
        f1, f2 = st.columns(2)
        with f1:
            t_batch = st.text_input("Confirm Batch ID", key="confirm_batch")
            new_loc = st.selectbox("New Location", ["Testing Center", "Gas Company"])
        with f2:
            new_stat = st.selectbox("Update Status", ["No Change", "Empty", "Full", "Damaged"])
            new_owner = st.text_input("Owner Name", value=st.session_state["client_link"] if role != "admin" else "")

        bulk_ids = st.text_area("Cylinder IDs", value=st.session_state.bulk_ids_val, height=150)

        if st.button("🚀 Execute Bulk Update", type="primary", use_container_width=True):
            if bulk_ids:
                id_list = [i.strip().upper() for i in bulk_ids.replace(',', '\n').split('\n') if i.strip()]
                payload = {"Current_Location": new_loc}
                if t_batch: payload["Batch_ID"] = t_batch
                if new_stat != "No Change": payload["Status"] = new_stat
                if new_owner: payload["Customer_Name"] = new_owner

                try:
                    supabase.table(TARGET_TABLE).update(payload).in_("Cylinder_ID", id_list).execute()
                    st.success("Updated!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

    if not batch_data.empty:
        st.subheader(f"🚩 Reconciliation: {batch_lookup}")
        total = len(batch_data)
        full = len(batch_data[batch_data["Status"] == "Full"]) if "Status" in batch_data.columns else 0
        st.progress(full/total if total > 0 else 0)
        m1, m2, m3 = st.columns(3)
        m1.metric("Sent Back (Full)", full)
        m2.metric("In Testing (Empty)", len(batch_data[batch_data["Status"] == "Empty"]) if "Status" in batch_data.columns else 0)
        m3.metric("Damaged", len(batch_data[batch_data["Status"] == "Damaged"]) if "Status" in batch_data.columns else 0)

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 7. CYLINDER FINDER ---
elif page == "Cylinder Finder":
    st.title("🔍 Individual Cylinder Lookup")
    search_id = st.text_input("Enter Cylinder ID").strip().upper()
    if search_id:
        result = df_main[df_main["Cylinder_ID"] == search_id] if not df_main.empty else pd.DataFrame()
        if not result.empty:
            st.dataframe(result, use_container_width=True, hide_index=True)
        else:
            st.warning("Not found.")

#------------------------------------------------------------------------------------------------------------------------------------------------------------

# --- 8. INVENTORY MANAGEMENT ---
elif page == "Inventory Management":
    st.title("⚙️ System Inventory Management")
    with st.form("add_cylinder_form"):
        new_id = st.text_input("Cylinder ID")
        new_cust = st.text_input("Assign to Customer")
        new_cap = st.number_input("Capacity (kg)", min_value=0.0)
        if st.form_submit_button("Add to System"):
            try:
                supabase.table("cylinders").insert({
                    "Cylinder_ID": new_id.upper(), "Customer_Name": new_cust,
                    "Capacity_kg": new_cap, "Status": "Empty", "Current_Location": "Testing Center"
                }).execute()
                st.success("Added!")
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Error: {e}")



























































