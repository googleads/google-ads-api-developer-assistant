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

"""Creates a Google Ads campaign (and optional campaign budget) via CampaignService.

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
        f"FAILURE: Campaign creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    if hasattr(exception, "failure") and hasattr(exception.failure, "errors"):
        for error in exception.failure.errors:
            print(f"  - {error.message}", file=sys.stderr)
            if getattr(error, "location", None):
                for element in error.location.field_path_elements:
                    print(f"    On field: {element.field_name}", file=sys.stderr)


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
        start_date: Optional start date (YYYY-MM-DD or YYYYMMDD).
        end_date: Optional end date (YYYY-MM-DD or YYYYMMDD).
        validate_only: If True, validates the request without creating resources.
        client: Optional pre-initialized GoogleAdsClient instance.
        json_output: If True, emits structured JSON to stdout.

    Returns:
        Dictionary containing validation or creation details.
    """
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    if not budget_resource_name and int(budget_amount_micros) <= 0:
        print(
            f"Error: budget_amount_micros must be > 0 (got {budget_amount_micros}).",
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

    if not campaign_name:
        campaign_name = f"Interplanetary Cruise {uuid.uuid4().hex[:8]}"

    channel_upper = str(advertising_channel_type or "SEARCH").strip().upper()
    channel_enum = getattr(
        client.enums.AdvertisingChannelTypeEnum, channel_upper, None
    )
    if channel_enum is None:
        print(
            f"Error: Unknown advertising_channel_type '{advertising_channel_type}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    status_upper = str(status or "PAUSED").strip().upper()
    status_enum = getattr(client.enums.CampaignStatusEnum, status_upper, None)
    if status_enum is None:
        print(
            f"Error: Unknown campaign status '{status}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    delivery_upper = str(budget_delivery_method or "STANDARD").strip().upper()
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
        resolved_budget_rn = (budget_resource_name or "").strip()
        if not resolved_budget_rn:
            campaign_budget_service = client.get_service("CampaignBudgetService")
            budget_op = client.get_type("CampaignBudgetOperation")
            budget = budget_op.create
            budget.name = f"{campaign_name} Budget {uuid.uuid4().hex[:8]}"
            budget.delivery_method = delivery_enum
            budget.amount_micros = int(budget_amount_micros)

            budget_req = client.get_type("MutateCampaignBudgetsRequest")
            budget_req.customer_id = clean_customer_id
            budget_req.operations = [budget_op]
            budget_req.validate_only = bool(validate_only)

            budget_resp = campaign_budget_service.mutate_campaign_budgets(
                request=budget_req
            )
            if getattr(budget_resp, "results", None) and len(budget_resp.results) > 0:
                resolved_budget_rn = budget_resp.results[0].resource_name
            else:
                resolved_budget_rn = campaign_budget_service.campaign_budget_path(
                    clean_customer_id, "-1"
                )

        campaign_service = client.get_service("CampaignService")
        campaign_op = client.get_type("CampaignOperation")
        campaign = campaign_op.create
        campaign.name = campaign_name
        campaign.advertising_channel_type = channel_enum
        campaign.status = status_enum
        campaign.manual_cpc = client.get_type("ManualCpc")
        campaign.campaign_budget = resolved_budget_rn
        campaign.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )

        campaign.network_settings.target_google_search = bool(target_google_search)
        campaign.network_settings.target_search_network = bool(target_search_network)
        campaign.network_settings.target_partner_search_network = bool(
            target_partner_search_network
        )
        campaign.network_settings.target_content_network = bool(
            target_content_network
        )

        if start_date:
            campaign.start_date_time = str(start_date).strip()
        if end_date:
            campaign.end_date_time = str(end_date).strip()

        campaign_req = client.get_type("MutateCampaignsRequest")
        campaign_req.customer_id = clean_customer_id
        campaign_req.operations = [campaign_op]
        campaign_req.validate_only = bool(validate_only)

        campaign_resp = campaign_service.mutate_campaigns(request=campaign_req)
        campaign_rn = ""
        if getattr(campaign_resp, "results", None) and len(campaign_resp.results) > 0:
            campaign_rn = campaign_resp.results[0].resource_name

        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "customer_id": clean_customer_id,
            "campaign_name": campaign_name,
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
                f"'{campaign_name}' ({channel_upper}, {status_upper}) under customer {clean_customer_id}."
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
        description="Creates a Google Ads campaign (and optional budget) via CampaignService."
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
        help="Optional campaign start date (YYYY-MM-DD or YYYYMMDD).",
    )
    parser.add_argument(
        "--end-date",
        "--end_date",
        dest="end_date",
        default=None,
        help="Optional campaign end date (YYYY-MM-DD or YYYYMMDD).",
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
        help="Execute live campaign creation (validate_only=False).",
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
    )


if __name__ == "__main__":
    main()
