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

"""Programmatic Conversion Upload Pre-Validation Utility."""

import argparse
import csv
import os
import sys
from datetime import datetime
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient


def validate_conversion_csv(
    csv_path: str,
    api_version: str,
    client: Optional[GoogleAdsClient] = None,
) -> None:
    """Validates that conversion upload records conform to logical time rules."""
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found at '{csv_path}'.", file=sys.stderr)
        sys.exit(1)

    print(f"--- Validating Conversion Upload CSV: {csv_path} ---")
    errors_found = 0

    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            # Check for required headers
            required_headers = ["gclid", "conversion_time", "conversion_value"]
            # Support case-insensitive match
            headers = {h.lower(): h for h in reader.fieldnames} if reader.fieldnames else {}
            
            missing = [h for h in required_headers if h not in headers]
            if missing:
                print(f"ERROR: Missing required CSV headers: {', '.join(missing)}", file=sys.stderr)
                sys.exit(1)

            row_idx = 1
            for row in reader:
                row_idx += 1
                gclid = row[headers["gclid"]]
                conv_time_str = row[headers["conversion_time"]]
                
                # Validate date format
                try:
                    # Google Ads API accepts YYYY-MM-DD HH:MM:SS+TZ format
                    # We extract the date portion YYYY-MM-DD
                    date_part = conv_time_str.split(" ")[0]
                    _ = datetime.strptime(date_part, "%Y-%m-%d")
                except Exception:
                    print(f"  [Row {row_idx}] ERROR: Invalid conversion_time format '{conv_time_str}'. Use 'YYYY-MM-DD HH:MM:SS-HH:MM'.")
                    errors_found += 1
                    continue

                # A basic GCLID upload rule: GCLIDs must be alphanumeric and not placeholders
                if not gclid or len(gclid) < 10:
                    print(f"  [Row {row_idx}] ERROR: GCLID is too short or empty: '{gclid}'")
                    errors_found += 1

        if errors_found == 0:
            print("SUCCESS: Conversion Upload CSV parsed cleanly with valid formatting rules.")
        else:
            print(f"FAILURE: Pre-validation failed with {errors_found} error(s).")
            sys.exit(1)

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to parse CSV: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Validates a conversion upload CSV.")
    parser.add_argument("--csv_path", required=True, help="Path to the conversion CSV file.")
    parser.add_argument("--api_version", required=True, help="API Version (e.g., v24).")
    args = parser.parse_args()

    validate_conversion_csv(args.csv_path, args.api_version)


if __name__ == "__main__":
    main()
