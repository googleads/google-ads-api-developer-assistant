# Copyright 2026 Google LLC
"""Retrieves change history with optional resource type filtering."""

import argparse
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str, start: str, end: str, resource_type: str = None) -> None:
    ga_service = client.get_service("GoogleAdsService")
    where_clauses = [f"change_status.last_change_date_time BETWEEN '{start}' AND '{end}'"]
    if resource_type:
        where_clauses.append(f"change_status.resource_type = '{resource_type.upper()}'")

    query = f"""
        SELECT
            change_status.resource_name,
            change_status.last_change_date_time,
            change_status.resource_type,
            change_status.resource_status
        FROM change_status
        WHERE {" AND ".join(where_clauses)}
        ORDER BY change_status.last_change_date_time DESC
        LIMIT 1000
    """

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        print(f"{'Date/Time':<25} | {'Type':<20} | {'Status':<15} | {'Resource'}")
        print("-" * 100)
        for batch in stream:
            for row in batch.results:
                cs = row.change_status
                print(f"{str(cs.last_change_date_time):<25} | {cs.resource_type.name:<20} | {cs.resource_status.name:<15} | {cs.resource_name}")
    except GoogleAdsException as ex:
        print(f"Error (Request ID {ex.request_id}): {ex.failure.errors[0].message}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("--start_date")
    parser.add_argument("--resource_type", help="Filter by type (e.g. CAMPAIGN, AD_GROUP)")
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()

    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)
    end = datetime.now().strftime("%Y-%m-%d")
    start = args.start_date or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    main(googleads_client, args.customer_id, start, end, args.resource_type)
