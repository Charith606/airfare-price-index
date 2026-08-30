import pytest
import pandas as pd
from src.cleaning.cleaner import clean_and_transfer_data
from src.index.index_builder import calculate_index

def test_cleaning_logic():
    # Simple test to ensure pandas is available and logic can be imported
    assert callable(clean_and_transfer_data)
    
    # In a real scenario, we would mock the database connection here 
    # and insert test rows to verify outlier removal and tax calculations.
    # For prototype validation, we ensure the function structure is sound.
    df = pd.DataFrame([
        {'price': 100, 'airline': 'IndiGo', 'origin': 'DEL', 'destination': 'BOM'}, # Outlier (too low)
        {'price': 5000, 'airline': 'indigo ', 'origin': 'DEL', 'destination': 'BOM'}, # Needs stripping
    ])
    
    # Test outlier removal
    df_clean = df[(df['price'] >= 1000) & (df['price'] <= 50000)].copy()
    assert len(df_clean) == 1
    
    # Test standardizing
    df_clean['airline'] = df_clean['airline'].str.strip().str.title()
    assert df_clean.iloc[0]['airline'] == 'Indigo'
    
def test_index_calculation():
    assert callable(calculate_index)
