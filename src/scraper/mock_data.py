import sqlite3
import random
from datetime import date, timedelta
from src.config.database import get_connection

def generate_mock_data():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Generate 35 days of data for backtesting requirement
    routes = [("DEL", "BOM"), ("DEL", "BLR"), ("BOM", "BLR"), ("DEL", "CCU"), ("BLR", "HYD")]
    airlines = ["IndiGo", "Air India", "Akasa Air", "SpiceJet", "Air India Express"]
    windows = [1, 7, 15, 30, 45]
    
    records = []
    for i in range(35):
        coll_date = date.today() - timedelta(days=34-i)
        
        for origin, dest in routes:
            for window in windows:
                travel_date = coll_date + timedelta(days=window)
                airline = random.choice(airlines)
                
                # Base price mock logic
                base = random.randint(3000, 5000)
                # Price increases closer to departure
                multiplier = 1 + (45 - window) * 0.05
                price = int(base * multiplier)
                
                records.append((coll_date.isoformat(), travel_date.isoformat(), origin, dest, airline, price, 'INR', '10:00', 'quoted_fare', window))
                
    cursor.executemany("""
        INSERT INTO raw_quotes 
        (collection_date, travel_date, origin, destination, airline, price, currency, departure_time, fare_type, advance_days)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, records)
                
    conn.commit()
    conn.close()
    print("Mock data generated.")

if __name__ == "__main__":
    generate_mock_data()
