import requests

from src.config.settings import IGNAV_API_KEY


# IGNAV API endpoint
IGNAV_URL = "https://ignav.com/api/fares/one-way"


def search_ignav(origin, destination, travel_date):
    """
    Search IGNAV for one-way airfare between two airports.

    Parameters:
        origin (str): Origin airport IATA code, e.g. DEL
        destination (str): Destination airport IATA code, e.g. BOM
        travel_date (str): Travel date in YYYY-MM-DD format

    Returns:
        dict: JSON response from IGNAV API
    """

    headers = {
        "X-Api-Key": IGNAV_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "origin": origin,
        "destination": destination,
        "departure_date": travel_date,
        "adults": 1,
        "cabin_class": "economy"
    }

    response = requests.post(
        IGNAV_URL,
        headers=headers,
        json=payload,
        timeout=60
    )

    print("HTTP status:", response.status_code)

    response.raise_for_status()

    return response.json()