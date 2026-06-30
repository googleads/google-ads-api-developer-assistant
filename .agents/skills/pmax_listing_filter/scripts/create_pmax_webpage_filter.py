# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PMax Webpage Filter Creation Utility.

Demonstrates listing group filters subdivision tree setup for webpage URL rules.
"""

import argparse
import sys
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def create_pmax_webpage_filter(
    customer_id: str,
    asset_group_id: str,
    url_exclusion: str,
    api_version: str,
    client: Optional[GoogleAdsClient] = None,
    validate_only: bool = True,
) -> None:
    """Creates webpage URL expansion filters on an Asset Group."""
    if client is None:
        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}", file=sys.stderr)
            sys.exit(1)

    # Retrieve services
    asset_group_listing_filter_service = client.get_service("AssetGroupListingGroupFilterService")

    # Create parent node operation
    # Node 1: Webpage root node
    parent_filter_op = client.get_type("AssetGroupListingGroupFilterOperation")
    parent_filter = parent_filter_op.create
    parent_filter.asset_group = client.get_service("AssetGroupService").asset_group_path(
        customer_id, asset_group_id
    )
    parent_filter.type_ = (
        client.enums.ListingGroupFilterTypeEnum.SUBDIVISION
    )
    parent_filter.listing_source = (
        client.enums.ListingGroupFilterListingSourceEnum.WEBPAGE
    )
    # Temporary resource name for parenting child nodes in the same transaction
    parent_resource_name = asset_group_listing_filter_service.asset_group_listing_group_filter_path(
        customer_id, asset_group_id, "-1"
    )
    parent_filter.resource_name = parent_resource_name

    # Child Node 2: Unit Included Webpage filter matching the URL contains string
    child_filter_op = client.get_type("AssetGroupListingGroupFilterOperation")
    child_filter = child_filter_op.create
    child_filter.asset_group = parent_filter.asset_group
    child_filter.parent_listing_group_filter = parent_resource_name
    child_filter.type_ = (
        client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED
    )
    child_filter.listing_source = parent_filter.listing_source

    # Set Webpage condition: URL contains the exclusion rule
    condition = child_filter.case_value.webpage
    webpage_condition = client.get_type("ListingGroupFilterDimension").WebpageCondition()
    webpage_condition.url_contains = url_exclusion
    condition.conditions.append(webpage_condition)

    # Build transaction operations
    operations = [parent_filter_op, child_filter_op]

    try:
        # Execute mutate listing filters in dry-run mode by default
        request = client.get_type("MutateAssetGroupListingGroupFiltersRequest")
        request.customer_id = customer_id
        request.operations.extend(operations)
        request.validate_only = validate_only

        response = asset_group_listing_filter_service.mutate_asset_group_listing_group_filters(
            request=request
        )
        print("SUCCESS: Subdivision Webpage Listing Filter tree validated/created successfully.")
        for result in response.results:
            print(f"  - Created Listing Filter resource: '{result.resource_name}'")
    except GoogleAdsException as ex:
        print(f"FAILURE: Listing Filter creation failed (Request ID: {ex.request_id})")
        for error in ex.failure.errors:
            print(f"  - {error.message}")
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parses command line arguments and calls filter creation."""
    parser = argparse.ArgumentParser(description="Creates webpage exclusions listing group filter for PMax.")
    parser.add_argument("--customer_id", required=True, help="The Google Ads customer ID.")
    parser.add_argument("--asset_group_id", required=True, help="The Asset Group ID.")
    parser.add_argument("--url_exclusion", required=True, help="URL matching string to exclude (e.g., /blog).")
    parser.add_argument("--api_version", required=True, help="The Google Ads API version (e.g., v24).")
    parser.add_argument("--execute", action="store_true", default=False, help="If set, execute the actual mutation instead of dry-run validation.")
    args = parser.parse_args()

    create_pmax_webpage_filter(
        args.customer_id,
        args.asset_group_id,
        args.url_exclusion,
        args.api_version,
        validate_only=not args.execute,
    )


if __name__ == "__main__":
    main()
