import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import os
import sys

# Ensure project root is on sys.path so src imports work
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.scraper.mock_data import generate_mock_data
from src.cleaning.cleaner import clean_and_transfer_data
from src.index.index_builder import calculate_index

# Set page config
st.set_page_config(page_title="Real-time Airfare Price Index (APIx)", layout="wide")

# Database path
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'airfare_index.db'

# Cache functions to keep performance fast
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
    
    # Load and display data
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
        st.markdown("Search and compare specific historical flight ticket prices across airline routes.")
        
        if fares_df.empty:
            st.warning("No fare database available to search.")
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
                
            st.subheader(f"Search Results ({len(filtered_df)} matches)")
            st.dataframe(filtered_df.rename(columns={
                'collection_date': 'Scrape Date',
                'travel_date': 'Travel Date',
                'origin': 'From',
                'destination': 'To',
                'airline': 'Carrier',
                'base_fare': 'Base Fare (INR)',
                'taxes': 'Taxes/Fees (INR)',
                'total_fare': 'Total Price (INR)',
                'advance_days': 'Booking Lead Window (Days)'
            }).drop(columns=['id', 'quote_id', 'route'], errors='ignore'), use_container_width=True)

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
