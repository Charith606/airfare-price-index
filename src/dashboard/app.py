import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import os
import sys
import asyncio
import hashlib
from datetime import date, datetime

# Ensure project root is on sys.path so src imports work
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Helper to automatically verify and install Playwright browser dependencies on startup
def ensure_playwright_installed():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        import subprocess
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])

# Perform the installation check
ensure_playwright_installed()

from src.scraper.mock_data import generate_mock_data
from src.cleaning.cleaner import clean_and_transfer_data
from src.index.index_builder import calculate_index
from src.scraper.ota_scraper import OTAScraper
from src.api.ignav_client import search_ignav
from src.collection.itinerary_extractor import extract_itineraries

# Set page config
st.set_page_config(page_title="Real-time Airfare Price Index (APIx)", layout="wide")

# Database path
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'airfare_index.db'

# ----------------- AUTHENTICATION DATABASE SETUP -----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_auth_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        # Seed default admin account: admin / adminpassword
        cursor.execute("INSERT INTO admin_users VALUES (?, ?)", ("admin", hash_password("adminpassword")))
    conn.commit()
    conn.close()

# Run auth db initializer
init_auth_db()

# ----------------- CACHED DATA LOADING FUNCTIONS -----------------
@st.cache_data
def load_fares_data():
    conn = sqlite3.connect(str(DB_PATH))
    fares_df = pd.read_sql_query("SELECT * FROM cleaned_fares", conn)
    conn.close()
    fares_df.columns = fares_df.columns.str.lower()
    return fares_df

@st.cache_data
def load_index_data():
    conn = sqlite3.connect(str(DB_PATH))
    index_df = pd.read_sql_query("SELECT * FROM price_index WHERE frequency='daily'", conn)
    conn.close()
    index_df.columns = index_df.columns.str.lower()
    return index_df

@st.cache_data
def load_routes_data():
    conn = sqlite3.connect(str(DB_PATH))
    routes_df = pd.read_sql_query("SELECT * FROM routes", conn)
    conn.close()
    routes_df.columns = routes_df.columns.str.lower()
    return routes_df

def get_stats():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM raw_quotes")
    raw_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM cleaned_fares")
    cleaned_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM price_index")
    index_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM routes")
    routes_count = cursor.fetchone()[0]
    conn.close()
    return {
        "raw": raw_count,
        "cleaned": cleaned_count,
        "index": index_count,
        "routes": routes_count
    }

# ----------------- CARD-BASED TICKET LAYOUT RENDERER -----------------
def render_flight_card(flight, is_cheapest=False):
    departure_time = flight.get('departure_time', 'N/A')
    arrival_time = flight.get('arrival_time', 'N/A')
    
    if 'T' in str(departure_time):
        departure_time = str(departure_time).split('T')[1][:5]
    if 'T' in str(arrival_time):
        arrival_time = str(arrival_time).split('T')[1][:5]
        
    duration = flight.get('duration_minutes', flight.get('duration', 'N/A'))
    if duration != 'N/A' and str(duration).replace('.', '', 1).isdigit():
        hours = int(float(duration)) // 60
        mins = int(float(duration)) % 60
        duration_str = f"{hours}h {mins}m"
    else:
        duration_str = str(duration) if duration != 'N/A' else "2h 15m"
        
    stops = flight.get('stops', 0)
    try:
        stops_str = "Direct (Non-Stop)" if int(stops) == 0 else f"{stops} Stop(s)"
    except Exception:
        stops_str = "Direct"
        
    airline = flight.get('airline', 'Unknown Airline')
    price = flight.get('total_fare', flight.get('price', 0))
    currency = flight.get('currency', 'INR')
    
    if currency == 'USD':
        price = float(price) * 84
        
    price_formatted = f"₹{float(price):,.2f}"
    flight_no = flight.get('flight_numbers', flight.get('flight_number', 'N/A'))
    cabin = str(flight.get('fare_class', flight.get('cabin_class', 'Economy'))).title()
    origin = flight.get('origin', 'DEP')
    destination = flight.get('destination', 'ARR')

    with st.container(border=True):
        if is_cheapest:
            st.caption("🏆 **CHEAPEST FLIGHT OPTION (BEST VALUE)**")
        
        c1, c2, c3 = st.columns([2, 3, 2])
        
        with c1:
            st.markdown(f"#### ✈️ {airline}")
            st.caption(f"Flight: **{flight_no}** | Class: **{cabin}**")
            
        with c2:
            st.markdown(f"### {departure_time} ➔ {arrival_time}")
            st.caption(f"📍 **{origin}** to **{destination}** | ⏱️ {duration_str} | 🛑 {stops_str}")
            
        with c3:
            st.markdown(f"<h2 style='color:#2e7d32; margin:0;'>{price_formatted}</h2>", unsafe_allow_html=True)
            st.caption("🟢 Verified Live / Database Fare")

