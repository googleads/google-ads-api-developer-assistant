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
import sys
from datetime import datetime, timedelta
from typing import Optional

def _get_config_path() -> str:
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path and os.path.isfile(config_path):
        return config_path

    candidates = [
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"),
        os.path.abspath("config/google-ads.yaml"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../config/google-ads.yaml")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../config/google-ads.yaml")),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
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
    GoogleAdsException = Exception  # type: ignore


def get_recent_gclids(client: GoogleAdsClient, customer_id: str, date: str) -> None:
    """Queries click_view for a sample of recent GCLIDs on a specific date."""
    try:
        ga_service = client.get_service("GoogleAdsService")
        
        query = f"""
            SELECT 
                click_view.gclid, 
                segments.date 
            FROM click_view 
            WHERE 
                segments.date = '{date}' 
            LIMIT 10
        """
        
        search_request = client.get_type("SearchGoogleAdsRequest")
        search_request.customer_id = customer_id
        search_request.query = query
        
        results = ga_service.search(request=search_request)
        
        print(f"{'GCLID':<40} | {'Click Date':<15}")
        print("-" * 60)
        
        count = 0
        for row in results:
            count += 1
            print(f"{row.click_view.gclid:<40} | {row.segments.date:<15}")
            
        if count == 0:
            print(f"No GCLIDs found on date '{date}'.")
            
    except GoogleAdsException as ex:
        print(f"Request failed with status '{ex.error.code().name}' and includes the following errors:")
        for error in ex.failure.errors:
            print(f"\tError with message '{error.message}'.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieve a sample of recent GCLIDs from click_view.")
    parser.add_argument("-c", "--customer_id", required=True, help="The Google Ads customer ID.")
    parser.add_argument("-v", "--api_version", required=True, help="The Google Ads API version (e.g., v24).")
    parser.add_argument(
        "-d", 
        "--date", 
        default=(datetime.now() - timedelta(1)).strftime('%Y-%m-%d'), 
        help="The date of the clicks in YYYY-MM-DD format. Defaults to yesterday."
    )
    args = parser.parse_args()

    try:
        cfg_path = _get_config_path()
        client = GoogleAdsClient.load_from_storage(path=cfg_path, version=args.api_version)
    except Exception as e:
        print(f"ERROR: Failed to initialize GoogleAdsClient: {e}")
        sys.exit(1)

    get_recent_gclids(client, args.customer_id, args.date)


if __name__ == "__main__":
    main()
