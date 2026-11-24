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

"""Creates a Google Ads Responsive Search Ad via AdGroupAdService.

Supports both validate_only=True dry-run validation (--dry-run, default) and
live execution (--execute) under the 4-Step HITL Mutation Protocol.
"""

import argparse
import importlib
import importlib.util
import json
import os
import re
import sys
from typing import Any, Optional


class _FallbackGoogleAdsError(Exception):
    """Fallback exception when the google-ads package is not installed."""


try:
    GoogleAdsClient: Any = importlib.import_module(
        "google.ads.googleads.client"
    ).GoogleAdsClient
    GoogleAdsException: Any = importlib.import_module(
        "google.ads.googleads.errors"
    ).GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # pylint: disable=invalid-name
    GoogleAdsException = _FallbackGoogleAdsError


def _load_extra_sdk_exceptions() -> tuple[type[Exception], ...]:
    """Loads optional transport/config exception types when installed."""
    extra: list[type[Exception]] = []
    for mod_name, attr in (
        ("yaml", "YAMLError"),
        ("grpc", "RpcError"),
        ("google.auth.exceptions", "GoogleAuthError"),
    ):
        try:
            cls = getattr(importlib.import_module(mod_name), attr, None)
            if isinstance(cls, type) and issubclass(cls, Exception):
                extra.append(cls)
        except ImportError:
            pass
    return tuple(extra)


_SDK_EXCEPTIONS: tuple[type[Exception], ...] = (
    OSError,
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    RuntimeError,
    *_load_extra_sdk_exceptions(),
)


