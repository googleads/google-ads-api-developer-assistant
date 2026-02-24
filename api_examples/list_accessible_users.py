# Copyright 2026 Google LLC
"""Lists accessible customers with management context."""

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main() -> None:
    client = GoogleAdsClient.load_from_storage(version="v23")
    customer_service = client.get_service("CustomerService")
    try:
        accessible = customer_service.list_accessible_customers()
        print(f"Found {len(accessible.resource_names)} accessible customers.")
        for rn in accessible.resource_names:
            print(f"- {rn}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    main()
