def extract_itineraries(data, collection_date, advance_days, travel_date, origin, destination):
    """
    Convert raw IGNAV JSON into itinerary-level airfare records.

    One itinerary becomes one record, even if the itinerary
    contains multiple flight segments.
    """

    records = []

    itineraries = data.get("itineraries", [])

    for itinerary in itineraries:

        price = itinerary.get("price", {})
        outbound = itinerary.get("outbound", {})
        segments = outbound.get("segments", [])

        if not segments:
            continue

        # First segment = journey departure
        first_segment = segments[0]

        # Last segment = final arrival
        last_segment = segments[-1]

        # Collect flight numbers from all segments
        flight_numbers = [
            segment.get("flight_number")
            for segment in segments
            if segment.get("flight_number")
        ]

        # Collect carrier codes from all segments
        carrier_codes = [
            segment.get("marketing_carrier_code")
            for segment in segments
            if segment.get("marketing_carrier_code")
        ]

        record = {

            "collection_date": collection_date,

            "advance_days": advance_days,

            "travel_date": travel_date,

            "origin": origin,

            "destination": destination,

            "airline": outbound.get("carrier"),

            "carrier_codes": ",".join(carrier_codes),

            "flight_numbers": ",".join(flight_numbers),

            "departure_airport":
                first_segment.get("departure_airport"),

            "arrival_airport":
                last_segment.get("arrival_airport"),

            "departure_time":
                first_segment.get("departure_time_local"),

            "arrival_time":
                last_segment.get("arrival_time_local"),

            "duration_minutes":
                outbound.get("duration_minutes"),

            "number_of_segments":
                len(segments),

            "stops":
                max(len(segments) - 1, 0),

            "price":
                price.get("amount"),

            "currency":
                price.get("currency"),

            "price_status":
                price.get("status"),

            "cabin_class":
                itinerary.get("cabin_class"),

            "self_transfer":
                itinerary.get("requires_self_transfer"),

            "ignav_id":
                itinerary.get("ignav_id")
        }

        records.append(record)

    return records