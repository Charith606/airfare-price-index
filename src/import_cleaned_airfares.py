from __future__ import annotations

import argparse
import csv
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from config.database import get_connection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data" / "cleaned" / "airfare_cleaned.csv"
USD_TO_INR_RATE = Decimal(os.getenv("USD_TO_INR_RATE", "84"))
SOURCE_NAME = "IGNAV"


def text(value: Any) -> str:
    return str(value or "").strip()


def first_value(row: dict[str, str], *names: str, default: str = "") -> str:
    normalized = {key.strip().lower(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name.lower())
        if text(value):
            return text(value)
    return default


def parse_date(value: str, field_name: str) -> date:
    value = text(value)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Invalid {field_name}: {value!r}")


def parse_decimal(value: str, field_name: str) -> Decimal:
    try:
        return Decimal(text(value).replace(",", "").replace("$", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc


def convert_to_inr(price: Decimal, currency: str) -> Decimal:
    currency = text(currency).upper()
    if currency == "INR":
        return price.quantize(Decimal("0.01"))
    if currency == "USD":
        if USD_TO_INR_RATE <= 0:
            raise ValueError("USD_TO_INR_RATE must be greater than zero")
        return (price * USD_TO_INR_RATE).quantize(Decimal("0.01"))
    raise ValueError(f"Unsupported currency {currency!r}. Expected USD or INR.")


def parse_int(value: str, field_name: str) -> int:
    try:
        return int(text(value).lower().replace("t+", ""))
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value!r}") from exc


def table_columns(cursor, table_name: str) -> set[str]:
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (table_name,),
    )
    return {row[0].lower() for row in cursor.fetchall()}


def lookup_route_id(cursor, origin: str, destination: str) -> int:
    columns = table_columns(cursor, "routes")
    if {"origin", "destination"}.issubset(columns):
        cursor.execute(
            """
            SELECT route_id FROM routes
            WHERE UPPER(TRIM(origin)) = UPPER(TRIM(%s))
              AND UPPER(TRIM(destination)) = UPPER(TRIM(%s))
            ORDER BY route_id LIMIT 1
            """,
            (origin, destination),
        )
    elif "route_code" in columns:
        cursor.execute(
            """
            SELECT route_id FROM routes
            WHERE UPPER(TRIM(route_code)) = UPPER(%s)
            ORDER BY route_id LIMIT 1
            """,
            (f"{origin}-{destination}",),
        )
    else:
        raise RuntimeError("routes needs origin/destination columns or route_code")
    result = cursor.fetchone()
    if not result:
        raise LookupError(f"No route found for {origin}-{destination}")
    return int(result[0])


def lookup_airline_id(cursor, airline_name: str) -> int:
    cursor.execute(
        """
        SELECT airline_id FROM airlines
        WHERE LOWER(TRIM(airline_name)) = LOWER(TRIM(%s))
        ORDER BY airline_id LIMIT 1
        """,
        (airline_name,),
    )
    result = cursor.fetchone()
    if not result:
        raise LookupError(f"No airline found for {airline_name!r}")
    return int(result[0])


def lookup_source_id(cursor, source_name: str) -> int:
    cursor.execute(
        """
        SELECT source_id FROM sources
        WHERE LOWER(TRIM(source_name)) = LOWER(TRIM(%s))
        ORDER BY source_id LIMIT 1
        """,
        (source_name,),
    )
    result = cursor.fetchone()
    if not result:
        raise LookupError(f"Source {source_name!r} is not present in sources")
    return int(result[0])


def quote_exists(cursor, values: dict[str, Any]) -> bool:
    cursor.execute(
        """
        SELECT quote_id FROM airfare_quotes
        WHERE collection_date = %s AND travel_date = %s
          AND route_id = %s AND airline_id = %s AND booking_window = %s
          AND COALESCE(flight_number, '') = %s AND total_fare = %s
          AND source_id = %s
        LIMIT 1
        """,
        (
            values["collection_date"], values["travel_date"], values["route_id"],
            values["airline_id"], values["booking_window"], values["flight_number"],
            values["total_fare"], values["source_id"],
        ),
    )
    return cursor.fetchone() is not None


def map_csv_row(cursor, row: dict[str, str], source_id: int) -> dict[str, Any]:
    origin = first_value(row, "origin").upper()
    destination = first_value(row, "destination").upper()
    airline_name = first_value(row, "airline", "airline_name")
    raw_price = parse_decimal(first_value(row, "price", "total_fare"), "price")
    price = convert_to_inr(raw_price, first_value(row, "currency", default="INR"))
    collection_date = parse_date(first_value(row, "collection_date", "search_date"), "collection_date")
    travel_date = parse_date(first_value(row, "travel_date"), "travel_date")

    return {
        "search_date": collection_date,
        "travel_date": travel_date,
        "route_id": lookup_route_id(cursor, origin, destination),
        "airline_id": lookup_airline_id(cursor, airline_name),
        "flight_number": first_value(row, "flight_numbers", "flight_number"),
        "booking_window": parse_int(first_value(row, "advance_days", "booking_window"), "advance_days"),
        "fare_class": first_value(row, "cabin_class", "fare_class", "fare_type", default="Economy"),
        "base_fare": price,
        "taxes": Decimal("0.00"),
        "fees": Decimal("0.00"),
        "total_fare": price,
        "availability": first_value(row, "availability", default="Available"),
        "source": SOURCE_NAME,
        "collected_at": datetime.now(),
        "source_id": source_id,
        "collection_date": collection_date,
    }


def insert_quote(cursor, values: dict[str, Any]) -> None:
    cursor.execute(
        """
        INSERT INTO airfare_quotes (
            search_date, travel_date, route_id, airline_id, flight_number,
            booking_window, fare_class, base_fare, taxes, fees, total_fare,
            availability, source, collected_at, source_id, collection_date
        ) VALUES (
            %(search_date)s, %(travel_date)s, %(route_id)s, %(airline_id)s,
            %(flight_number)s, %(booking_window)s, %(fare_class)s,
            %(base_fare)s, %(taxes)s, %(fees)s, %(total_fare)s,
            %(availability)s, %(source)s, %(collected_at)s, %(source_id)s,
            %(collection_date)s
        )
        """,
        values,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Import cleaned airfare quotes into MySQL.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--commit", action="store_true", help="Insert valid new rows.")
    args = parser.parse_args()
    csv_path = args.csv.resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    valid = skipped = failed = 0
    connection = get_connection()
    cursor = connection.cursor()
    try:
        source_id = lookup_source_id(cursor, SOURCE_NAME)
        print(f"Using source_id={source_id} for {SOURCE_NAME}; all prices are stored in INR.")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            for line_number, row in enumerate(csv.DictReader(file), start=2):
                try:
                    values = map_csv_row(cursor, row, source_id)
                    if quote_exists(cursor, values):
                        skipped += 1
                        print(f"Line {line_number}: skipped (already imported).")
                    elif args.commit:
                        insert_quote(cursor, values)
                        valid += 1
                        print(f"Line {line_number}: inserted (INR {values['total_fare']}).")
                    else:
                        valid += 1
                        print(f"Line {line_number}: valid (INR {values['total_fare']}; dry run).")
                except (ValueError, LookupError, RuntimeError) as exc:
                    failed += 1
                    print(f"Line {line_number}: ERROR - {exc}")
        if failed:
            connection.rollback()
            raise RuntimeError(f"Import cancelled: {failed} invalid row(s). No database changes were made.")
        if args.commit:
            connection.commit()
            print(f"Complete: inserted={valid}, skipped={skipped}.")
        else:
            connection.rollback()
            print(f"Dry run complete: valid_new_rows={valid}, skipped={skipped}. No database changes were made.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
