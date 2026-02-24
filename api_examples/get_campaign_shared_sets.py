# Copyright 2026 Google LLC
"""Lists campaign shared sets with detailed types."""

import argparse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, shared_set.id, shared_set.name, shared_set.type
        FROM campaign_shared_set
        ORDER BY campaign.id"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        print(f"{'Campaign':<20} | {'Shared Set':<20} | {'Type'}")
        print("-" * 60)
        for batch in stream:
            for row in batch.results:
                print(f"{row.campaign.name[:20]:<20} | {row.shared_set.name[:20]:<20} | {row.shared_set.type.name}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id)
