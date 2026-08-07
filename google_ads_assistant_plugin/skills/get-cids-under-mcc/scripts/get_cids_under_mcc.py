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

"""Skill script to retrieve all child customer accounts under an MCC."""

import argparse
import csv
import os
import re
import sys
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException."""
    print(
        f"FAILURE: API call failed with Request ID {exception.request_id}",
        file=sys.stderr,
    )
    for error in exception.failure.errors:
        print(f"  - {error.message}", file=sys.stderr)
        if error.location:
            for element in error.location.field_path_elements:
                print(f"    On field: {element.field_name}", file=sys.stderr)


def get_cids_under_mcc(
    customer_id: str,
    api_version: str,
    client: Optional[GoogleAdsClient] = None,
) -> list[tuple[str, int, bool]]:
    """Retrieves all child customer accounts under an MCC as a list of tuples."""
    if client is None:
        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception as e:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            customer_client.id,
            customer_client.level,
            customer_client.manager
        FROM customer_client
        WHERE customer_client.level > 0
        ORDER BY customer_client.level, customer_client.id
    """

    results = []
    try:
        stream = ga_service.search_stream(customer_id=clean_customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                cc = row.customer_client
                cid = str(cc.id)
                level = int(cc.level)
                is_mcc = bool(cc.manager)
                results.append((cid, level, is_mcc))
        return results
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parses command line arguments or prompts user, then calls get_cids."""
    parser = argparse.ArgumentParser(
        description="Retrieves child customer accounts under an MCC."
    )
    parser.add_argument(
        "--customer_id",
        help="Google Ads MCC Customer ID.",
    )
    parser.add_argument(
        "--api_version",
        required=True,
        help="API Version (e.g., v24).",
    )
    parser.add_argument(
        "--save_csv",
        action="store_true",
        default=False,
        help="If set, saves the results to a CSV file in saved/csv/.",
    )
    parser.add_argument(
        "--print_cids",
        action="store_true",
        default=False,
        help="If set, prints the detailed table of child accounts to the console.",
    )
    args = parser.parse_args()

    customer_id = args.customer_id
    if not customer_id:
        try:
            customer_id = input("Please enter the MCC Customer ID: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nError: No MCC Customer ID provided.", file=sys.stderr)
            sys.exit(1)

    if not customer_id:
        print("Error: No MCC Customer ID provided.", file=sys.stderr)
        sys.exit(1)

    clean_id = "".join(re.findall(r"\d+", str(customer_id)))
    cids = get_cids_under_mcc(customer_id, args.api_version)

    if args.save_csv:
        csv_dir = os.path.join(os.getcwd(), "saved", "csv")
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, f"cids_under_mcc_{clean_id}.csv")

        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Customer ID", "Level", "Is MCC"])
                writer.writerows(cids)
            print(f"SUCCESS: Results saved to {csv_path}")
        except Exception as e:
            print(f"Error saving CSV file: {e}", file=sys.stderr)
            sys.exit(1)

    if args.print_cids:
        print(f"Child accounts under MCC {clean_id}:")
        print(f"{'Customer ID':<15} {'Level':<7} {'Is MCC':<8}")
        print("-" * 32)
        for cid, level, is_mcc in cids:
            is_mcc_str = "Yes" if is_mcc else "No"
            print(f"{cid:<15} {level:<7} {is_mcc_str:<8}")
        if not cids:
            print("No child accounts found.")

    if not args.save_csv and not args.print_cids:
        print(f"Found {len(cids)} child accounts under MCC {clean_id}.")


if __name__ == "__main__":
    main()
