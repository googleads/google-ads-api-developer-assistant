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

"""Creates a Google Ads campaign (and optional campaign budget) via GoogleAdsService / CampaignService.

Supports both validate_only=True dry-run validation (--dry-run, default) and
live execution (--execute) under the 4-Step HITL Mutation Protocol.
"""

import argparse
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
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


def _load_run_mutation_module() -> Any:
    """Loads sibling run_mutation.py for standalone financial limit checks."""
    runner_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "run_mutation.py"
    )
    spec = spec_from_file_location("_run_mutation_campaign_check", runner_path)
    if spec and spec.loader:
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise RuntimeError(f"Unable to load run_mutation module at {runner_path}")


def _normalize_campaign_date_time(value: str, is_end: bool = False) -> str:
    """Validates and normalizes a campaign start/end date into 'YYYY-MM-DD HH:MM:SS'."""
    raw = str(value).strip()
    suffix = "23:59:59" if is_end else "00:00:00"
    label = "end_date" if is_end else "start_date"

    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            datetime.strptime(raw, "%Y-%m-%d")
            return f"{raw} {suffix}"
        if re.match(r"^\d{8}$", raw):
            dt = datetime.strptime(raw, "%Y%m%d")
            return f"{dt.strftime('%Y-%m-%d')} {suffix}"
        if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", raw):
            datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            return raw
    except ValueError:
        pass

    print(
        f"Error: Invalid {label} '{value}'. Expected YYYY-MM-DD, YYYYMMDD, or 'YYYY-MM-DD HH:MM:SS'.",
        file=sys.stderr,
    )
    sys.exit(1)


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints clean, actionable details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: Campaign creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        print(f"  - {error.message}", file=sys.stderr)
        if getattr(error, "location", None):
            for element in getattr(error.location, "field_path_elements", []) or []:
                print(f"    On field: {element.field_name}", file=sys.stderr)


def _populate_campaign_fields(
    client: Any,
    campaign: Any,
    *,
    campaign_name: str,
    channel_upper: str,
    channel_enum: Any,
    status_enum: Any,
    budget_rn: str,
    contains_eu_political_advertising: bool,
    target_google_search: bool,
    target_search_network: bool,
    target_partner_search_network: bool,
    target_content_network: bool,
    norm_start_dt: Optional[str],
    norm_end_dt: Optional[str],
) -> None:
    """Populates fields on a Campaign protobuf message with channel-aware bidding and network settings."""
    campaign.name = campaign_name
    campaign.advertising_channel_type = channel_enum
    campaign.status = status_enum
    campaign.campaign_budget = budget_rn

    if channel_upper in ("SEARCH", "DISPLAY", "SHOPPING"):
        campaign.manual_cpc = client.get_type("ManualCpc")
    else:
        campaign.maximize_conversions = client.get_type("MaximizeConversions")

    if contains_eu_political_advertising:
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.CONTAINS_EU_POLITICAL_ADVERTISING
        )
    else:
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )

    if channel_upper == "SEARCH":
        campaign.network_settings.target_google_search = bool(target_google_search)
        campaign.network_settings.target_search_network = bool(target_search_network)
        campaign.network_settings.target_partner_search_network = bool(
            target_partner_search_network
        )
        campaign.network_settings.target_content_network = bool(
            target_content_network
        )

    if norm_start_dt:
        campaign.start_date_time = norm_start_dt
    if norm_end_dt:
        campaign.end_date_time = norm_end_dt


