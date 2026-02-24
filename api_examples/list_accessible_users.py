# Copyright 2026 Google LLC
"""Lists accessible customers with management context."""

import argparse

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient) -> None:
    """The main function to list accessible customers.

    Args:
        client: An initialized GoogleAdsClient instance.
    """
    customer_service = client.get_service("CustomerService")
    try:
        accessible = customer_service.list_accessible_customers()
        print(f"Found {len(accessible.resource_names)} accessible customers.")
        for rn in accessible.resource_names:
            print(f"- {rn}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lists accessible customers.")
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()

    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)

    main(googleads_client)