def _load_config_init() -> Any:
    """Imports the plugin's config/config_init.py (shared API version resolver)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    if plugin_root not in sys.path and os.path.isdir(plugin_root):
        sys.path.insert(0, plugin_root)
    return importlib.import_module("config.config_init")


def _normalize_api_version(api_version: Optional[str] = None) -> str:
    """Returns a validated 'vN' API version.

    Delegates to config_init.resolve_active_api_version (explicit value, then
    GOOGLE_ADS_API_VERSION, then assistant_config, then installed versions).

    Raises:
        ValueError: If the version is invalid or cannot be determined.
    """
    try:
        resolver = _load_config_init().resolve_active_api_version
    except (ImportError, AttributeError) as exc:
        clean = str(api_version or "").strip().lower()
        if re.fullmatch(r"v?\d+", clean):
            return f"v{int(clean.lstrip('v'))}"
        raise ValueError(
            "Could not load config/config_init.py to resolve the Google Ads "
            f"API version ({exc}); pass --api_version vN"
        ) from exc
    return str(resolver(api_version))


def _get_config_path() -> str:
    """Resolves the active assistant google-ads.yaml configuration path."""
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path:
        expanded_env = os.path.abspath(os.path.expanduser(config_path))
        raw_home_yaml = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
        if expanded_env != raw_home_yaml and os.path.isfile(expanded_env):
            return config_path if os.path.isfile(config_path) else expanded_env

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    candidates = (
        os.path.abspath("config/google-ads.yaml"),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/"
            "google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/"
            "google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath(
            os.path.join(script_dir, "../../../../config/google-ads.yaml")
        ),
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    try:
        if plugin_root not in sys.path and os.path.isdir(plugin_root):
            sys.path.insert(0, plugin_root)
        config_init = importlib.import_module("config.config_init")
        return config_init.sync_and_set_config_kv()
    except (AttributeError, ImportError, OSError, RuntimeError, ValueError):
        pass

    return os.path.abspath("config/google-ads.yaml")


def handle_googleads_exception(exception: Exception) -> None:
    """Prints clean, actionable details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: Ad creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        print(f"  - {error.message}", file=sys.stderr)
        if getattr(error, "location", None):
            elems = getattr(error.location, "field_path_elements", []) or []
            for element in elems:
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
    api_version: Optional[str] = None,
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
        ad_group_id: Ad Group ID (or resource name) to attach the ad to.
        ad_group_resource_name: Full ad group resource name (e.g.,
          'customers/123/adGroups/789').
        api_version: Google Ads API version (defaults to active version).
        final_urls: List of landing page final URLs (default:
          ['https://www.example.com']).
        headlines: List of 3 to 15 headline strings (<=30 chars each).
        descriptions: List of 2 to 4 description strings (<=90 chars each).
        path1: Optional first display URL path segment (<=15 chars).
        path2: Optional second display URL path segment (<=15 chars).
        status: AdGroupAdStatusEnum name (default: 'PAUSED').
        validate_only: If True, validates without creating the ad.
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
    raw_ad_group_id = str(ad_group_id or "").strip()
    if not resolved_ad_group_rn and raw_ad_group_id.startswith("customers/"):
        resolved_ad_group_rn = raw_ad_group_id

    if resolved_ad_group_rn and not re.fullmatch(
        r"customers/\d+/adGroups/-?\d+", resolved_ad_group_rn
    ):
        print(
            f"Error: Invalid ad group resource name '{resolved_ad_group_rn}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    clean_ad_group_id = (
        ""
        if resolved_ad_group_rn
        else "".join(re.findall(r"\d+", raw_ad_group_id))
    )
    if not resolved_ad_group_rn and not clean_ad_group_id:
        print(
            "Error: Either ad_group_id or ad_group_resource_name is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    status_upper = str(status or "PAUSED").strip().upper()
    if status_upper == "REMOVED":
        print(
            "Error: BLOCKED BY DELETION PROHIBITION: Setting ad status to "
            "'REMOVED' is prohibited. Use 'PAUSED' instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if status_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid ad status '{status}'. Must be 'PAUSED' or "
            "'ENABLED'.",
            file=sys.stderr,
        )
        sys.exit(1)

    resolved_final_urls = [
        str(u).strip() for u in final_urls or [] if str(u).strip()
    ]
    if not resolved_final_urls:
        resolved_final_urls = ["https://www.example.com"]

    if headlines is not None:
        resolved_headlines = [
            str(h).strip() for h in headlines if str(h).strip()
        ]
    else:
        resolved_headlines = [
            "Explore Official Solutions",
            "Trusted Quality & Service",
            "Get Started Online Today",
        ]

    if len(resolved_headlines) < 3 or len(resolved_headlines) > 15:
        print(
            "Error: Responsive Search Ads require between 3 and 15 headlines "
            f"(got {len(resolved_headlines)}).",
            file=sys.stderr,
        )
        sys.exit(1)
    for idx, hl in enumerate(resolved_headlines, start=1):
        if len(hl) > 30:
            print(
                f"Error: Headline {idx} exceeds maximum length of 30 "
                f"characters ({len(hl)} chars): '{hl}'.",
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

    if len(resolved_descriptions) < 2 or len(resolved_descriptions) > 4:
        print(
            "Error: Responsive Search Ads require between 2 and 4 "
            f"descriptions (got {len(resolved_descriptions)}).",
            file=sys.stderr,
        )
        sys.exit(1)
    for idx, desc in enumerate(resolved_descriptions, start=1):
        if len(desc) > 90:
            print(
                f"Error: Description {idx} exceeds maximum length of 90 "
                f"characters ({len(desc)} chars).",
                file=sys.stderr,
            )
            sys.exit(1)

    clean_path1 = str(path1).strip() if path1 is not None else ""
    clean_path2 = str(path2).strip() if path2 is not None else ""
    if len(clean_path1) > 15:
        print(
            "Error: path1 exceeds maximum length of 15 characters "
            f"({len(clean_path1)} chars): '{clean_path1}'.",
            file=sys.stderr,
        )
        sys.exit(1)
    if len(clean_path2) > 15:
        print(
            "Error: path2 exceeds maximum length of 15 characters "
            f"({len(clean_path2)} chars): '{clean_path2}'.",
            file=sys.stderr,
        )
        sys.exit(1)
    if clean_path2 and not clean_path1:
        print(
            "Error: path2 cannot be specified when path1 is empty.",
            file=sys.stderr,
        )
        sys.exit(1)

    if client is None:
        if GoogleAdsClient is None:
            sys.stderr.write("ERROR: google-ads package is not installed.\n")
            sys.exit(1)
        try:
            cfg_path = _get_config_path()
            norm_ver = _normalize_api_version(api_version)
            client = GoogleAdsClient.load_from_storage(
                path=cfg_path, version=norm_ver
            )
        except _SDK_EXCEPTIONS as exc:
            print(
                "CRITICAL ERROR: Failed to load Google Ads configuration: "
                f"{exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    if not resolved_ad_group_rn:
        ad_group_service = client.get_service("AdGroupService")
        resolved_ad_group_rn = ad_group_service.ad_group_path(
            clean_customer_id, clean_ad_group_id
        )

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

        if clean_path1:
            ad_group_ad.ad.responsive_search_ad.path1 = clean_path1
        if clean_path2:
            ad_group_ad.ad.responsive_search_ad.path2 = clean_path2

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
            "path1": clean_path1 or None,
            "path2": clean_path2 or None,
            "ad_group_ad_resource_name": ad_group_ad_rn,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                "SUCCESS (validate_only=True): Verified creation of Responsive "
                f"Search Ad ({len(resolved_headlines)} headlines, "
                f"{len(resolved_descriptions)} descriptions, "
                f"status={status_upper}) under {resolved_ad_group_rn}."
            )
        else:
            print(
                "SUCCESS: Created responsive search ad with resource_name "
                f"{ad_group_ad_rn}."
            )
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except _SDK_EXCEPTIONS as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


create_ad = create_responsive_search_ad


def main() -> None:
    """CLI entrypoint for creating a Google Ads Responsive Search Ad."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Creates a Google Ads Responsive Search Ad under an ad group via "
            "AdGroupAdService."
        )
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
        help=(
            "Full ad group resource name (e.g., 'customers/123/adGroups/789')."
        ),
    )
    parser.add_argument(
        "-v",
        "--api-version",
        "--api_version",
        dest="api_version",
        default=None,
        help="Google Ads API version (defaults to active configured version).",
    )
    parser.add_argument(
        "--final-url",
        "--final_url",
        dest="final_urls",
        action="append",
        default=None,
        help=(
            "Landing page final URL (can be specified multiple times; "
            "default: https://www.example.com)."
        ),
    )
    parser.add_argument(
        "--headline",
        dest="headlines",
        action="append",
        default=None,
        help=(
            "Headline text (specify 3 to 15 times when provided, "
            "<=30 chars each)."
        ),
    )
    parser.add_argument(
        "--description",
        dest="descriptions",
        action="append",
        default=None,
        help=(
            "Description text (specify 2 to 4 times when provided, "
            "<=90 chars each)."
        ),
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
        help="Execute live responsive search ad creation against Google Ads.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )

    args = parser.parse_args()
    try:
        args.api_version = _normalize_api_version(args.api_version)
    except ValueError as exc:
        parser.error(str(exc))
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
