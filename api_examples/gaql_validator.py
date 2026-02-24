#!/usr/bin/env python3
"""GAQL Query Validator Utility.

This script performs a dry-run validation of a GAQL query using the
validate_only=True parameter. It reads the query from stdin to avoid
shell-escaping issues with complex SQL strings.
"""

import argparse
import importlib
import re
import sys
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException.

    Args:
        exception: An exception of type GoogleAdsException.
    """
    print(
        f"FAILURE: Query validation failed with Request ID {exception.request_id}"
    )
    for error in exception.failure.errors:
        print(f"  - {error.message}")
        if error.location:
            for element in error.location.field_path_elements:
                print(f"    On field: {element.field_name}")


def main(
    client: Optional[GoogleAdsClient] = None,
    customer_id: Optional[str] = None,
    api_version: Optional[str] = None,
    query: Optional[str] = None,
) -> None:
    """Main function for the GAQL validator.

    Args:
        client: An optional GoogleAdsClient instance.
        customer_id: The Google Ads customer ID.
        api_version: The API version to use (e.g., "v23").
        query: The GAQL query to validate.
    """
    if client is None:
        parser = argparse.ArgumentParser(description="Validates a GAQL query.")
        parser.add_argument(
            "--customer_id", required=True, help="Google Ads Customer ID."
        )
        parser.add_argument(
            "--api_version",
            default="v23",
            help="API Version (e.g., v23). Defaults to v23.",
        )
        args = parser.parse_args()

        customer_id = args.customer_id
        api_version = args.api_version
        # Read query from stdin to handle multiline/quoted strings safely
        query = sys.stdin.read().strip()

        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}")
            sys.exit(1)

    if not query:
        print("Error: No query provided.")
        sys.exit(1)

    # Dynamically handle versioned types for the request object
    api_version_lower = api_version.lower()
    module_path = f"google.ads.googleads.{api_version_lower}.services.types.google_ads_service"
    try:
        module = importlib.import_module(module_path)
        search_request_type = getattr(module, "SearchGoogleAdsRequest")
    except (ImportError, AttributeError):
        print(
            f"CRITICAL ERROR: Could not import SearchGoogleAdsRequest for {api_version}."
        )
        sys.exit(1)

    ga_service = client.get_service("GoogleAdsService")
    # Normalize customer_id to digits only
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))

    try:
        print(f"--- [DRY RUN] Validating Query for {clean_customer_id} ---")
        request = search_request_type(
            customer_id=clean_customer_id, query=query, validate_only=True
        )
        ga_service.search(request=request)
        print("SUCCESS: GAQL query is structurally valid.")
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
