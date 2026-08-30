import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# IGNAV API configuration
IGNAV_API_KEY = os.getenv("IGNAV_API_KEY")

if not IGNAV_API_KEY:
    raise ValueError("IGNAV_API_KEY not found in .env")