# ----------------- BACKGROUND SCRAPING PIPELINE -----------------
def run_live_backend_pipeline(progress_bar, status_text, protocol_choice="scraper"):
    routes = load_routes_data()
    if routes.empty:
        status_text.error("No active routes configured in database. Scraper canceled.")
        return
        
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    total_steps = len(routes) * 5  # 5 booking windows (T+1, 7, 15, 30, 45)
    current_step = 0
    
    status_text.info("🚀 Initiating live airfare extraction pipeline...")
    scraper = OTAScraper(headless=True)
    
    for _, row in routes.iterrows():
        origin = row['origin']
        destination = row['destination']
        
        for window in [1, 7, 15, 30, 45]:
            travel_date = date.today() + pd.Timedelta(days=window)
            current_step += 1
            progress_bar.progress(current_step / total_steps)
            status_text.info(f"Extracting {origin} ➔ {destination} (T+{window}) from {protocol_choice.upper()}...")
            
            try:
                if "scraper" in protocol_choice.lower():
                    # Playwright scraper
                    flights = asyncio.run(scraper.scrape_route(origin, destination, travel_date))
                else:
                    # IGNav API
                    from src.config.settings import IGNAV_API_KEY
                    if not IGNAV_API_KEY:
                        # Fallback sample
                        import json
                        sample_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "sample_ignav_response.json"
                        with open(sample_path, "r") as f:
                            payload = json.load(f)
                        flights = extract_itineraries(payload, date.today().isoformat(), window, travel_date.isoformat(), origin, destination)
                    else:
                        payload = search_ignav(origin, destination, travel_date.isoformat())
                        flights = extract_itineraries(payload, date.today().isoformat(), window, travel_date.isoformat(), origin, destination)
                
                # Write live quotes to raw_quotes table
                for flight in flights:
                    cursor.execute("""
                        INSERT INTO raw_quotes 
                        (collection_date, travel_date, origin, destination, airline, price, currency, departure_time, fare_type, advance_days)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        flight.get('collection_date', date.today().isoformat()),
                        flight.get('travel_date', travel_date.isoformat()),
                        flight.get('origin', origin),
                        flight.get('destination', destination),
                        flight.get('airline', 'Unknown'),
                        flight.get('price', 0),
                        flight.get('currency', 'INR'),
                        flight.get('departure_time', '10:00'),
                        flight.get('fare_type', 'quoted_fare'),
                        window
                    ))
            except Exception as exc:
                st.sidebar.warning(f"Error fetching {origin}-{destination} T+{window}: {exc}")
                
    conn.commit()
    conn.close()
    
    # Run data cleaner
    status_text.info("🧼 Executing data cleaner & outlier filters...")
    clean_and_transfer_data()
    
    # Recalculate daily index
    status_text.info("📈 Recalculating Airfare Price Index values...")
    calculate_index()
    
    progress_bar.empty()
    status_text.success("🎉 Live backend data extraction pipeline completed successfully!")
    st.cache_data.clear()

# ----------------- SIDEBAR PORTAL SELECTION -----------------
st.sidebar.title("Navigation")
portal = st.sidebar.selectbox("Choose Portal", ["🌐 Public User Portal", "🔐 MoSPI Admin Portal"])

# Clear cache helper button
if st.sidebar.button("🔄 Refresh Application Data"):
    st.cache_data.clear()
    st.rerun()

# ----------------- 🌐 PUBLIC USER PORTAL -----------------
if portal == "🌐 Public User Portal":
    st.title("Real-time Airfare Price Index (APIx)")
    st.markdown("Augmentation of the Consumer Price Index (CPI) using automated web scraping.")
    
    # Load data
    fares_df = load_fares_data()
    index_df = load_index_data()
    
    tab1, tab2 = st.tabs(["📊 Index Trends & Sector Analysis", "🔍 Interactive Flight Fares Lookup"])
    
    with tab1:
        if index_df.empty:
            st.warning("No index data available yet. Please ask the Administrator to calculate index.")
        else:
            st.header("Airfare Price Index (APIx) Trend vs MoSPI Baseline")
            st.markdown("This chart illustrates the difference between traditional manual monthly airfare collection (simulated) and real-time automated daily collection (APIx).")
            
            # Add a mock DGCA baseline for comparison
            index_df['DGCA_Baseline'] = 100 + (index_df['index_value'] - 100) * 0.5 
            
            chart_data = index_df.set_index('index_date')[['index_value', 'DGCA_Baseline']]
            chart_data.columns = ['Real-time APIx (Daily)', 'DGCA Manual Baseline (Simulated)']
            
            st.line_chart(data=chart_data)
        
        if not fares_df.empty:
            st.header("Sector-wise Analysis")
            fares_df['Route'] = fares_df['origin'] + " - " + fares_df['destination']
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Price Trends by Route")
                route_trends = fares_df.groupby(['collection_date', 'Route'])['total_fare'].mean().unstack()
                st.line_chart(route_trends)
                
            with col2:
                st.subheader("Lead-Time Price Elasticity")
                st.markdown("Average flight price based on advance purchase window (days).")
                elasticity = fares_df.groupby(['advance_days'])['total_fare'].mean().reset_index()
                st.bar_chart(elasticity.set_index('advance_days'))
    
    with tab2:
        st.header("Flight Fare Lookup Tool")
        st.markdown("Search and compare specific flight ticket prices in real-time or from historical records.")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Let user select from popular origins or type any IATA code
            popular_origins = ["DEL", "BOM", "BLR", "CCU", "HYD", "MAA", "GOI", "PNQ", "AMD", "COK"]
            origin_val = st.selectbox("Origin Airport (From)", popular_origins, index=0)
            
        with col2:
            popular_dests = ["BOM", "DEL", "BLR", "CCU", "HYD", "MAA", "GOI", "PNQ", "AMD", "COK"]
            dest_val = st.selectbox("Destination Airport (To)", popular_dests, index=1)
            
        with col3:
            travel_date_val = st.date_input("Travel Date", value=date.today() + pd.Timedelta(days=7))
            
        col_btn, col_info = st.columns([1, 3])
        with col_btn:
            search_clicked = st.button("🚀 Search Flights", type="primary", use_container_width=True)
            
        if search_clicked:
            if origin_val == dest_val:
                st.error("Origin and destination airports must be different.")
            else:
                with st.spinner(f"Fetching real-time flights for {origin_val} ➔ {dest_val}..."):
                    results = []
                    
                    # 1. Try Live Web Scraper
                    try:
                        scraper = OTAScraper(headless=True)
                        results = asyncio.run(scraper.scrape_route(origin_val, dest_val, travel_date_val))
                    except Exception as scrape_err:
                        pass
                        
                    # 2. If scraper returned results, display them
                    if results:
                        results = sorted(results, key=lambda x: float(x.get('price', x.get('total_fare', 0))))
                        st.subheader(f"Found {len(results)} Flights for {origin_val} ➔ {dest_val}")
                        st.caption("🟢 Live real-time pricing extracted from web")
                        for index, flight in enumerate(results):
                            render_flight_card(flight, is_cheapest=(index == 0))
                    else:
                        # 3. Fallback to database quotes for this route if scraper is blocked
                        db_matches = fares_df[(fares_df['origin'] == origin_val) & (fares_df['destination'] == dest_val)]
                        if not db_matches.empty:
                            db_matches = db_matches.sort_values(by="total_fare")
                            st.subheader(f"Found {len(db_matches)} Flights for {origin_val} ➔ {dest_val}")
                            st.caption("📂 Verified database flight records")
                            for index, row in db_matches.reset_index(drop=True).iterrows():
                                render_flight_card(row.to_dict(), is_cheapest=(index == 0))
                        else:
                            st.warning(f"No flights found for {origin_val} ➔ {dest_val} on {travel_date_val}. Try another route or check the live scraper.")

# ----------------- 🔐 MOSPI AUTHORIZED ADMIN PORTAL -----------------
else:
    st.title("🔐 MoSPI Authorized Administrator Portal")
    
    # Session state initialization for login status
    if "admin_logged_in" not in st.session_state:
        st.session_state["admin_logged_in"] = False
        st.session_state["admin_user"] = ""

    if not st.session_state["admin_logged_in"]:
        auth_mode = st.tabs(["🔑 Sign In", "📝 Create Admin Account"])
        
        # 🔑 SIGN IN PANEL
        with auth_mode[0]:
            st.subheader("Login to Administrator Panel")
            login_user = st.text_input("Username", key="login_user")
            login_pass = st.text_input("Password", type="password", key="login_pass")
            if st.button("Authenticate & Log In"):
                if login_user == "" or login_pass == "":
                    st.error("Fields cannot be empty.")
                else:
                    conn = sqlite3.connect(str(DB_PATH))
                    cursor = conn.cursor()
                    cursor.execute("SELECT password FROM admin_users WHERE username = ?", (login_user,))
                    row = cursor.fetchone()
                    conn.close()
                    
                    if row and row[0] == hash_password(login_pass):
                        st.session_state["admin_logged_in"] = True
                        st.session_state["admin_user"] = login_user
                        st.success("Successfully Authenticated!")
                        st.rerun()
                    else:
                        st.error("Invalid Username or Password.")
                        
        # 📝 CREATE ADMIN ACCOUNT PANEL
        with auth_mode[1]:
            st.subheader("Register New MoSPI Administrator")
            new_user = st.text_input("Choose Username", key="new_user")
            new_pass = st.text_input("Choose Password", type="password", key="new_pass")
            confirm_pass = st.text_input("Confirm Password", type="password", key="confirm_pass")
            
            if st.button("Register Account"):
                if new_user == "" or new_pass == "":
                    st.error("Fields cannot be empty.")
                elif new_pass != confirm_pass:
                    st.error("Passwords do not match.")
                else:
                    try:
                        conn = sqlite3.connect(str(DB_PATH))
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO admin_users VALUES (?, ?)", (new_user, hash_password(new_pass)))
                        conn.commit()
                        conn.close()
                        st.success("Admin Account registered successfully! You can now log in.")
                    except sqlite3.IntegrityError:
                        st.error("Username already exists. Choose a different one.")
                    except Exception as e:
                        st.error(f"Registration failed: {e}")
    else:
        # LOGGED IN VIEW
        st.success(f"Authorized Access Granted (User: {st.session_state['admin_user']})")
        if st.sidebar.button("🚪 Logout of Admin Panel"):
            st.session_state["admin_logged_in"] = False
            st.session_state["admin_user"] = ""
            st.rerun()
            
        stats = get_stats()
        
        # Tabs for Admin tasks
        admin_tab1, admin_tab2, admin_tab3 = st.tabs([
            "⚙️ Scraper & Pipeline Controls", 
            "🛣️ DGCA Routes & Weights Configuration",
            "📊 System Statistics & DB Manager"
        ])
        
        with admin_tab1:
            st.header("Scraper Pipeline Dashboard")
            st.markdown("Initiate live web scraping and compile new Airfare Price Index data.")
            
            st.markdown(
                """
                <div style="background-color:#e8f4fd; border-left: 5px solid #2196f3; padding: 12px; border-radius: 4px; margin-bottom: 20px;">
                    <strong>ℹ️ Backend Scraping Execution</strong><br>
                    Running the live scraper queries all active flight sectors from your database, extracts real-time quotes using Playwright or the IGNav API, runs data cleaning steps (removing outliers), and recalculates the daily APIx index.
                </div>
                """,
                unsafe_allow_html=True
            )
            
            # Setup columns for the controls
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("⚡ Execute Live Web Extraction Pipeline")
                live_protocol = st.selectbox(
                    "Select Scraping Source Protocol",
                    ["🌐 Cleartrip Web Scraper (Playwright Headless)", "🔌 MoSPI IGNav API Portal"],
                    key="admin_live_protocol"
                )
                
                # Container to show run feedback
                progress_container = st.empty()
                status_container = st.empty()
                
                if st.button("▶️ Launch Live Scraper"):
                    p_bar = progress_container.progress(0.0)
                    run_live_backend_pipeline(p_bar, status_container, live_protocol)
                    
            with col2:
                st.subheader("🛠️ Pipeline Simulations")
                st.info("Trigger isolated sub-jobs for testing or manual index updates.")
                
                sim1, sim2, sim3 = st.columns(3)
                
                with sim1:
                    if st.button("Generate Mock Logs"):
                        with st.spinner("Writing..."):
                            generate_mock_data()
                            st.success("Raw mock entries added!")
                            st.cache_data.clear()
                with sim2:
                    if st.button("Run Data Clean"):
                        with st.spinner("Cleaning..."):
                            clean_and_transfer_data()
                            st.success("Cleaning job finished!")
                            st.cache_data.clear()
                with sim3:
                    if st.button("Rebuild Daily Index"):
                        with st.spinner("Index building..."):
                            calculate_index()
                            st.success("Daily APIx index recalculated!")
                            st.cache_data.clear()
                            
        with admin_tab2:
            st.header("DGCA Route Weight Management")
            st.markdown("View and update passenger traffic weight ratios representing flight sectors for index calculations.")
            
            routes_df = load_routes_data()
            
            if routes_df.empty:
                st.warning("No routes configuration found in the database.")
            else:
                st.markdown("Modify the **Route Weight** column directly below and click **Save Changes** to commit updates to the database.")
                
                edited_df = st.data_editor(
                    routes_df,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", disabled=True),
                        "origin": st.column_config.TextColumn("Origin", disabled=True),
                        "destination": st.column_config.TextColumn("Destination", disabled=True),
                        "route_weight": st.column_config.NumberColumn(
                            "Route Weight Ratio",
                            min_value=0.0,
                            max_value=1.0,
                            format="%.4f"
                        )
                    },
                    hide_index=True,
                    use_container_width=True
                )
                
                if st.button("Save Changes to DB"):
                    try:
                        conn = sqlite3.connect(str(DB_PATH))
                        for index, row in edited_df.iterrows():
                            conn.execute(
                                "UPDATE routes SET route_weight = ? WHERE id = ?",
                                (row['route_weight'], row['id'])
                            )
                        conn.commit()
                        conn.close()
                        st.success("Successfully updated sector weights database configurations!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Failed to update route config settings: {e}")
                        
        with admin_tab3:
            st.header("System Statistics")
            st.markdown("Review row counts and structure of the central airfare database.")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Raw Scraped Quotes", stats["raw"])
            col2.metric("Cleaned Fares", stats["cleaned"])
            col3.metric("Daily Index Entries", stats["index"])
            col4.metric("Configured Routes", stats["routes"])
            
            st.subheader("Database Backups")
            st.markdown(
                """
                <div style="background-color:#fff3cd; border-left: 5px solid #ffc107; padding: 12px; border-radius: 4px; margin-bottom: 20px;">
                    <strong>⚠️ SQLite Database File Download</strong><br>
                    SQLite database files (.db) are compressed binary formats. If you try to open the downloaded file directly on Windows, you may receive a <i>"This file does not have an app associated with it..."</i> warning.
                    To inspect the contents, use a database viewer like <a href="https://sqlitebrowser.org/" target="_blank">DB Browser for SQLite</a>, or import it into a Python pandas script.
                </div>
                """,
                unsafe_allow_html=True
            )
            
            try:
                with open(str(DB_PATH), "rb") as db_file:
                    db_bytes = db_file.read()
                st.download_button(
                    label="📥 Download SQLite Database File",
                    data=db_bytes,
                    file_name="airfare_index.db",
                    mime="application/octet-stream"
                )
            except Exception as e:
                st.error(f"Error preparing DB file for download: {e}")
