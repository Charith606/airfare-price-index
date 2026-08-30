import os
from dotenv import load_dotenv
import snowflake.connector

load_dotenv()

def get_connection():
    """Return a connection to the Snowflake database."""
    conn = snowflake.connector.connect(
        user=os.getenv('SNOWFLAKE_USER'),
        password=os.getenv('SNOWFLAKE_PASSWORD'),
        account=os.getenv('SNOWFLAKE_ACCOUNT'),
        warehouse=os.getenv('SNOWFLAKE_WAREHOUSE'),
        database=os.getenv('SNOWFLAKE_DATABASE'),
        schema=os.getenv('SNOWFLAKE_SCHEMA')
    )
    return conn

def get_sqlalchemy_engine():
    """Return a SQLAlchemy engine for Pandas integration."""
    from sqlalchemy import create_engine
    
    user = os.getenv('SNOWFLAKE_USER')
    password = os.getenv('SNOWFLAKE_PASSWORD')
    account = os.getenv('SNOWFLAKE_ACCOUNT')
    warehouse = os.getenv('SNOWFLAKE_WAREHOUSE')
    database = os.getenv('SNOWFLAKE_DATABASE')
    schema = os.getenv('SNOWFLAKE_SCHEMA')
    
    # URL format: snowflake://<user_login_name>:<password>@<account_identifier>/<database_name>/<schema_name>?warehouse=<warehouse_name>
    connection_string = f"snowflake://{user}:{password}@{account}/{database}/{schema}?warehouse={warehouse}"
    return create_engine(connection_string)

def init_db():
    """Initialize the database schema in Snowflake."""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Raw Quotes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS raw_quotes (
                id NUMBER AUTOINCREMENT,
                collection_date VARCHAR,
                travel_date VARCHAR,
                origin VARCHAR,
                destination VARCHAR,
                airline VARCHAR,
                price FLOAT,
                currency VARCHAR,
                departure_time VARCHAR,
                fare_type VARCHAR,
                advance_days NUMBER
            )
        """)
        
        # Routes Table for Index Weights
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id NUMBER AUTOINCREMENT,
                origin VARCHAR,
                destination VARCHAR,
                route_weight FLOAT
            )
        """)
        
        # Cleaned Fares Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cleaned_fares (
                id NUMBER AUTOINCREMENT,
                quote_id NUMBER,
                collection_date VARCHAR,
                travel_date VARCHAR,
                origin VARCHAR,
                destination VARCHAR,
                airline VARCHAR,
                base_fare FLOAT,
                taxes FLOAT,
                total_fare FLOAT,
                advance_days NUMBER
            )
        """)
        
        # Index Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_index (
                id NUMBER AUTOINCREMENT,
                index_date VARCHAR,
                frequency VARCHAR,
                index_value FLOAT
            )
        """)
        
        # Insert some dummy routes if empty
        cursor.execute("SELECT COUNT(*) FROM routes")
        result = cursor.fetchone()
        if result and result[0] == 0:
            cursor.execute("""
                INSERT INTO routes (origin, destination, route_weight) 
                VALUES ('DEL', 'BOM', 0.3),
                       ('DEL', 'BLR', 0.25),
                       ('BOM', 'BLR', 0.2),
                       ('DEL', 'CCU', 0.15),
                       ('BLR', 'HYD', 0.1)
            """)
            
        print("Snowflake Database schema initialized successfully.")
    except Exception as e:
        print(f"Error initializing Snowflake: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    init_db()