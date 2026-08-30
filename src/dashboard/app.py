import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import os

# Set page config
st.set_page_config(page_title="Real-time Airfare Price Index (APIx)", layout="wide")

st.title("Real-time Airfare Price Index (APIx)")
st.markdown("Augmentation of the Consumer Price Index (CPI) using automated web scraping.")

# Database path
DB_PATH = Path(__file__).resolve().parents[2] / 'data' / 'airfare_index.db'

from src.config.database import get_sqlalchemy_engine

def load_data():
    engine = get_sqlalchemy_engine()
    fares_df = pd.read_sql_query("SELECT * FROM cleaned_fares", engine)
    index_df = pd.read_sql_query("SELECT * FROM price_index WHERE frequency='daily'", engine)
    
    # lowercase columns because Snowflake returns them uppercase
    fares_df.columns = fares_df.columns.str.lower()
    index_df.columns = index_df.columns.str.lower()
    
    return fares_df, index_df

fares_df, index_df = load_data()

if index_df.empty:
    st.warning("No index data available yet. Please run the scraper and index builder.")
else:
    st.header("Airfare Price Index (APIx) Trend vs DGCA Baseline")
    
    # Add a mock DGCA baseline for comparison
    index_df['DGCA_Baseline'] = 100 + (index_df['index_value'] - 100) * 0.5 # A smoother, delayed version representing manual collection
    
    chart_data = index_df.set_index('index_date')[['index_value', 'DGCA_Baseline']]
    chart_data.columns = ['Real-time APIx', 'DGCA Manual Baseline (Simulated)']
    
    st.line_chart(data=chart_data)

if not fares_df.empty:
    st.header("Sector-wise Analysis")
    
    # Create Route column
    fares_df['Route'] = fares_df['origin'] + " - " + fares_df['destination']
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Price Trends by Route")
        route_trends = fares_df.groupby(['collection_date', 'Route'])['total_fare'].mean().unstack()
        st.line_chart(route_trends)
        
    with col2:
        st.subheader("Lead-Time Elasticity")
        st.markdown("Average price based on advance purchase window.")
        elasticity = fares_df.groupby(['advance_days'])['total_fare'].mean().reset_index()
        st.bar_chart(elasticity.set_index('advance_days'))
        
    st.header("Raw Cleaned Fares Data")
    st.dataframe(fares_df.head(100))
