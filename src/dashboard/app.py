import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import os
import sys
import asyncio
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
            # Test opening a headless browser
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        import subprocess
        # Run playwright install inside the streamlit container
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

# Cache functions for static data to keep UI snappy
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

# Render flight details as a clean, styled card (instead of raw table)
def render_flight_card(flight, is_cheapest=False):
    # CSS styling for container cards
    card_bg = "#d4edda" if is_cheapest else "#f8f9fa"
    border_color = "#28a745" if is_cheapest else "#e3e6f0"
    badge_html = '<span style="background-color:#28a745; color:white; padding:4px 8px; border-radius:4px; font-size:12px; font-weight:bold; margin-bottom:8px; display:inline-block;">CHEAPEST FLIGHT</span>' if is_cheapest else ''
    
    # Format dates/times
    departure_time = flight.get('departure_time', 'N/A')
    arrival_time = flight.get('arrival_time', 'N/A')
    
    # Strip dates if they contain T timestamps
    if 'T' in str(departure_time):
        departure_time = str(departure_time).split('T')[1][:5]
    if 'T' in str(arrival_time):
        arrival_time = str(arrival_time).split('T')[1][:5]
        
    duration = flight.get('duration_minutes', flight.get('duration', 'N/A'))
    if duration != 'N/A':
        hours = int(duration) // 60
        mins = int(duration) % 60
        duration_str = f"{hours}h {mins}m"
    else:
        duration_str = "N/A"
        
    stops = flight.get('stops', 0)
    stops_str = "Direct" if int(stops) == 0 else f"{stops} Stop(s)"
    
    airline = flight.get('airline', 'Unknown Airline')
    price = flight.get('total_fare', flight.get('price', 0))
    currency = flight.get('currency', 'INR')
    
    # Convert USD to INR representation
    if currency == 'USD':
        price = float(price) * 84
        currency = 'INR'
        
    price_formatted = f"₹{float(price):,.2f}"
    
    st.markdown(
        f"""
        <div style="background-color:{card_bg}; border: 1.5px solid {border_color}; border-radius: 8px; padding: 16px; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
            {badge_html}
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
                <!-- Airline Branding -->
                <div style="flex: 1; min-width: 150px;">
                    <h4 style="margin: 0; color: #333;">✈️ {airline}</h4>
                    <span style="font-size: 13px; color: #666;">Flight No: {flight.get('flight_numbers', flight.get('flight_number', 'N/A'))}</span>
                </div>
                <!-- Times & Stops -->
                <div style="flex: 2; min-width: 250px; text-align: center; display: flex; justify-content: space-around; align-items: center;">
                    <div>
                        <h3 style="margin: 0; color: #222;">{departure_time}</h3>
                        <span style="font-size: 12px; color: #888;">{flight.get('origin', 'DEP')}</span>
                    </div>
                    <div style="border-bottom: 2px dashed #bbb; flex-grow: 0.5; position: relative; margin: 0 10px;">
                        <span style="font-size: 11px; color: #555; background-color: {card_bg}; padding: 0 4px; position: absolute; top: -18px; left: 50%; transform: translateX(-50%); white-space: nowrap;">{duration_str}</span>
                        <span style="font-size: 11px; color: #777; background-color: {card_bg}; padding: 0 4px; position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%); white-space: nowrap;">{stops_str}</span>
                    </div>
                    <div>
                        <h3 style="margin: 0; color: #222;">{arrival_time}</h3>
                        <span style="font-size: 12px; color: #888;">{flight.get('destination', 'ARR')}</span>
                    </div>
                </div>
                <!-- Pricing details -->
                <div style="flex: 1; min-width: 120px; text-align: right;">
                    <h2 style="margin: 0; color: #2e7d32; font-weight: bold;">{price_formatted}</h2>
                    <span style="font-size: 12px; color: #555;">Cabin: {flight.get('fare_class', flight.get('cabin_class', 'Economy')).title()}</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

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
        
        search_mode = st.radio(
            "Select Search Source", 
            ["📂 Search Historical Data (Cached SQLite DB)", "⚡ Search Live Real-time Prices (Active Scraper/API)"],
            horizontal=True
        )
        
        # 📂 HISTORICAL DB MODE
        if search_mode == "📂 Search Historical Data (Cached SQLite DB)":
            if fares_df.empty:
                st.warning("No historical database available to search.")
            else:
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    origins = sorted(fares_df['origin'].unique())
                    origin_select = st.selectbox("Origin Airport", ["All"] + origins)
                    
                with col2:
                    destinations = sorted(fares_df['destination'].unique())
                    dest_select = st.selectbox("Destination Airport", ["All"] + destinations)
                    
                with col3:
                    airlines = sorted(fares_df['airline'].unique())
                    airline_select = st.selectbox("Airline", ["All"] + airlines)
                    
                # Filtering database logic
                filtered_df = fares_df.copy()
                if origin_select != "All":
                    filtered_df = filtered_df[filtered_df['origin'] == origin_select]
                if dest_select != "All":
                    filtered_df = filtered_df[filtered_df['destination'] == dest_select]
                if airline_select != "All":
                    filtered_df = filtered_df[filtered_df['airline'] == airline_select]
                
                # Sort flights by price
                filtered_df = filtered_df.sort_values(by="total_fare")
                
                st.subheader(f"Search Results ({len(filtered_df)} matches)")
                
                if filtered_df.empty:
                    st.info("No matching flights found in historical logs.")
                else:
                    # Render with custom cards
                    for index, row in filtered_df.reset_index(drop=True).iterrows():
                        render_flight_card(row.to_dict(), is_cheapest=(index == 0))
                        
        # ⚡ LIVE REAL-TIME DATA MODE
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                origin_val = st.text_input("Origin Airport IATA (e.g., DEL)", value="DEL").upper()
            with col2:
                dest_val = st.text_input("Destination Airport IATA (e.g., BOM)", value="BOM").upper()
            with col3:
                travel_date_val = st.date_input("Travel Date", value=date.today() + pd.Timedelta(days=7))
                
            live_source = st.selectbox(
                "Select Live Data Protocol", 
                ["🌐 Live Web Scraper (Cleartrip / Playwright)", "🔌 Live IGNav API Portal"]
            )
            
            if st.button("🔍 Search Real-time Flights"):
                if len(origin_val) != 3 or len(dest_val) != 3:
                    st.error("Please enter a valid 3-letter IATA code for origin and destination.")
                elif origin_val == dest_val:
                    st.error("Origin and destination airports must be different.")
                else:
                    with st.spinner("Connecting to live server and fetching real-time airline flight charges..."):
                        results = []
                        error_msg = ""
                        
                        # Use Playwright Scraper
                        if live_source == "🌐 Live Web Scraper (Cleartrip / Playwright)":
                            try:
                                scraper = OTAScraper(headless=True)
                                # Playwright runs inside an async event loop
                                results = asyncio.run(scraper.scrape_route(origin_val, dest_val, travel_date_val))
                            except Exception as e:
                                error_msg = f"Web Scraper exception occurred: {e}"
                                
                        # Use IGNav API
                        else:
                            from src.config.settings import IGNAV_API_KEY
                            if not IGNAV_API_KEY:
                                st.warning("⚠️ IGNAV_API_KEY environment variable is not configured. To query the live API portal, configure `IGNAV_API_KEY` in Streamlit's secrets settings.")
                                # Fall back to reading local sample response to provide high-fidelity showcase
                                try:
                                    import json
                                    sample_path = Path(__file__).resolve().parents[2] / "data" / "raw" / "sample_ignav_response.json"
                                    with open(sample_path, "r") as f:
                                        payload = json.load(f)
                                    results = extract_itineraries(
                                        payload,
                                        collection_date=date.today().isoformat(),
                                        advance_days=(travel_date_val - date.today()).days,
                                        travel_date=travel_date_val.isoformat(),
                                        origin=origin_val,
                                        destination=dest_val
                                    )
                                    st.info("💡 Displaying sandbox simulation results below (mock API response).")
                                except Exception as sample_err:
                                    error_msg = f"Failed to load fallback sample data: {sample_err}"
                            else:
                                try:
                                    # Call the real API
                                    payload = search_ignav(origin_val, dest_val, travel_date_val.isoformat())
                                    results = extract_itineraries(
                                        payload,
                                        collection_date=date.today().isoformat(),
                                        advance_days=(travel_date_val - date.today()).days,
                                        travel_date=travel_date_val.isoformat(),
                                        origin=origin_val,
                                        destination=dest_val
                                    )
                                except Exception as api_err:
                                    error_msg = f"IGNav API Exception: {api_err}"
                                    
                        # Display Results
                        if error_msg:
                            st.error(f"Failed to fetch live real-time pricing: {error_msg}")
                        elif not results:
                            st.info("No active flights were returned for this route and date by the live portal.")
                        else:
                            # Sort by price
                            results = sorted(results, key=lambda x: float(x.get('price', x.get('total_fare', 0))))
                            
                            st.subheader(f"Cheapest Live Flight Tickets Found ({len(results)} flights)")
                            
                            for index, flight in enumerate(results):
                                render_flight_card(flight, is_cheapest=(index == 0))

# ----------------- 🔐 MOSPI AUTHORIZED ADMIN PORTAL -----------------
else:
    st.title("🔐 MoSPI Authorized Administrator Portal")
    
    # Simple Passcode Protection
    password = st.text_input("Enter Admin Passcode to Authenticate:", type="password")
    
    if password == "admin123":
        st.success("Authorized Access Granted")
        
        stats = get_stats()
        
        # Tabs for Admin tasks
        admin_tab1, admin_tab2, admin_tab3 = st.tabs([
            "⚙️ Scraper & Pipeline Controls", 
            "🛣️ DGCA Routes & Weights Configuration",
            "📊 System Statistics & DB Download"
        ])
        
        with admin_tab1:
            st.header("Scraper Pipeline Dashboard")
            st.markdown("Manually run or simulate scraping, data cleaning, and index recalculation.")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.subheader("1. Generate Scraping Data")
                st.info("Simulate live scraping. Creates raw index flight quotes and inserts them into `raw_quotes` table.")
                if st.button("Run Web Scraper simulation"):
                    with st.spinner("Generating mock airfare prices..."):
                        try:
                            generate_mock_data()
                            st.success("Successfully generated and saved new raw scraping quotes!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Error executing scraper: {e}")
                            
            with col2:
                st.subheader("2. Run Data Cleaner")
                st.info("Runs the processing logic: removes outlier pricing and performs cleaning on new raw data.")
                if st.button("Run Clean & Transfer"):
                    with st.spinner("Processing raw pricing data..."):
                        try:
                            clean_and_transfer_data()
                            st.success("Data cleaning step completed successfully!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Error executing cleaner: {e}")
                            
            with col3:
                st.subheader("3. Rebuild Index")
                st.info("Computes the Airfare Price Index (APIx) using current route weights and cleaned flight data.")
                if st.button("Recalculate APIx"):
                    with st.spinner("Rebuilding daily price indices..."):
                        try:
                            calculate_index()
                            st.success("Price index calculations updated successfully!")
                            st.cache_data.clear()
                        except Exception as e:
                            st.error(f"Error building index: {e}")
                            
        with admin_tab2:
            st.header("DGCA Route Weight Management")
            st.markdown("View and update passenger traffic weight ratios representing flight sectors for index calculations.")
            
            routes_df = load_routes_data()
            
            if routes_df.empty:
                st.warning("No routes configuration found in the database.")
            else:
                st.markdown("Modify the **Route Weight** column directly below and click **Save Changes** to commit updates to the database.")
                
                # Interactive data editor
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
                
                # Button to save changes
                if st.button("Save Changes to DB"):
                    try:
                        conn = sqlite3.connect(str(DB_PATH))
                        # Save back updated values
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
            st.markdown("You can download the full SQLite Database below:")
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
                
    elif password != "":
        st.error("Invalid passcode. Please enter the correct Administrator credentials.")
