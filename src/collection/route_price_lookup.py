from __future__ import annotations

import argparse
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from src.api.ignav_client import search_ignav
from src.collection.itinerary_extractor import extract_itineraries


USD_TO_INR_RATE = Decimal(os.getenv("USD_TO_INR_RATE", "84"))


def ask_airport(prompt: str) -> str:
    value = input(prompt).strip().upper()
    if len(value) != 3 or not value.isalpha():
        raise ValueError("Use a three-letter IATA airport code, such as DEL or BOM.")
    return value


def fare_value(record: dict) -> Decimal:
    try:
        return Decimal(str(record.get("price") or "0"))
    except InvalidOperation:
        return Decimal("0")


def display_price(record: dict) -> str:
    price = fare_value(record)
    currency = str(record.get("currency") or "").upper()
    if currency == "USD":
        inr = (price * USD_TO_INR_RATE).quantize(Decimal("0.01"))
        return f"INR {inr:.2f}"
    return f"{currency or 'Unknown currency'} {price:.2f}"


def print_itinerary(record: dict, number: int) -> None:
    print(f"  {number}. {display_price(record)}")
    print(
        f"     {record.get('airline') or 'Unknown airline'} | "
        f"Flights: {record.get('flight_numbers') or 'not provided'} | "
        f"Stops: {record.get('stops', 'not provided')}"
    )
    print(
        f"     {record.get('departure_airport')} {record.get('departure_time')}"
        f" -> {record.get('arrival_airport')} {record.get('arrival_time')} | "
        f"Duration: {record.get('duration_minutes')} minutes"
    )


def collect_window(origin: str, destination: str, advance_days: int, max_results: int) -> None:
    travel_date = date.today() + timedelta(days=advance_days)
    print("\n" + "=" * 64)
    print(f"{origin} -> {destination} | T+{advance_days} | Travel date: {travel_date}")

    try:
        response = search_ignav(origin, destination, travel_date.isoformat())
        records = extract_itineraries(
            response,
            collection_date=date.today().isoformat(),
            advance_days=advance_days,
            travel_date=travel_date.isoformat(),
            origin=origin,
            destination=destination,
        )
    except Exception as exc:
        print(f"API request failed: {exc}")
        return

    usable = [record for record in records if fare_value(record) > 0]
    usable.sort(key=fare_value)
    if not usable:
        print("No priced itineraries were returned.")
        return

    print(f"Lowest fare: {display_price(usable[0])}")
    print(f"Showing {min(len(usable), max_results)} of {len(usable)} priced itineraries:")
    for number, record in enumerate(usable[:max_results], start=1):
        print_itinerary(record, number)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Look up one-way airfare prices from IGNAV by booking window."
    )
    parser.add_argument("--origin", help="Origin IATA code, e.g. DEL")
    parser.add_argument("--destination", help="Destination IATA code, e.g. BOM")
    parser.add_argument(
        "--windows",
        type=int,
        nargs="+",
        default=[1, 7, 15, 30, 45],
        help="Advance booking windows in days; default: 1 7 15 30 45",
    )
    parser.add_argument(
        "--results",
        type=int,
        default=3,
        help="Maximum itineraries to display for each window; default: 3",
    )
    args = parser.parse_args()

    origin = (args.origin or ask_airport("Origin IATA code (for example DEL): ")).strip().upper()
    destination = (args.destination or ask_airport("Destination IATA code (for example BOM): ")).strip().upper()
    if len(origin) != 3 or len(destination) != 3 or not origin.isalpha() or not destination.isalpha():
        raise ValueError("Origin and destination must be three-letter IATA airport codes.")
    if origin == destination:
        raise ValueError("Origin and destination must be different.")
    if any(window < 1 for window in args.windows):
        raise ValueError("Each booking window must be at least 1 day.")
    if args.results < 1:
        raise ValueError("--results must be at least 1.")

    print(f"Searching IGNAV for {origin} -> {destination}...")
    for window in args.windows:
        collect_window(origin, destination, window, args.results)


if __name__ == "__main__":
    main()
