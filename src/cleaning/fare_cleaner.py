import pandas as pd


def clean_fares(df):
    """
    Clean raw airfare data.

    This function does NOT call any API.
    It only processes the supplied DataFrame.
    """

    df = df.copy()

    print("\n" + "=" * 60)
    print("STARTING FARE CLEANING")
    print("=" * 60)

    # -----------------------------------------
    # 1. Remove completely empty rows
    # -----------------------------------------

    df = df.dropna(how="all")

    # -----------------------------------------
    # 2. Remove duplicate records
    # -----------------------------------------

    before = len(df)

    df = df.drop_duplicates(
        subset=["ignav_id"]
    )

    after = len(df)

    print(
        f"Duplicates removed: {before - after}"
    )

    # -----------------------------------------
    # 3. Convert numeric columns
    # -----------------------------------------

    numeric_columns = [
        "advance_days",
        "duration_minutes",
        "number_of_segments",
        "stops",
        "price"
    ]

    for column in numeric_columns:

        if column in df.columns:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    # -----------------------------------------
    # 4. Convert dates
    # -----------------------------------------

    df["collection_date"] = pd.to_datetime(
        df["collection_date"],
        errors="coerce"
    )

    df["travel_date"] = pd.to_datetime(
        df["travel_date"],
        errors="coerce"
    )

    # -----------------------------------------
    # 5. Remove records with invalid price
    # -----------------------------------------

    before = len(df)

    df = df[
        df["price"].notna()
        & (df["price"] > 0)
    ]

    after = len(df)

    print(
        f"Invalid prices removed: {before - after}"
    )

    # -----------------------------------------
    # 6. Remove invalid routes
    # -----------------------------------------

    before = len(df)

    df = df[
        df["origin"].notna()
        & df["destination"].notna()
        & (df["origin"] != df["destination"])
    ]

    after = len(df)

    print(
        f"Invalid routes removed: {before - after}"
    )

    # -----------------------------------------
    # 7. Normalize text fields
    # -----------------------------------------

    text_columns = [
        "origin",
        "destination",
        "airline",
        "carrier_codes",
        "flight_numbers",
        "currency",
        "cabin_class",
        "price_status"
    ]

    for column in text_columns:

        if column in df.columns:

            df[column] = (
                df[column]
                .astype("string")
                .str.strip()
            )

    # -----------------------------------------
    # 8. Create fare type
    # -----------------------------------------

    df["fare_type"] = "quoted_fare"

    # -----------------------------------------
    # 9. Add direct/connecting classification
    # -----------------------------------------

    df["flight_type"] = df["stops"].apply(
        lambda x:
            "non_stop"
            if x == 0
            else "connecting"
    )

    # -----------------------------------------
    # 10. Reset index
    # -----------------------------------------

    df = df.reset_index(drop=True)

    print(
        f"Final cleaned records: {len(df)}"
    )

    print("=" * 60)

    return df