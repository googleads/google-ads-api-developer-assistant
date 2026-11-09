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

"""
Google Ads API - Get Recent GCLIDs Utility
Retrieves a sample of recent GCLIDs from the click_view resource.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta


def _normalize_api_version(api_version: str) -> str:
    clean = str(api_version or "").strip().lower()
    if clean and not clean.startswith("v") and clean.isdigit():
        clean = f"v{clean}"
    return clean


def _get_config_path() -> str:
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path:
        expanded_env = os.path.abspath(os.path.expanduser(config_path))
        raw_home_yaml = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
        if expanded_env != raw_home_yaml and os.path.isfile(expanded_env):
            return config_path if os.path.isfile(config_path) else expanded_env

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    candidates = [
        os.path.abspath("config/google-ads.yaml"),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath(os.path.join(script_dir, "../../../../config/google-ads.yaml")),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        if plugin_root not in sys.path and os.path.isdir(plugin_root):
            sys.path.insert(0, plugin_root)
        from config.config_init import sync_and_set_config_kv

        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore

    class GoogleAdsException(Exception):  # type: ignore[no-redef]
        pass


def get_recent_gclids(client: GoogleAdsClient, customer_id: str, date: str) -> None:
    """Queries click_view for a sample of recent GCLIDs on a specific YYYY-MM-DD date."""
    clean_cid = re.sub(r"\D", "", str(customer_id or ""))
    if not clean_cid:
        print(f"ERROR: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    clean_date = str(date or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean_date):
        print(
            f"ERROR: Invalid date '{date}'. Expected strict YYYY-MM-DD format.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        datetime.strptime(clean_date, "%Y-%m-%d")
    except ValueError:
        print(
            f"ERROR: Invalid calendar date '{date}'. Expected valid YYYY-MM-DD.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        ga_service = client.get_service("GoogleAdsService")

        query = (
            "SELECT click_view.gclid, segments.date "
            f"FROM click_view WHERE segments.date = '{clean_date}' LIMIT 10"
        )

        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = clean_cid
        search_request.query = query

        results = ga_service.search(request=search_request)

        print("Created by the Google Ads API Developer Assistant")
        print(f"{'GCLID':<40} | {'Click Date':<15}")
        print("-" * 60)

        count = 0
        for row in results:
            count += 1
            print(f"{row.click_view.gclid:<40} | {row.segments.date:<15}")

        if count == 0:
            print(f"No GCLIDs found on date '{clean_date}'.")

    except GoogleAdsException as ex:
        err_obj = getattr(ex, "error", None)
        status_name = "UNKNOWN"
        if err_obj is not None and callable(getattr(err_obj, "code", None)):
            try:
                code_val = err_obj.code()
                status_name = getattr(code_val, "name", str(code_val))
            except Exception:
                status_name = "UNKNOWN"
        print(
            f"Request failed with status '{status_name}' and includes the following errors:"
        )
        failure = getattr(ex, "failure", None)
        errors = getattr(failure, "errors", None) if failure is not None else None
        if errors:
            for error in errors:
                print(
                    f"\tError with message '{getattr(error, 'message', str(error))}'."
                )
        elif str(ex):
            print(f"\tError with message '{ex}'.")
        sys.exit(1)
    except Exception as ex:
        print(f"ERROR: Failed to retrieve recent GCLIDs: {ex}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrieve a sample of recent GCLIDs from click_view."
    )
    parser.add_argument(
        "-c", "--customer_id", required=True, help="The Google Ads customer ID."
    )
    parser.add_argument(
        "-v",
        "--api_version",
        required=True,
        help="The Google Ads API version (e.g., v26).",
    )
    parser.add_argument(
        "-d",
        "--date",
        default=(datetime.now() - timedelta(1)).strftime("%Y-%m-%d"),
        help="The date of the clicks in YYYY-MM-DD format. Defaults to yesterday.",
    )
    args = parser.parse_args()

    if GoogleAdsClient is None:
        print("CRITICAL ERROR: google-ads package is not installed.", file=sys.stderr)
        sys.exit(1)

    try:
        cfg_path = _get_config_path()
        norm_ver = _normalize_api_version(args.api_version)
        client = GoogleAdsClient.load_from_storage(path=cfg_path, version=norm_ver)
    except Exception as e:
        print(f"ERROR: Failed to initialize GoogleAdsClient: {e}", file=sys.stderr)
        sys.exit(1)

    get_recent_gclids(client, args.customer_id, args.date)


if __name__ == "__main__":
    main()
