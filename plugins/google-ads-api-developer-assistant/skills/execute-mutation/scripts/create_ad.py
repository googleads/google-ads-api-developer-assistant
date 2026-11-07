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

"""Creates a Google Ads Responsive Search Ad under an ad group via AdGroupAdService.

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
        f"FAILURE: Ad creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    if hasattr(exception, "failure") and hasattr(exception.failure, "errors"):
        for error in exception.failure.errors:
            print(f"  - {error.message}", file=sys.stderr)
            if getattr(error, "location", None):
                for element in error.location.field_path_elements:
                    print(f"    On field: {element.field_name}", file=sys.stderr)


def _create_ad_text_asset(client: Any, text: str) -> Any:
    """Creates an AdTextAsset protobuf message with the specified text."""
    ad_text_asset = client.get_type("AdTextAsset")
    ad_text_asset.text = text
    return ad_text_asset


def create_responsive_search_ad(
    customer_id: str,
    ad_group_id: Optional[str] = None,
    ad_group_resource_name: Optional[str] = None,
    api_version: str = "v26",
    final_urls: Optional[list[str]] = None,
    headlines: Optional[list[str]] = None,
    descriptions: Optional[list[str]] = None,
    path1: Optional[str] = None,
    path2: Optional[str] = None,
    status: str = "PAUSED",
    validate_only: bool = True,
    client: Optional[Any] = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Creates or validates a Google Ads Responsive Search Ad under an ad group.

    Args:
        customer_id: The Google Ads Customer ID.
        ad_group_id: Ad Group ID to attach the ad to (if ad_group_resource_name not set).
        ad_group_resource_name: Full ad group resource name (e.g., 'customers/123/adGroups/789').
        api_version: Google Ads API version (e.g., 'v26').
        final_urls: List of landing page final URLs (default: ['https://www.example.com']).
        headlines: List of at least 3 headline strings (up to 15, <=30 chars each).
        descriptions: List of at least 2 description strings (up to 4, <=90 chars each).
        path1: Optional first display URL path segment (<=15 chars).
        path2: Optional second display URL path segment (<=15 chars).
        status: AdGroupAdStatusEnum name (default: 'PAUSED').
        validate_only: If True, validates the request without creating the ad.
        client: Optional pre-initialized GoogleAdsClient instance.
        json_output: If True, emits structured JSON to stdout.

    Returns:
        Dictionary containing validation or creation details.
    """
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    resolved_ad_group_rn = (ad_group_resource_name or "").strip()
    clean_ad_group_id = "".join(re.findall(r"\d+", str(ad_group_id or "")))
    if not resolved_ad_group_rn and not clean_ad_group_id:
        print(
            "Error: Either ad_group_id or ad_group_resource_name is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    resolved_final_urls = [
        str(u).strip() for u in (final_urls or []) if str(u).strip()
    ]
    if not resolved_final_urls:
        resolved_final_urls = ["https://www.example.com"]

    if headlines is not None:
        resolved_headlines = [str(h).strip() for h in headlines if str(h).strip()]
    else:
        short_id = uuid.uuid4().hex[:4]
        resolved_headlines = [
            f"Cruise to Mars #{short_id}",
            "Best Space Cruise Line",
            "Experience the Stars",
        ]

    if len(resolved_headlines) < 3:
        print(
            f"Error: Responsive Search Ads require at least 3 headlines (got {len(resolved_headlines)}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if descriptions is not None:
        resolved_descriptions = [
            str(d).strip() for d in descriptions if str(d).strip()
        ]
    else:
        resolved_descriptions = [
            "Buy your tickets now for an unforgettable interplanetary journey.",
            "Visit the Red Planet in luxury and comfort.",
        ]

    if len(resolved_descriptions) < 2:
        print(
            f"Error: Responsive Search Ads require at least 2 descriptions (got {len(resolved_descriptions)}).",
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

    if not resolved_ad_group_rn:
        ad_group_service = client.get_service("AdGroupService")
        resolved_ad_group_rn = ad_group_service.ad_group_path(
            clean_customer_id, clean_ad_group_id
        )

    status_upper = str(status or "PAUSED").strip().upper()
    status_enum = getattr(client.enums.AdGroupAdStatusEnum, status_upper, None)
    if status_enum is None:
        print(
            f"Error: Unknown ad status '{status}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        ad_group_ad_service = client.get_service("AdGroupAdService")
        ad_group_ad_op = client.get_type("AdGroupAdOperation")
        ad_group_ad = ad_group_ad_op.create
        ad_group_ad.status = status_enum
        ad_group_ad.ad_group = resolved_ad_group_rn

        for url in resolved_final_urls:
            ad_group_ad.ad.final_urls.append(url)

        for headline_text in resolved_headlines:
            ad_group_ad.ad.responsive_search_ad.headlines.append(
                _create_ad_text_asset(client, headline_text)
            )

        for desc_text in resolved_descriptions:
            ad_group_ad.ad.responsive_search_ad.descriptions.append(
                _create_ad_text_asset(client, desc_text)
            )

        if path1:
            ad_group_ad.ad.responsive_search_ad.path1 = str(path1).strip()
        if path2:
            ad_group_ad.ad.responsive_search_ad.path2 = str(path2).strip()

        request = client.get_type("MutateAdGroupAdsRequest")
        request.customer_id = clean_customer_id
        request.operations = [ad_group_ad_op]
        request.validate_only = bool(validate_only)

        response = ad_group_ad_service.mutate_ad_group_ads(request=request)
        ad_group_ad_rn = ""
        if getattr(response, "results", None) and len(response.results) > 0:
            ad_group_ad_rn = response.results[0].resource_name

        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "customer_id": clean_customer_id,
            "ad_group_resource_name": resolved_ad_group_rn,
            "ad_status": status_upper,
            "final_urls": resolved_final_urls,
            "headlines": resolved_headlines,
            "descriptions": resolved_descriptions,
            "path1": path1,
            "path2": path2,
            "ad_group_ad_resource_name": ad_group_ad_rn,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                f"SUCCESS (validate_only=True): Verified creation of Responsive Search Ad "
                f"({len(resolved_headlines)} headlines, {len(resolved_descriptions)} descriptions, "
                f"status={status_upper}) under {resolved_ad_group_rn}."
            )
        else:
            print(
                f"SUCCESS: Created responsive search ad with resource_name {ad_group_ad_rn}."
            )
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


create_ad = create_responsive_search_ad


def main() -> None:
    """CLI entrypoint for creating a Google Ads Responsive Search Ad."""
    parser = argparse.ArgumentParser(
        description="Creates a Google Ads Responsive Search Ad under an ad group via AdGroupAdService."
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
        "--ad-group-id",
        "--ad_group_id",
        dest="ad_group_id",
        default=None,
        help="Ad Group ID to create the ad under.",
    )
    parser.add_argument(
        "--ad-group-resource-name",
        "--ad_group_resource_name",
        dest="ad_group_resource_name",
        default=None,
        help="Full ad group resource name (e.g., 'customers/123/adGroups/789').",
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
        "--final-url",
        "--final_url",
        dest="final_urls",
        action="append",
        default=None,
        help="Landing page final URL (can be specified multiple times; default: https://www.example.com).",
    )
    parser.add_argument(
        "--headline",
        dest="headlines",
        action="append",
        default=None,
        help="Headline text (specify at least 3 times when provided).",
    )
    parser.add_argument(
        "--description",
        dest="descriptions",
        action="append",
        default=None,
        help="Description text (specify at least 2 times when provided).",
    )
    parser.add_argument(
        "--path1",
        default=None,
        help="Optional first display URL path segment (<=15 chars).",
    )
    parser.add_argument(
        "--path2",
        default=None,
        help="Optional second display URL path segment (<=15 chars).",
    )
    parser.add_argument(
        "--status",
        default="PAUSED",
        help="Initial ad status (PAUSED or ENABLED, default: PAUSED).",
    )
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Validate only without creating the ad (default: True).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live ad creation (validate_only=False).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )

    args = parser.parse_args()
    create_responsive_search_ad(
        customer_id=args.customer_id,
        ad_group_id=args.ad_group_id,
        ad_group_resource_name=args.ad_group_resource_name,
        api_version=args.api_version,
        final_urls=args.final_urls,
        headlines=args.headlines,
        descriptions=args.descriptions,
        path1=args.path1,
        path2=args.path2,
        status=args.status,
        validate_only=not args.execute,
        json_output=args.json,
    )


if __name__ == "__main__":
    main()
