# Copyright 2026 Google LLC
"""Lists Performance Max campaigns with enhanced status diagnostics."""

import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.primary_status,
            campaign.primary_status_reasons
        FROM
            campaign
        WHERE
            campaign.advertising_channel_type = 'PERFORMANCE_MAX'
            AND campaign.status != 'REMOVED'"""

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        print(f"{'ID':<15} | {'Name':<30} | {'Status':<15} | {'Primary Status'}")
        print("-" * 85)
        for batch in response:
            for row in batch.results:
                campaign = row.campaign
                reasons = f" ({', '.join([r.name for r in campaign.primary_status_reasons])})" if campaign.primary_status_reasons else ""
                print(f"{campaign.id:<15} | {campaign.name[:30]:<30} | {campaign.status.name:<15} | {campaign.primary_status.name}{reasons}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(googleads_client, args.customer_id)
