# Copyright 2026 Google LLC
"""Retrieves campaign bid simulations with dynamic date ranges."""

import argparse
from datetime import datetime, timedelta
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str, campaign_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=8)).strftime("%Y-%m-%d")
    
    query = f"""
        SELECT campaign_bid_simulation.campaign_id, campaign_bid_simulation.bid_modifier,
               campaign_bid_simulation.clicks, campaign_bid_simulation.cost_micros
        FROM campaign_bid_simulation
        WHERE campaign.id = {campaign_id}
        AND campaign_bid_simulation.start_date = '{start}'
        AND campaign_bid_simulation.end_date = '{end}'
        ORDER BY campaign_bid_simulation.bid_modifier"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        print(f"{'Modifier':<10} | {'Clicks':<10} | {'Cost (micros)'}")
        print("-" * 40)
        for batch in stream:
            for row in batch.results:
                sim = row.campaign_bid_simulation
                print(f"{sim.bid_modifier:<10.2f} | {sim.clicks:<10} | {sim.cost_micros}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("-i", "--campaign_id", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id, args.campaign_id)
