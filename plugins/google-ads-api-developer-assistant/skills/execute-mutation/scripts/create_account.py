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

"""Creates a new Google Ads client customer account under a Manager (MCC) account.

Supports both validate_only=True dry-run validation (--dry-run, default) and
live execution (--execute) under the 4-Step HITL Mutation Protocol.
"""

import argparse
import json
import os
import re
import sys
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


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints clean, actionable details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: Account creation failed with Request ID {req_id}",
        file=sys.stderr,
    )
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        print(f"  - {error.message}", file=sys.stderr)
        if getattr(error, "location", None):
            for element in getattr(error.location, "field_path_elements", []) or []:
                print(f"    On field: {element.field_name}", file=sys.stderr)


def create_account_under_mcc(
    manager_customer_id: str,
    api_version: str = "v26",
    descriptive_name: Optional[str] = None,
    currency_code: str = "USD",
    time_zone: str = "America/New_York",
    tracking_url_template: Optional[str] = None,
    final_url_suffix: Optional[str] = None,
    email_address: Optional[str] = None,
    access_role: Optional[str] = None,
    validate_only: bool = True,
    client: Optional[Any] = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Creates or validates a new client account under an MCC account.

    Args:
        manager_customer_id: The Google Ads MCC Customer ID.
        api_version: Google Ads API version (e.g., 'v26').
        descriptive_name: Human-readable name for the new account.
        currency_code: ISO 4217 currency code (e.g., 'USD').
        time_zone: IANA time zone (e.g., 'America/New_York').
        tracking_url_template: Optional tracking URL template.
        final_url_suffix: Optional final URL suffix.
        email_address: Optional email address to invite to the new account.
        access_role: Optional AccessRole enum name (e.g., 'ADMIN', 'STANDARD').
        validate_only: If True, validates the request without creating the account.
        client: Optional pre-initialized GoogleAdsClient instance.
        json_output: If True, emits structured JSON to stdout.

    Returns:
        Dictionary containing validation or creation details.
    """
    clean_mcc_id = "".join(re.findall(r"\d+", str(manager_customer_id)))
    if not clean_mcc_id:
        print(
            f"Error: Invalid manager customer ID '{manager_customer_id}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    clean_currency = str(currency_code or "").strip().upper()
    if not re.match(r"^[A-Z]{3}$", clean_currency):
        print(
            f"Error: Invalid 3-letter ISO currency code '{currency_code}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    clean_tz = str(time_zone or "").strip()
    if not clean_tz:
        print("Error: time_zone must not be empty.", file=sys.stderr)
        sys.exit(1)

    role_upper: Optional[str] = None
    if access_role is not None and str(access_role).strip():
        role_upper = str(access_role).strip().upper()
        if role_upper in ("UNSPECIFIED", "UNKNOWN"):
            print(
                f"Error: Invalid access_role '{access_role}'. Must be a concrete role (e.g., ADMIN, STANDARD, READ_ONLY).",
                file=sys.stderr,
            )
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
        except Exception as exc:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

    resolved_name = (descriptive_name or "").strip() or "New Sub-Account"

    customer_service = client.get_service("CustomerService")
    customer = client.get_type("Customer")
    customer.descriptive_name = resolved_name
    customer.currency_code = clean_currency
    customer.time_zone = clean_tz

    if tracking_url_template:
        customer.tracking_url_template = tracking_url_template
    if final_url_suffix:
        customer.final_url_suffix = final_url_suffix

    request = client.get_type("CreateCustomerClientRequest")
    request.customer_id = clean_mcc_id
    request.customer_client = customer
    request.validate_only = bool(validate_only)

    if email_address:
        request.email_address = email_address.strip()
    if role_upper:
        role_enum = getattr(client.enums.AccessRoleEnum, role_upper, None)
        if role_enum is None:
            print(
                f"Error: Unknown access_role '{access_role}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        request.access_role = role_enum

    try:
        response = customer_service.create_customer_client(request=request)
        resource_name = getattr(response, "resource_name", "") or ""
        invitation_link = getattr(response, "invitation_link", "") or ""

        result_payload: dict[str, Any] = {
            "status": "DRY_RUN_PASSED" if validate_only else "CREATED",
            "validate_only": bool(validate_only),
            "manager_customer_id": clean_mcc_id,
            "descriptive_name": resolved_name,
            "currency_code": clean_currency,
            "time_zone": clean_tz,
            "resource_name": resource_name,
        }
        if invitation_link:
            result_payload["invitation_link"] = invitation_link

        if json_output:
            print(json.dumps(result_payload, indent=2))
        elif validate_only:
            print(
                f"SUCCESS (validate_only=True): Verified creation of client account "
                f"'{resolved_name}' ({clean_currency}, {clean_tz}) under MCC {clean_mcc_id}."
            )
        else:
            print(
                f'SUCCESS: Customer created with resource name "{resource_name}" '
                f'under manager account with ID "{clean_mcc_id}".'
            )
        return result_payload
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as exc:
        print(f"CRITICAL ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """CLI entrypoint for creating a client account under an MCC."""
    parser = argparse.ArgumentParser(
        description="Creates a new Google Ads client customer account under an MCC."
    )
    parser.add_argument(
        "-m",
        "--manager-customer-id",
        "--manager_customer_id",
        "--customer-id",
        "--customer_id",
        dest="manager_customer_id",
        required=True,
        help="Google Ads Manager (MCC) Customer ID.",
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
        "--descriptive-name",
        "--descriptive_name",
        "--name",
        dest="descriptive_name",
        default=None,
        help="Descriptive name for the new client customer account.",
    )
    parser.add_argument(
        "--currency-code",
        "--currency_code",
        dest="currency_code",
        default="USD",
        help="3-letter ISO 4217 currency code (default: USD).",
    )
    parser.add_argument(
        "--time-zone",
        "--time_zone",
        dest="time_zone",
        default="America/New_York",
        help="IANA time zone (default: America/New_York).",
    )
    parser.add_argument(
        "--tracking-url-template",
        "--tracking_url_template",
        dest="tracking_url_template",
        default=None,
        help="Optional tracking URL template (e.g., '{lpurl}?device={device}').",
    )
    parser.add_argument(
        "--final-url-suffix",
        "--final_url_suffix",
        dest="final_url_suffix",
        default=None,
        help="Optional final URL suffix.",
    )
    parser.add_argument(
        "--email-address",
        "--email_address",
        dest="email_address",
        default=None,
        help="Optional email address to invite to the created account.",
    )
    parser.add_argument(
        "--access-role",
        "--access_role",
        dest="access_role",
        default=None,
        help="Optional access role for invited user (e.g., ADMIN, STANDARD, READ_ONLY).",
    )
    parser.add_argument(
        "--dry-run",
        "--dry_run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Validate only without creating the account (default: True).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live account creation against Google Ads.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Output structured JSON.",
    )

    args = parser.parse_args()
    create_account_under_mcc(
        manager_customer_id=args.manager_customer_id,
        api_version=args.api_version,
        descriptive_name=args.descriptive_name,
        currency_code=args.currency_code,
        time_zone=args.time_zone,
        tracking_url_template=args.tracking_url_template,
        final_url_suffix=args.final_url_suffix,
        email_address=args.email_address,
        access_role=args.access_role,
        validate_only=not args.execute,
        json_output=args.json,
    )


if __name__ == "__main__":
    main()