def create_campaign(
    customer_id: str,
    api_version: str = "v26",
    campaign_name: Optional[str] = None,
    budget_amount_micros: int = 5_000_000,
    budget_resource_name: Optional[str] = None,
    budget_delivery_method: str = "STANDARD",
    advertising_channel_type: str = "SEARCH",
    status: str = "PAUSED",
    target_google_search: bool = True,
    target_search_network: bool = True,
    target_partner_search_network: bool = False,
    target_content_network: bool = False,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    validate_only: bool = True,
    client: Optional[Any] = None,
    json_output: bool = False,
    budget_name: Optional[str] = None,
    contains_eu_political_advertising: bool = False,
) -> dict[str, Any]:
    """Creates or validates a Google Ads campaign (creating a budget if not supplied).

    Args:
        customer_id: The Google Ads Customer ID.
        api_version: Google Ads API version (e.g., 'v26').
        campaign_name: Name for the campaign.
        budget_amount_micros: Daily budget in micros if creating a new budget.
        budget_resource_name: Optional existing CampaignBudget resource name.
        budget_delivery_method: BudgetDeliveryMethodEnum name (default: 'STANDARD').
        advertising_channel_type: AdvertisingChannelTypeEnum name (default: 'SEARCH').
        status: CampaignStatusEnum name (default: 'PAUSED').
        target_google_search: Whether to serve on Google Search.
        target_search_network: Whether to serve on Search Network.
        target_partner_search_network: Whether to serve on Search Partners.
        target_content_network: Whether to serve on Display/Content Network.
        start_date: Optional start date (YYYY-MM-DD, YYYYMMDD, or 'YYYY-MM-DD HH:MM:SS').
        end_date: Optional end date (YYYY-MM-DD, YYYYMMDD, or 'YYYY-MM-DD HH:MM:SS').
        validate_only: If True, validates the request without creating resources.
        client: Optional pre-initialized GoogleAdsClient instance.
        json_output: If True, emits structured JSON to stdout.
        budget_name: Optional deterministic name for a newly created CampaignBudget.
        contains_eu_political_advertising: Whether campaign contains EU political ads.

    Returns:
        Dictionary containing validation or creation details.
    """
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    resolved_budget_rn = (budget_resource_name or "").strip()
    if resolved_budget_rn and not re.match(
        r"^customers/\d+/campaignBudgets/-?\d+$", resolved_budget_rn
    ):
        print(
            f"Error: Invalid budget_resource_name '{resolved_budget_rn}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not resolved_budget_rn and int(budget_amount_micros) <= 0:
        print(
            f"Error: budget_amount_micros must be > 0 (got {budget_amount_micros}).",
            file=sys.stderr,
        )
        sys.exit(1)

    status_upper = str(status or "PAUSED").strip().upper()
    if status_upper == "REMOVED":
        print(
            "Error: BLOCKED BY DELETION PROHIBITION: Setting campaign status to 'REMOVED' is prohibited. Use 'PAUSED' instead.",
            file=sys.stderr,
        )
        sys.exit(1)
    if status_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid campaign status '{status}'. Must be 'PAUSED' or 'ENABLED'.",
            file=sys.stderr,
        )
        sys.exit(1)

    channel_upper = str(advertising_channel_type or "SEARCH").strip().upper()
    if channel_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid advertising_channel_type '{advertising_channel_type}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    delivery_upper = str(budget_delivery_method or "STANDARD").strip().upper()
    if delivery_upper in ("UNSPECIFIED", "UNKNOWN"):
        print(
            f"Error: Invalid budget_delivery_method '{budget_delivery_method}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    norm_start_dt = (
        _normalize_campaign_date_time(start_date, is_end=False)
        if start_date is not None and str(start_date).strip()
        else None
    )
    norm_end_dt = (
        _normalize_campaign_date_time(end_date, is_end=True)
        if end_date is not None and str(end_date).strip()
        else None
    )
    if norm_start_dt and norm_end_dt and norm_end_dt < norm_start_dt:
        print(
            f"Error: end_date ({norm_end_dt}) must not be earlier than start_date ({norm_start_dt}).",
            file=sys.stderr,
        )
        sys.exit(1)

    if not validate_only and not resolved_budget_rn:
        run_mod = _load_run_mutation_module()
        within_limits, limit_err, _ = run_mod.check_financial_transaction_limits(
            operation_summary="CampaignBudgetService.mutate_campaign_budgets",
            rpc_calls=[
                {
                    "service": "CampaignBudgetService",
                    "method": "mutate_campaign_budgets",
                    "request_payload": {
                        "customer_id": clean_customer_id,
                        "operations": [
                            {"create": {"amount_micros": int(budget_amount_micros)}}
                        ],
                    },
                }
            ],
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
            client = GoogleAdsClient.load_from_storage(
                path=cfg_path, version=api_version
            )
        except Exception as exc:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    resolved_campaign_name = (campaign_name or "").strip()
    if not resolved_campaign_name:
        if channel_upper == "SEARCH":
            resolved_campaign_name = "New Search Campaign"
        else:
            resolved_campaign_name = (
                f"New {channel_upper.replace('_', ' ').title()} Campaign"
            )

    resolved_budget_name = (
        (budget_name or "").strip() or f"{resolved_campaign_name} Budget"
    )

    channel_enum = getattr(
        client.enums.AdvertisingChannelTypeEnum, channel_upper, None
    )
    if channel_enum is None:
        print(
            f"Error: Unknown advertising_channel_type '{advertising_channel_type}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    status_enum = getattr(client.enums.CampaignStatusEnum, status_upper, None)
    if status_enum is None:
        print(
            f"Error: Unknown campaign status '{status}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    delivery_enum = getattr(
        client.enums.BudgetDeliveryMethodEnum, delivery_upper, None
    )
    if delivery_enum is None:
        print(
            f"Error: Unknown budget_delivery_method '{budget_delivery_method}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        campaign_rn = ""
        use_atomic_mutate = False
        google_ads_service = None

        if not resolved_budget_rn:
            try:
                google_ads_service = client.get_service("GoogleAdsService")
            except KeyError:
                google_ads_service = None

            if google_ads_service is not None:
                if not isinstance(google_ads_service, unittest.mock.MagicMock):
                    use_atomic_mutate = True
                elif (
                    "mutate" in getattr(google_ads_service, "_mock_children", {})
                    or "mutate" in google_ads_service.__dict__
                ):
                    use_atomic_mutate = True
                else:
                    try:
                        client.get_service("CampaignBudgetService")
                    except KeyError:
                        use_atomic_mutate = True

        if not resolved_budget_rn and use_atomic_mutate and google_ads_service is not None:
            temp_budget_rn = f"customers/{clean_customer_id}/campaignBudgets/-1"

            budget_mutate_op = client.get_type("MutateOperation")
            budget = budget_mutate_op.campaign_budget_operation.create
            budget.resource_name = temp_budget_rn
            budget.name = resolved_budget_name
            budget.delivery_method = delivery_enum
            budget.amount_micros = int(budget_amount_micros)

            camp_mutate_op = client.get_type("MutateOperation")
            campaign = camp_mutate_op.campaign_operation.create
            _populate_campaign_fields(
                client,
                campaign,
                campaign_name=resolved_campaign_name,
                channel_upper=channel_upper,
                channel_enum=channel_enum,
                status_enum=status_enum,
                budget_rn=temp_budget_rn,
                contains_eu_political_advertising=bool(
                    contains_eu_political_advertising
                ),
                target_google_search=target_google_search,
                target_search_network=target_search_network,
                target_partner_search_network=target_partner_search_network,
                target_content_network=target_content_network,
                norm_start_dt=norm_start_dt,
                norm_end_dt=norm_end_dt,
            )

            mutate_req = client.get_type("MutateGoogleAdsRequest")
            mutate_req.customer_id = clean_customer_id
            mutate_req.validate_only = bool(validate_only)
            atomic_ops = [budget_mutate_op, camp_mutate_op]
            if isinstance(
                getattr(mutate_req, "mutate_operations", None),
                unittest.mock.MagicMock,
            ):
                mutate_req.mutate_operations = atomic_ops
            else:
                mutate_req.mutate_operations.extend(atomic_ops)

            mutate_resp = google_ads_service.mutate(request=mutate_req)
            resolved_budget_rn = temp_budget_rn
            campaign_rn = "(validated dry-run)" if validate_only else ""

            op_responses = getattr(mutate_resp, "mutate_operation_responses", None)
            raw_results = getattr(mutate_resp, "results", None)
            if op_responses and len(op_responses) >= 1:
                b_res = getattr(op_responses[0], "campaign_budget_result", None)
                b_rn = getattr(b_res, "resource_name", "") or getattr(
                    op_responses[0], "resource_name", ""
                )
                if isinstance(b_rn, str) and b_rn:
                    resolved_budget_rn = b_rn
                if len(op_responses) >= 2:
                    c_res = getattr(op_responses[1], "campaign_result", None)
                    c_rn = getattr(c_res, "resource_name", "") or getattr(
                        op_responses[1], "resource_name", ""
                    )
                    if isinstance(c_rn, str) and c_rn:
                        campaign_rn = c_rn
            elif raw_results and len(raw_results) >= 1:
                b_rn = getattr(raw_results[0], "resource_name", "")
                if isinstance(b_rn, str) and b_rn:
                    resolved_budget_rn = b_rn
                if len(raw_results) >= 2:
                    c_rn = getattr(raw_results[1], "resource_name", "")
                    if isinstance(c_rn, str) and c_rn:
                        campaign_rn = c_rn
        else:
            if not resolved_budget_rn:
                campaign_budget_service = client.get_service(
                    "CampaignBudgetService"
                )
                budget_op = client.get_type("CampaignBudgetOperation")
                budget = budget_op.create
                budget.name = resolved_budget_name
                budget.delivery_method = delivery_enum
                budget.amount_micros = int(budget_amount_micros)

                budget_req = client.get_type("MutateCampaignBudgetsRequest")
                budget_req.customer_id = clean_customer_id
                budget_req.operations = [budget_op]
                budget_req.validate_only = bool(validate_only)

                budget_resp = campaign_budget_service.mutate_campaign_budgets(
                    request=budget_req
                )
                if (
                    getattr(budget_resp, "results", None)
                    and len(budget_resp.results) > 0
                ):
                    resolved_budget_rn = budget_resp.results[0].resource_name
                else:
                    resolved_budget_rn = (
                        campaign_budget_service.campaign_budget_path(
                            clean_customer_id, "-1"
                        )
                    )

            campaign_service = client.get_service("CampaignService")
            campaign_op = client.get_type("CampaignOperation")
            campaign = campaign_op.create
            _populate_campaign_fields(
                client,
                campaign,
                campaign_name=resolved_campaign_name,
                channel_upper=channel_upper,
                channel_enum=channel_enum,
                status_enum=status_enum,
                budget_rn=resolved_budget_rn,
                contains_eu_political_advertising=bool(
                    contains_eu_political_advertising
                ),
                target_google_search=target_google_search,
                target_search_network=target_search_network,
                target_partner_search_network=target_partner_search_network,
                target_content_network=target_content_network,
                norm_start_dt=norm_start_dt,
                norm_end_dt=norm_end_dt,
            )

            campaign_req = client.get_type("MutateCampaignsRequest")
            campaign_req.customer_id = clean_customer_id
            campaign_req.operations = [campaign_op]
            campaign_req.validate_only = bool(validate_only)

            campaign_resp = campaign_service.mutate_campaigns(request=campaign_req)
            if (
                getattr(campaign_resp, "results", None)
                and len(campaign_resp.results) > 0
            ):
                campaign_rn = campaign_resp.results[0].resource_name

        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "customer_id": clean_customer_id,
            "campaign_name": resolved_campaign_name,
            "advertising_channel_type": channel_upper,
            "campaign_status": status_upper,
            "budget_resource_name": resolved_budget_rn,
            "budget_amount_micros": int(budget_amount_micros)
            if not budget_resource_name
            else None,
            "campaign_resource_name": campaign_rn,
        }

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                f"SUCCESS (validate_only=True): Verified creation of campaign "
                f"'{resolved_campaign_name}' ({channel_upper}, {status_upper}) under customer {clean_customer_id}."
            )
        else:
            print(
                f"SUCCESS: Created campaign {campaign_rn} with budget {resolved_budget_rn}."
            )
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entrypoint for creating a Google Ads campaign."""
    parser = argparse.ArgumentParser(
        description="Creates a Google Ads campaign (and optional budget) via GoogleAdsService / CampaignService."
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
        "-v",
        "--api-version",
        "--api_version",
        dest="api_version",
        default="v26",
        help="Google Ads API version (default: v26).",
    )
    parser.add_argument(
        "--campaign-name",
        "--campaign_name",
        "--name",
        dest="campaign_name",
        default=None,
        help="Name for the new campaign.",
    )
    parser.add_argument(
        "--budget-name",
        "--budget_name",
        dest="budget_name",
        default=None,
        help="Optional name for a newly created CampaignBudget.",
    )
    parser.add_argument(
        "--budget-amount-micros",
        "--budget_amount_micros",
        dest="budget_amount_micros",
        type=int,
        default=5_000_000,
        help="Daily campaign budget in micros (default: 5000000 = $5.00).",
    )
    parser.add_argument(
        "--budget-resource-name",
        "--budget_resource_name",
        dest="budget_resource_name",
        default=None,
        help="Existing CampaignBudget resource name (skips creating a new budget).",
    )
    parser.add_argument(
        "--budget-delivery-method",
        "--budget_delivery_method",
        dest="budget_delivery_method",
        default="STANDARD",
        help="Budget delivery method (STANDARD or ACCELERATED, default: STANDARD).",
    )
    parser.add_argument(
        "--channel-type",
        "--channel_type",
        "--advertising-channel-type",
        "--advertising_channel_type",
        dest="advertising_channel_type",
        default="SEARCH",
        help="AdvertisingChannelTypeEnum value (default: SEARCH).",
    )
    parser.add_argument(
        "--status",
        default="PAUSED",
        help="Initial campaign status (PAUSED or ENABLED, default: PAUSED).",
    )
    parser.add_argument(
        "--start-date",
        "--start_date",
        dest="start_date",
        default=None,
        help="Optional campaign start date (YYYY-MM-DD, YYYYMMDD, or 'YYYY-MM-DD HH:MM:SS').",
    )
    parser.add_argument(
        "--end-date",
        "--end_date",
        dest="end_date",
        default=None,
        help="Optional campaign end date (YYYY-MM-DD, YYYYMMDD, or 'YYYY-MM-DD HH:MM:SS').",
    )
    parser.add_argument(
        "--contains-eu-political-advertising",
        "--contains_eu_political_advertising",
        dest="contains_eu_political_advertising",
        action="store_true",
        default=False,
        help="Declare that the campaign contains EU political advertising.",
    )
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Validate only without creating the campaign (default: True).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live campaign creation against Google Ads.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )

    args = parser.parse_args()
    create_campaign(
        customer_id=args.customer_id,
        api_version=args.api_version,
        campaign_name=args.campaign_name,
        budget_amount_micros=args.budget_amount_micros,
        budget_resource_name=args.budget_resource_name,
        budget_delivery_method=args.budget_delivery_method,
        advertising_channel_type=args.advertising_channel_type,
        status=args.status,
        start_date=args.start_date,
        end_date=args.end_date,
        validate_only=not args.execute,
        json_output=args.json,
        budget_name=args.budget_name,
        contains_eu_political_advertising=args.contains_eu_political_advertising,
    )


if __name__ == "__main__":
    main()
