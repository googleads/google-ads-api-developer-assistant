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


def _load_run_mutation_module() -> Any:
    """Loads sibling run_mutation.py for standalone financial limit checks."""
    runner_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_mutation.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_run_mutation_adgroup_check", runner_path
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise RuntimeError(f"Unable to load run_mutation module at {runner_path}")


def handle_googleads_exception(exception: Exception) -> None:
    """Prints clean, actionable details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: Ad group creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        print(f"  - {error.message}", file=sys.stderr)
        if getattr(error, "location", None):
            elems = getattr(error.location, "field_path_elements", []) or []
            for element in elems:
                print(f"    On field: {element.field_name}", file=sys.stderr)


def create_ad_group(
    customer_id: str,
    campaign_id: Optional[str] = None,
    campaign_resource_name: Optional[str] = None,
    api_version: Optional[str] = None,
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
        campaign_id: Campaign ID (or resource name) to attach the ad group to.
        campaign_resource_name: Full campaign resource name (e.g.,
          'customers/123/campaigns/456').
        api_version: Google Ads API version (defaults to active version).
        ad_group_name: Name for the new ad group.
        cpc_bid_micros: Optional default CPC bid in micros (e.g., 10_000_000 =
          $10.00).
        status: AdGroupStatusEnum name (default: 'ENABLED').
        ad_group_type: AdGroupTypeEnum name (default: 'SEARCH_STANDARD').
        validate_only: If True, validates without creating the ad group.
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
    raw_campaign_id = str(campaign_id or "").strip()
    if not resolved_campaign_rn and raw_campaign_id.startswith("customers/"):
        resolved_campaign_rn = raw_campaign_id

    if resolved_campaign_rn and not re.fullmatch(
        r"customers/\d+/campaigns/-?\d+", resolved_campaign_rn
    ):
        print(
            f"Error: Invalid campaign resource name '{resolved_campaign_rn}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    clean_campaign_id = (
        ""
        if resolved_campaign_rn
        else "".join(re.findall(r"\d+", raw_campaign_id))
    )
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

    status_upper = str(status or "ENABLED").strip().upper()
    if status_upper == "REMOVED":
        print(
            "Error: BLOCKED BY DELETION PROHIBITION: Setting ad group status "
            "to 'REMOVED' is prohibited. Use 'PAUSED' instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if status_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid ad group status '{status}'. Must be 'ENABLED' "
            "or 'PAUSED'.",
            file=sys.stderr,
        )
        sys.exit(1)

    type_upper = str(ad_group_type or "SEARCH_STANDARD").strip().upper()
    if type_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid ad_group_type '{ad_group_type}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not validate_only and cpc_bid_micros is not None:
        run_mod = _load_run_mutation_module()
        within_limits, limit_err, _ = (
            run_mod.check_financial_transaction_limits(
                operation_summary="AdGroupService.mutate_ad_groups",
                rpc_calls=[{
                    "service": "AdGroupService",
                    "method": "mutate_ad_groups",
                    "request_payload": {
                        "customer_id": clean_customer_id,
                        "operations": [
                            {"create": {"cpc_bid_micros": int(cpc_bid_micros)}}
                        ],
                    },
                }],
            )
        )
        if not within_limits:
            sys.stderr.write(f"{limit_err}\n")
            sys.exit(2)

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

    if not resolved_campaign_rn:
        campaign_service = client.get_service("CampaignService")
        resolved_campaign_rn = campaign_service.campaign_path(
            clean_customer_id, clean_campaign_id
        )

    resolved_ad_group_name = (
        ad_group_name or ""
    ).strip() or "Standard Ad Group"

    status_enum = getattr(client.enums.AdGroupStatusEnum, status_upper, None)
    if status_enum is None:
        print(
            f"Error: Unknown ad group status '{status}'.",
            file=sys.stderr,
        )
        sys.exit(1)

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
        ad_group.name = resolved_ad_group_name
        ad_group.status = status_enum
        ad_group.campaign = resolved_campaign_rn
        ad_group.type_ = type_enum

        resolved_cpc_micros: Optional[int] = None
        if cpc_bid_micros is not None:
            resolved_cpc_micros = int(cpc_bid_micros)
            ad_group.cpc_bid_micros = resolved_cpc_micros

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
            "ad_group_name": resolved_ad_group_name,
            "ad_group_status": status_upper,
            "ad_group_type": type_upper,
            "cpc_bid_micros": resolved_cpc_micros,
            "ad_group_resource_name": ad_group_rn,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                "SUCCESS (validate_only=True): Verified creation of ad group "
                f"'{resolved_ad_group_name}' ({type_upper}, {status_upper}) "
                f"under {resolved_campaign_rn}."
            )
        else:
            print(f"SUCCESS: Created ad group {ad_group_rn}.")
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except _SDK_EXCEPTIONS as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entrypoint for creating a Google Ads ad group."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Creates a Google Ads ad group under a campaign via AdGroupService."
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
        help=(
            "Full campaign resource name (e.g., 'customers/123/campaigns/456')."
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
        help="Execute live ad group creation against Google Ads.",
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
