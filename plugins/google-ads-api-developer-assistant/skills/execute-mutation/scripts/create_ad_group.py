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

"""Creates a Google Ads ad group under a campaign via AdGroupService.

Supports both validate_only=True dry-run validation (--dry-run, default) and
live execution (--execute) under the 4-Step HITL Mutation Protocol.
"""

import argparse
import json
import os
import re
import sys
import uuid
from typing import Any, Optional

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

    candidates = [
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath("config/google-ads.yaml"),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../config/google-ads.yaml")
        ),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../../../config/google-ads.yaml")
        ),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    try:
        from config.config_init import sync_and_set_config_kv

        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints clean, actionable details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: Ad group creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    if hasattr(exception, "failure") and hasattr(exception.failure, "errors"):
        for error in exception.failure.errors:
            print(f"  - {error.message}", file=sys.stderr)
            if getattr(error, "location", None):
                for element in error.location.field_path_elements:
                    print(f"    On field: {element.field_name}", file=sys.stderr)


def create_ad_group(
    customer_id: str,
    campaign_id: Optional[str] = None,
    campaign_resource_name: Optional[str] = None,
    api_version: str = "v26",
    ad_group_name: Optional[str] = None,
    cpc_bid_micros: Optional[int] = None,
    status: str = "ENABLED",
    ad_group_type: str = "SEARCH_STANDARD",
    validate_only: bool = True,
    client: Optional[Any] = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Creates or validates a Google Ads ad group under a campaign.

    Args:
        customer_id: The Google Ads Customer ID.
        campaign_id: Campaign ID to attach the ad group to (if campaign_resource_name not set).
        campaign_resource_name: Full campaign resource name (e.g., 'customers/123/campaigns/456').
        api_version: Google Ads API version (e.g., 'v26').
        ad_group_name: Name for the new ad group.
        cpc_bid_micros: Optional default CPC bid in micros (e.g., 10_000_000 = $10.00).
        status: AdGroupStatusEnum name (default: 'ENABLED').
        ad_group_type: AdGroupTypeEnum name (default: 'SEARCH_STANDARD').
        validate_only: If True, validates the request without creating the ad group.
        client: Optional pre-initialized GoogleAdsClient instance.
        json_output: If True, emits structured JSON to stdout.

    Returns:
        Dictionary containing validation or creation details.
    """
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    resolved_campaign_rn = (campaign_resource_name or "").strip()
    clean_campaign_id = "".join(re.findall(r"\d+", str(campaign_id or "")))
    if not resolved_campaign_rn and not clean_campaign_id:
        print(
            "Error: Either campaign_id or campaign_resource_name is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    if cpc_bid_micros is not None and int(cpc_bid_micros) <= 0:
        print(
            f"Error: cpc_bid_micros must be > 0 (got {cpc_bid_micros}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if client is None:
        try:
            cfg_path = _get_config_path()
            client = GoogleAdsClient.load_from_storage(
                path=cfg_path, version=api_version
            )
        except Exception as exc:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not resolved_campaign_rn:
        campaign_service = client.get_service("CampaignService")
        resolved_campaign_rn = campaign_service.campaign_path(
            clean_customer_id, clean_campaign_id
        )

    if not ad_group_name:
        ad_group_name = f"Earth to Mars Cruises {uuid.uuid4().hex[:8]}"

    status_upper = str(status or "ENABLED").strip().upper()
    status_enum = getattr(client.enums.AdGroupStatusEnum, status_upper, None)
    if status_enum is None:
        print(
            f"Error: Unknown ad group status '{status}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    type_upper = str(ad_group_type or "SEARCH_STANDARD").strip().upper()
    type_enum = getattr(client.enums.AdGroupTypeEnum, type_upper, None)
    if type_enum is None:
        print(
            f"Error: Unknown ad_group_type '{ad_group_type}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        ad_group_service = client.get_service("AdGroupService")
        ad_group_op = client.get_type("AdGroupOperation")
        ad_group = ad_group_op.create
        ad_group.name = ad_group_name
        ad_group.status = status_enum
        ad_group.campaign = resolved_campaign_rn
        ad_group.type_ = type_enum

        if cpc_bid_micros is not None:
            ad_group.cpc_bid_micros = int(cpc_bid_micros)

        request = client.get_type("MutateAdGroupsRequest")
        request.customer_id = clean_customer_id
        request.operations = [ad_group_op]
        request.validate_only = bool(validate_only)

        response = ad_group_service.mutate_ad_groups(request=request)
        ad_group_rn = ""
        if getattr(response, "results", None) and len(response.results) > 0:
            ad_group_rn = response.results[0].resource_name

        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "customer_id": clean_customer_id,
            "campaign_resource_name": resolved_campaign_rn,
            "ad_group_name": ad_group_name,
            "ad_group_status": status_upper,
            "ad_group_type": type_upper,
            "cpc_bid_micros": int(cpc_bid_micros)
            if cpc_bid_micros is not None
            else None,
            "ad_group_resource_name": ad_group_rn,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                f"SUCCESS (validate_only=True): Verified creation of ad group "
                f"'{ad_group_name}' ({type_upper}, {status_upper}) under {resolved_campaign_rn}."
            )
        else:
            print(f"SUCCESS: Created ad group {ad_group_rn}.")
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entrypoint for creating a Google Ads ad group."""
    parser = argparse.ArgumentParser(
        description="Creates a Google Ads ad group under a campaign via AdGroupService."
    )
    parser.add_argument(
        "-c",
        "--customer-id",
        "--customer_id",
        dest="customer_id",
        required=True,
        help="Google Ads Customer ID.",
    )
    parser.add_argument(
        "--campaign-id",
        "--campaign_id",
        dest="campaign_id",
        default=None,
        help="Campaign ID to create the ad group under.",
    )
    parser.add_argument(
        "--campaign-resource-name",
        "--campaign_resource_name",
        dest="campaign_resource_name",
        default=None,
        help="Full campaign resource name (e.g., 'customers/123/campaigns/456').",
    )
    parser.add_argument(
        "-v",
        "--api-version",
        "--api_version",
        dest="api_version",
        default="v26",
        help="Google Ads API version (default: v26).",
    )
    parser.add_argument(
        "--ad-group-name",
        "--ad_group_name",
        "--name",
        dest="ad_group_name",
        default=None,
        help="Name for the new ad group.",
    )
    parser.add_argument(
        "--cpc-bid-micros",
        "--cpc_bid_micros",
        dest="cpc_bid_micros",
        type=int,
        default=None,
        help="Optional default CPC bid in micros (e.g., 10000000 = $10.00).",
    )
    parser.add_argument(
        "--status",
        default="ENABLED",
        help="Initial ad group status (ENABLED or PAUSED, default: ENABLED).",
    )
    parser.add_argument(
        "--ad-group-type",
        "--ad_group_type",
        dest="ad_group_type",
        default="SEARCH_STANDARD",
        help="AdGroupTypeEnum value (default: SEARCH_STANDARD).",
    )
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Validate only without creating the ad group (default: True).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live ad group creation (validate_only=False).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )

    args = parser.parse_args()
    create_ad_group(
        customer_id=args.customer_id,
        campaign_id=args.campaign_id,
        campaign_resource_name=args.campaign_resource_name,
        api_version=args.api_version,
        ad_group_name=args.ad_group_name,
        cpc_bid_micros=args.cpc_bid_micros,
        status=args.status,
        ad_group_type=args.ad_group_type,
        validate_only=not args.execute,
        json_output=args.json,
    )


if __name__ == "__main__":
    main()
