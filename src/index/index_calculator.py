from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from src.config.database import get_connection


HUNDRED = Decimal("100")
MONEY = Decimal("0.01")


def get_route_observations(cursor):
    """Return one average fare per date, route and booking window.

    All data is read from airfare_quotes.  No database tables or rows are changed.
    """
    cursor.execute(
        """
        SELECT
            q.collection_date,
            q.route_id,
            q.booking_window,
            AVG(q.total_fare) AS average_fare,
            COUNT(*) AS quote_count,
            r.origin,
            r.destination,
            r.route_weight
        FROM airfare_quotes AS q
        INNER JOIN routes AS r ON r.route_id = q.route_id
        WHERE q.total_fare IS NOT NULL
          AND (q.availability IS NULL
               OR LOWER(TRIM(q.availability)) NOT IN ('sold out', 'unavailable'))
        GROUP BY
            q.collection_date,
            q.route_id,
            q.booking_window,
            r.origin,
            r.destination,
            r.route_weight
        ORDER BY q.collection_date, q.route_id, q.booking_window
        """
    )
    return cursor.fetchall()


def calculate_index(rows):
    """Calculate a base-100 route and weighted composite index.

    For each route/booking-window pair, the first available collection date is
    the base (100). Later quotes are compared to that base. This lets the
    prototype work without changing the existing database schema.
    """
    baselines: dict[tuple[int, str], Decimal] = {}
    by_date: dict[date, list[dict]] = defaultdict(list)

    for row in rows:
        collection_date, route_id, booking_window, average_fare, quote_count, origin, destination, route_weight = row
        key = (int(route_id), str(booking_window))
        average_fare = Decimal(str(average_fare))
        route_weight = Decimal(str(route_weight or 0))

        if key not in baselines:
            baselines[key] = average_fare

        route_index = (average_fare / baselines[key] * HUNDRED).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        by_date[collection_date].append(
            {
                "route": f"{origin}-{destination}",
                "window": str(booking_window),
                "average_fare": average_fare.quantize(MONEY),
                "quote_count": int(quote_count),
                "weight": route_weight,
                "route_index": route_index,
            }
        )

    reports = []
    for collection_date, route_rows in sorted(by_date.items()):
        usable = [row for row in route_rows if row["weight"] > 0]
        total_weight = sum((row["weight"] for row in usable), Decimal("0"))
        weighted_index = None
        if total_weight:
            weighted_index = (
                sum((row["route_index"] * row["weight"] for row in usable), Decimal("0"))
                / total_weight
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        reports.append(
            {
                "collection_date": collection_date,
                "index": weighted_index,
                "weight_coverage": (total_weight * HUNDRED).quantize(Decimal("0.01")),
                "routes": route_rows,
            }
        )
    return reports


def print_report(reports, only_date: date | None):
    selected = [report for report in reports if only_date is None or report["collection_date"] == only_date]
    if not selected:
        print("No quote data found for the requested collection date.")
        return

    for report in selected:
        index_display = report["index"] if report["index"] is not None else "not available"
        print(f"\nAirfare Price Index - {report['collection_date']}")
        print(f"Index: {index_display} (base = 100)")
        print(f"Route-weight coverage: {report['weight_coverage']}%")
        print("Route details:")
        for row in report["routes"]:
            print(
                f"  {row['route']} | window {row['window']} | "
                f"INR {row['average_fare']} | route index {row['route_index']} | "
                f"quotes {row['quote_count']}"
            )


def main():
    parser = argparse.ArgumentParser(description="Calculate the Airfare Price Index from MySQL quotes.")
    parser.add_argument("--date", type=date.fromisoformat, help="Collection date to report, e.g. 2026-08-30.")
    args = parser.parse_args()

    connection = get_connection()
    cursor = connection.cursor()
    try:
        reports = calculate_index(get_route_observations(cursor))
        print_report(reports, args.date)
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
