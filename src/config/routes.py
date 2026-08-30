# Representative domestic routes for the prototype.
#
# IMPORTANT:
# These are prototype weights.
# For the final SIH submission, replace them with
# weights derived from DGCA passenger-traffic data.

ROUTE_WEIGHTS = {
    "DEL-BOM": 0.25,
    "DEL-BLR": 0.20,
    "BOM-BLR": 0.15,
    "DEL-CCU": 0.15,
    "BLR-HYD": 0.10,
    "MAA-DEL": 0.15,
}


def get_route_key(origin, destination):
    """Create a standard route identifier."""

    return f"{origin.upper()}-{destination.upper()}"


def get_route_weight(origin, destination):
    """Return the prototype weight for a route."""

    route = get_route_key(origin, destination)

    return ROUTE_WEIGHTS.get(route, 0.0)