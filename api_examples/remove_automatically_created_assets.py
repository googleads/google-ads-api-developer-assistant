# Copyright 2026 Google LLC
"""Removes automatically created assets using the dedicated service."""

import argparse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str, campaign_id: str, asset_rn: str, field_type: str) -> None:
    service = client.get_service("AutomaticallyCreatedAssetRemovalService")
    op = client.get_type("RemoveCampaignAutomaticallyCreatedAssetOperation")
    op.campaign = client.get_service("CampaignService").campaign_path(customer_id, campaign_id)
    op.asset = asset_rn
    op.field_type = getattr(client.enums.AssetFieldTypeEnum.AssetFieldType, field_type.upper())

    try:
        res = service.remove_campaign_automatically_created_asset(customer_id=customer_id, operations=[op])
        print(f"Removed {len(res.results)} assets.")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("-C", "--campaign_id", required=True)
    parser.add_argument("-a", "--asset_rn", required=True)
    parser.add_argument("-f", "--field_type", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id, args.campaign_id, args.asset_rn, args.field_type)
