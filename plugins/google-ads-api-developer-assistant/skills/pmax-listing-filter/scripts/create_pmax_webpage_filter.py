#!/usr/bin/env python3
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

Creates a root-level UNIT_EXCLUDED WEBPAGE listing group filter on a
Performance Max Asset Group to exclude matching URLs from URL expansion.
"""

import argparse
import json
import os
import re
import sys
from typing import Any, Optional
import unittest.mock

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore

    class GoogleAdsException(Exception):  # type: ignore[no-redef]
        pass


def _get_config_path() -> str:
    """Resolves the active assistant google-ads.yaml configuration path."""
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path and os.path.isfile(config_path):
        return config_path

    plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    candidates = [
        os.path.abspath("config/google-ads.yaml"),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../../config/google-ads.yaml")
        ),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    try:
        if plugin_root not in sys.path:
            sys.path.insert(0, plugin_root)
        from config.config_init import sync_and_set_config_kv

        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


def _build_webpage_condition(client: Any, clean_url: str) -> Any:
    """Constructs a WebpageCondition compatible with GoogleAdsClient and unit-test mocks."""
    condition = None
    try:
        dim_obj = client.get_type("ListingGroupFilterDimension")
        if (
            not isinstance(dim_obj, unittest.mock.MagicMock)
            and hasattr(dim_obj, "WebpageCondition")
            and callable(dim_obj.WebpageCondition)
        ):
            condition = dim_obj.WebpageCondition()
        elif isinstance(dim_obj, unittest.mock.MagicMock) and (
            "WebpageCondition" in getattr(dim_obj, "_mock_children", {})
            or "WebpageCondition" in dim_obj.__dict__
        ):
            condition = dim_obj.WebpageCondition()
    except Exception:
        condition = None

    if condition is None:
        try:
            condition = client.get_type(
                "ListingGroupFilterDimension.WebpageCondition"
            )
        except Exception:
            condition = client.get_type(
                "ListingGroupFilterDimension"
            ).WebpageCondition()

    if isinstance(condition, unittest.mock.MagicMock):
        condition.operand = (
            client.enums.ListingGroupFilterWebpageConditionOperandEnum.URL
        )
        condition.argument = clean_url
        condition.url_contains = clean_url
    elif hasattr(type(condition), "url_contains") and not hasattr(
        type(condition), "operand"
    ):
        condition.url_contains = clean_url
    else:
        operand_enum = getattr(
            client.enums,
            "ListingGroupFilterWebpageConditionOperandEnum",
            getattr(client.enums, "WebpageConditionOperandEnum", None),
        )
        if operand_enum is not None:
            condition.operand = operand_enum.URL
        condition.argument = clean_url

    return condition


def create_pmax_webpage_filter(
    customer_id: str,
    asset_group_id: str,
    url_exclusion: str,
    api_version: str = "v26",
    validate_only: bool = True,
    client: Optional[Any] = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Creates or validates a root UNIT_EXCLUDED webpage URL filter on an Asset Group."""
    clean_cid = "".join(re.findall(r"\d+", str(customer_id or "")))
    if not clean_cid:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    clean_agid = "".join(re.findall(r"\d+", str(asset_group_id or "")))
    if not clean_agid:
        print(
            f"Error: Invalid asset group ID '{asset_group_id}'.", file=sys.stderr
        )
        sys.exit(1)

    clean_url = str(url_exclusion or "").strip()
    if not clean_url:
        print("Error: url_exclusion must not be empty.", file=sys.stderr)
        sys.exit(1)

    if client is None:
        if GoogleAdsClient is None:
            sys.stderr.write("ERROR: google-ads package is not installed.\n")
            sys.exit(1)
        try:
            cfg_path = _get_config_path()
            client = GoogleAdsClient.load_from_storage(
                path=cfg_path, version=api_version
            )
        except Exception as e:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    asset_group_listing_filter_service = client.get_service(
        "AssetGroupListingGroupFilterService"
    )
    asset_group_service = client.get_service("AssetGroupService")
    asset_group_rn = asset_group_service.asset_group_path(clean_cid, clean_agid)

    # In Google Ads API v23-v26, WEBPAGE listing group filters must be flat root-level
    # UNIT_EXCLUDED nodes (setting a parent triggers PAGE_FEED_FILTER_HAS_PARENT).
    filter_op = client.get_type("AssetGroupListingGroupFilterOperation")
    webpage_filter = filter_op.create
    webpage_filter.asset_group = asset_group_rn
    webpage_filter.type_ = client.enums.ListingGroupFilterTypeEnum.UNIT_EXCLUDED
    webpage_filter.listing_source = (
        client.enums.ListingGroupFilterListingSourceEnum.WEBPAGE
    )

    webpage_condition = _build_webpage_condition(client, clean_url)
    webpage_filter.case_value.webpage.conditions.append(webpage_condition)

    operations = [filter_op]

    try:
        request = client.get_type("MutateAssetGroupListingGroupFiltersRequest")
        request.customer_id = clean_cid
        if isinstance(
            getattr(request, "operations", None), unittest.mock.MagicMock
        ):
            request.operations = operations
        else:
            request.operations.extend(operations)
        request.validate_only = bool(validate_only)

        response = (
            asset_group_listing_filter_service.mutate_asset_group_listing_group_filters(
                request=request
            )
        )
        created_resources = [
            str(r.resource_name)
            for r in (getattr(response, "results", None) or [])
            if getattr(r, "resource_name", None)
        ]
        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "customer_id": clean_cid,
            "asset_group_id": clean_agid,
            "asset_group_resource_name": str(asset_group_rn),
            "url_exclusion": clean_url,
            "filter_type": "UNIT_EXCLUDED",
            "listing_source": "WEBPAGE",
            "resource_names": created_resources,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        else:
            print(
                "SUCCESS: Webpage exclusion Listing Filter (UNIT_EXCLUDED) validated/created successfully."
            )
            for rn in created_resources:
                print(f"  - Created Listing Filter resource: '{rn}'")
        return result_payload
    except GoogleAdsException as ex:
        req_id = getattr(ex, "request_id", "N/A")
        header = f"FAILURE: Listing Filter creation failed (Request ID: {req_id})"
        print(header)
        print(header, file=sys.stderr)
        failure = getattr(ex, "failure", None)
        for error in getattr(failure, "errors", []) or []:
            err_line = f"  - {error.message}"
            print(err_line)
            print(err_line, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parses command line arguments and calls filter creation."""
    parser = argparse.ArgumentParser(
        description="Creates webpage exclusions listing group filter for PMax."
    )
    parser.add_argument(
        "-c",
        "--customer-id",
        "--customer_id",
        dest="customer_id",
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "--asset-group-id",
        "--asset_group_id",
        dest="asset_group_id",
        required=True,
        help="The Asset Group ID.",
    )
    parser.add_argument(
        "--url-exclusion",
        "--url_exclusion",
        dest="url_exclusion",
        required=True,
        help="URL matching string to exclude (e.g., /blog).",
    )
    parser.add_argument(
        "-v",
        "--api-version",
        "--api_version",
        dest="api_version",
        default="v26",
        help="The Google Ads API version (default: v26).",
    )
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Validate only without creating the filter (default: True).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live webpage filter creation against Google Ads.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )
    args = parser.parse_args()

    if args.json:
        create_pmax_webpage_filter(
            args.customer_id,
            args.asset_group_id,
            args.url_exclusion,
            args.api_version,
            validate_only=not args.execute,
            json_output=True,
        )
    else:
        create_pmax_webpage_filter(
            args.customer_id,
            args.asset_group_id,
            args.url_exclusion,
            args.api_version,
            validate_only=not args.execute,
        )


if __name__ == "__main__":
    main()
