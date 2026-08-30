import pandas as pd

from src.cleaning.fare_cleaner import clean_fares
from src.index.index_calculator import (
    calculate_route_prices,
    calculate_route_indices,
    calculate_overall_index,
)


# -----------------------------------------
# Load cleaned CSV
# -----------------------------------------

input_file = "data/cleaned/airfare_cleaned.csv"

df = pd.read_csv(input_file)

print("\nRaw cleaned CSV records:", len(df))


# -----------------------------------------
# Clean again
# -----------------------------------------

cleaned_df = clean_fares(df)


# -----------------------------------------
# Route prices
# -----------------------------------------

route_prices = calculate_route_prices(
    cleaned_df
)

print("\n" + "=" * 60)
print("ROUTE PRICE SUMMARY")
print("=" * 60)

print(
    route_prices.to_string(index=False)
)


# -----------------------------------------
# Route indices
# -----------------------------------------

route_indices = calculate_route_indices(
    cleaned_df
)

print("\n" + "=" * 60)
print("ROUTE INDICES")
print("=" * 60)

print(
    route_indices.to_string(index=False)
)


# -----------------------------------------
# Overall index
# -----------------------------------------

overall_index = calculate_overall_index(
    route_indices
)

print("\n" + "=" * 60)
print("OVERALL AIRFARE PRICE INDEX")
print("=" * 60)

if overall_index is not None:

    print(
        f"Index: {overall_index:.2f}"
    )

else:

    print(
        "Overall index could not be calculated."
    )