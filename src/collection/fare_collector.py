
import csv
from pathlib import Path




from datetime import date, timedelta

from src.api.ignav_client import search_ignav


# Advance-purchase windows required by the problem statement
ADVANCE_WINDOWS = [1, 7, 15, 30, 45]


def collect_fares(origin, destination):
    """
    Collect and extract airfare records for:

        T+1
        T+7
        T+15
        T+30
        T+45

    Returns:
        list of dictionaries
    """

    today = date.today()

    all_records = []

    for advance_days in ADVANCE_WINDOWS:

        travel_date = (
            today + timedelta(days=advance_days)
        ).strftime("%Y-%m-%d")

        print("\n" + "=" * 60)
        print(f"Route: {origin} → {destination}")
        print(f"Advance window: T+{advance_days}")
        print(f"Travel date: {travel_date}")

        try:

            result = search_ignav(
                origin,
                destination,
                travel_date
            )

            itineraries = result.get(
                "itineraries",
                []
            )

            print(
                "Itineraries returned:",
                len(itineraries)
            )

            # -----------------------------------------
            # Extract each itinerary
            # -----------------------------------------

            for itinerary in itineraries:

                price = itinerary.get(
                    "price",
                    {}
                )

                outbound = itinerary.get(
                    "outbound",
                    {}
                )

                segments = outbound.get(
                    "segments",
                    []
                )

                # -------------------------------------
                # Extract each flight segment
                # -------------------------------------

                for segment in segments:

                    record = {

                        "collection_date":
                            str(today),

                        "advance_days":
                            advance_days,

                        "travel_date":
                            travel_date,

                        "origin":
                            origin,

                        "destination":
                            destination,

                        "airline":
                            outbound.get(
                                "carrier"
                            ),

                        "carrier_code":
                            segment.get(
                                "marketing_carrier_code"
                            ),

                        "flight_number":
                            segment.get(
                                "flight_number"
                            ),

                        "departure_airport":
                            segment.get(
                                "departure_airport"
                            ),

                        "arrival_airport":
                            segment.get(
                                "arrival_airport"
                            ),

                        "departure_time":
                            segment.get(
                                "departure_time_local"
                            ),

                        "arrival_time":
                            segment.get(
                                "arrival_time_local"
                            ),

                        "duration_minutes":
                            segment.get(
                                "duration_minutes"
                            ),

                        "aircraft":
                            segment.get(
                                "aircraft"
                            ),

                        "price":
                            price.get(
                                "amount"
                            ),

                        "currency":
                            price.get(
                                "currency"
                            ),

                        "price_status":
                            price.get(
                                "status"
                            ),

                        "cabin_class":
                            itinerary.get(
                                "cabin_class"
                            ),

                        "self_transfer":
                            itinerary.get(
                                "requires_self_transfer"
                            ),

                        "ignav_id":
                            itinerary.get(
                                "ignav_id"
                            )
                    }

                    all_records.append(record)

            print(
                "Extracted records:",
                len([
                    r for r in all_records
                    if r["advance_days"] == advance_days
                ])
            )

        except Exception as e:

            print(
                f"Error for T+{advance_days}: {e}"
            )

    print("\n" + "=" * 60)
    print("TOTAL EXTRACTED RECORDS:", len(all_records))
    print("=" * 60)

    return all_records





def save_raw_fares(records):
    """
    Save itinerary-level airfare records to data/raw/airfare_raw.csv.
    """

    if not records:
        print("No records to save.")
        return

    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "airfare_raw.csv"

    fieldnames = [
        "collection_date",
        "advance_days",
        "travel_date",
        "origin",
        "destination",
        "airline",
        "carrier_codes",
        "flight_numbers",
        "departure_airport",
        "arrival_airport",
        "departure_time",
        "arrival_time",
        "duration_minutes",
        "number_of_segments",
        "stops",
        "price",
        "currency",
        "price_status",
        "cabin_class",
        "self_transfer",
        "ignav_id"
    ]

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()
        writer.writerows(records)

    print("\n" + "=" * 60)
    print("RAW DATA SAVED")
    print("=" * 60)
    print(f"File: {output_file}")
    print(f"Records saved: {len(records)}")