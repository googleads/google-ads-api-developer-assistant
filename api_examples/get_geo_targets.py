# Copyright 2026 Google LLC
"""Retrieves geo targets using efficient bulk queries."""

import argparse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    # Bulk query for criteria
    query = """
        SELECT campaign.id, campaign.name, campaign_criterion.criterion_id, campaign_criterion.negative
        FROM campaign_criterion
        WHERE campaign_criterion.type = 'LOCATION'"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        crit_map = {}
        for batch in stream:
            for row in batch.results:
                crit_map[row.campaign_criterion.criterion_id] = (row.campaign.name, row.campaign_criterion.negative)
        
        if not crit_map:
            print("No geo targets found.")
            return

        # Bulk query for constants
        ids = ", ".join([str(i) for i in crit_map.keys()])
        geo_query = f"SELECT geo_target_constant.id, geo_target_constant.canonical_name FROM geo_target_constant WHERE geo_target_constant.id IN ({ids})"
        geo_stream = ga_service.search_stream(customer_id=customer_id, query=geo_query)
        
        print(f"{'Campaign':<25} | {'Target':<30} | {'Negative'}")
        print("-" * 70)
        for batch in geo_stream:
            for row in batch.results:
                cid = row.geo_target_constant.id
                c_name, neg = crit_map[cid]
                print(f"{c_name[:25]:<25} | {row.geo_target_constant.canonical_name[:30]:<30} | {neg}")
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
