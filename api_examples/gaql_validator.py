#!/usr/bin/env python3
"""GAQL Query Validator Utility.

This script performs a dry-run validation of a GAQL query using the 
validate_only=True parameter. It reads the query from stdin to avoid 
shell-escaping issues with complex SQL strings.
"""

import sys
import re
import argparse
import importlib
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client=None, customer_id=None, api_version=None, query=None):
    if client is None:
        parser = argparse.ArgumentParser(description="Validates a GAQL query.")
        parser.add_argument("--customer_id", required=True, help="Google Ads Customer ID.")
        parser.add_argument("--api_version", required=True, help="API Version (e.g., v23).")
        args = parser.parse_args()

        customer_id = args.customer_id
        api_version = args.api_version
        # Read query from stdin to handle multiline/quoted strings safely
        query = sys.stdin.read().strip()

        # Initialize client
        try:
            client = GoogleAdsClient.load_from_storage()
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}")
            sys.exit(1)

    if not query:
        print("Error: No query provided.")
        sys.exit(1)

    # Dynamically handle versioned types
    api_version = api_version.lower()
    module_path = f"google.ads.googleads.{api_version}.services.types.google_ads_service"
    try:
        module = importlib.import_module(module_path)
        SearchGoogleAdsRequest = getattr(module, "SearchGoogleAdsRequest")
    except (ImportError, AttributeError):
        print(f"CRITICAL ERROR: Could not import SearchGoogleAdsRequest for {api_version}.")
        sys.exit(1)

    ga_service = client.get_service("GoogleAdsService")
    customer_id = "".join(re.findall(r'\d+', str(customer_id)))

    try:
        request = SearchGoogleAdsRequest(
            customer_id=customer_id, 
            query=query, 
            validate_only=True
        )
        ga_service.search(request=request)
        print("SUCCESS: GAQL query is valid.")
    except GoogleAdsException as ex:
        print(f"FAILURE: Query validation failed with Request ID {ex.request_id}")
        for error in ex.failure.errors:
            print(f"  - {error.message}")
            if error.location:
                for element in error.location.field_path_elements:
                    print(f"    On field: {element.field_name}")
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
