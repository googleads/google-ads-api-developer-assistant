# Copyright 2026 Google LLC
"""Targets a campaign with a user list using version-safe path construction."""

import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str, campaign_id: str, user_list_id: str) -> None:
    service = client.get_service("CampaignCriterionService")
    op = client.get_type("CampaignCriterionOperation")
    crit = op.create
    crit.campaign = client.get_service("CampaignService").campaign_path(customer_id, campaign_id)
    crit.user_list.user_list = client.get_service("UserListService").user_list_path(customer_id, user_list_id)

    try:
        res = service.mutate_campaign_criteria(customer_id=customer_id, operations=[op])
        print(f"Created criterion: {res.results[0].resource_name}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("-C", "--campaign_id", required=True)
    parser.add_argument("-u", "--user_list_id", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id, args.campaign_id, args.user_list_id)
