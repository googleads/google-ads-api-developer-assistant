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

"""Skill script to retrieve all child customer accounts under an MCC."""

import argparse
import builtins
import csv
import json
import os
import re
import sys
from typing import Any, Optional

_ORIG_INPUT = builtins.input

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore

    class GoogleAdsException(Exception):  # type: ignore[no-redef]
        pass


class ChildAccountRow(tuple):
    """3-tuple (customer_id, level, is_mcc) carrying optional descriptive_name and status metadata."""

    descriptive_name: str
    status: str

    def __new__(
        cls,
        customer_id: str,
        level: int,
        is_mcc: bool,
        descriptive_name: str = "",
        status: str = "",
    ) -> "ChildAccountRow":
        obj = super().__new__(cls, (customer_id, level, is_mcc))
        obj.descriptive_name = descriptive_name
        obj.status = status
        return obj


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException."""
    req_id = getattr(exception, "request_id", "N/A")
    print(
        f"FAILURE: API call failed with Request ID {req_id}",
        file=sys.stderr,
    )
    failure = getattr(exception, "failure", None)
    for error in getattr(failure, "errors", []) or []:
        print(f"  - {error.message}", file=sys.stderr)
        if getattr(error, "location", None):
            for element in getattr(error.location, "field_path_elements", []) or []:
                print(f"    On field: {element.field_name}", file=sys.stderr)


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


def get_cids_under_mcc(
    customer_id: str,
    api_version: str = "v26",
    client: Optional[Any] = None,
) -> list[tuple[str, int, bool]]:
    """Retrieves all child customer accounts under an MCC as a list of tuples."""
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id or "")))
    if not clean_customer_id:
        print(f"Error: Invalid customer ID '{customer_id}'.", file=sys.stderr)
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
        except Exception as e:
            print(
                f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            customer_client.id,
            customer_client.descriptive_name,
            customer_client.level,
            customer_client.manager,
            customer_client.status
        FROM customer_client
        WHERE customer_client.level > 0
        ORDER BY customer_client.level, customer_client.id
    """

    results: list[tuple[str, int, bool]] = []
    try:
        stream = ga_service.search_stream(customer_id=clean_customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                cc = row.customer_client
                cid = str(cc.id)
                level = int(cc.level)
                is_mcc = bool(cc.manager)
                raw_desc = getattr(cc, "descriptive_name", None)
                desc_name = raw_desc if isinstance(raw_desc, str) else ""
                raw_status = getattr(cc, "status", None)
                if isinstance(raw_status, str):
                    status_str = raw_status
                elif isinstance(getattr(raw_status, "name", None), str):
                    status_str = raw_status.name
                else:
                    status_str = ""
                results.append(
                    ChildAccountRow(cid, level, is_mcc, desc_name, status_str)
                )
        return results
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _extract_row_fields(row: Any) -> tuple[str, int, bool, str, str]:
    """Extracts (cid, level, is_mcc, descriptive_name, status) from a ChildAccountRow or plain tuple."""
    cid, level, is_mcc = str(row[0]), int(row[1]), bool(row[2])
    desc_name = getattr(row, "descriptive_name", "")
    if not isinstance(desc_name, str):
        desc_name = ""
    if not desc_name and len(row) > 3 and isinstance(row[3], str):
        desc_name = row[3]

    status_str = getattr(row, "status", "")
    if not isinstance(status_str, str):
        status_str = ""
    if not status_str and len(row) > 4 and isinstance(row[4], str):
        status_str = row[4]

    return cid, level, is_mcc, desc_name, status_str


def main() -> None:
    """Parses command line arguments or prompts user, then calls get_cids_under_mcc."""
    parser = argparse.ArgumentParser(
        description="Retrieves child customer accounts under an MCC."
    )
    parser.add_argument(
        "-c",
        "--customer-id",
        "--customer_id",
        dest="customer_id",
        help="Google Ads MCC Customer ID.",
    )
    parser.add_argument(
        "-v",
        "--api-version",
        "--api_version",
        dest="api_version",
        default="v26",
        help="API Version (default: v26).",
    )
    parser.add_argument(
        "--save-csv",
        "--save_csv",
        dest="save_csv",
        action="store_true",
        default=False,
        help="If set, saves the results to a CSV file in ./saved/data/.",
    )
    parser.add_argument(
        "--print-cids",
        "--print_cids",
        dest="print_cids",
        action="store_true",
        default=False,
        help="If set, prints the detailed table of child accounts to the console.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="If set, outputs child accounts in structured JSON format.",
    )
    args = parser.parse_args()

    customer_id = args.customer_id
    if not customer_id:
        if not sys.stdin.isatty() and builtins.input is _ORIG_INPUT:
            print(
                "Error: No MCC Customer ID provided (non-interactive stdin). Pass --customer-id.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            customer_id = input("Please enter the MCC Customer ID: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nError: No MCC Customer ID provided.", file=sys.stderr)
            sys.exit(1)

    if not customer_id or not str(customer_id).strip():
        print("Error: No MCC Customer ID provided.", file=sys.stderr)
        sys.exit(1)

    clean_id = "".join(re.findall(r"\d+", str(customer_id)))
    cids = get_cids_under_mcc(customer_id, args.api_version)
    extracted = [_extract_row_fields(r) for r in cids]
    has_names = any(item[3] for item in extracted)
    has_status = any(item[4] for item in extracted)

    csv_path: Optional[str] = None
    if args.save_csv:
        csv_dir = os.path.abspath(os.path.join("saved", "data"))
        os.makedirs(csv_dir, exist_ok=True)
        csv_path = os.path.join(csv_dir, f"cids_under_mcc_{clean_id}.csv")

        try:
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = ["Customer ID", "Level", "Is MCC"]
                if has_names:
                    headers.append("Descriptive Name")
                if has_status:
                    headers.append("Status")
                writer.writerow(headers)
                for cid, level, is_mcc, desc_name, status_str in extracted:
                    row_vals: list[Any] = [cid, level, is_mcc]
                    if has_names:
                        row_vals.append(desc_name)
                    if has_status:
                        row_vals.append(status_str)
                    writer.writerow(row_vals)
            if not args.json:
                print(f"SUCCESS: Results saved to {csv_path}")
        except Exception as e:
            print(f"Error saving CSV file: {e}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        child_dicts: list[dict[str, Any]] = []
        for cid, level, is_mcc, desc_name, status_str in extracted:
            entry: dict[str, Any] = {
                "customer_id": cid,
                "level": level,
                "is_mcc": is_mcc,
                "descriptive_name": desc_name,
            }
            if status_str:
                entry["status"] = status_str
            child_dicts.append(entry)
        payload: dict[str, Any] = {
            "mcc_customer_id": clean_id,
            "total_child_accounts": len(cids),
            "child_accounts": child_dicts,
        }
        if csv_path:
            payload["csv_path"] = csv_path
        print(json.dumps(payload, indent=2))
        return

    if args.print_cids:
        print(f"Child accounts under MCC {clean_id}:")
        if has_names:
            header_fmt = f"{'Customer ID':<15} {'Level':<7} {'Is MCC':<8} {'Descriptive Name'}"
            print(header_fmt)
            print("-" * 56)
            for cid, level, is_mcc, desc_name, status_str in extracted:
                is_mcc_str = "Yes" if is_mcc else "No"
                suffix = f" ({status_str})" if status_str else ""
                print(f"{cid:<15} {level:<7} {is_mcc_str:<8} {desc_name}{suffix}")
        else:
            print(f"{'Customer ID':<15} {'Level':<7} {'Is MCC':<8}")
            print("-" * 32)
            for cid, level, is_mcc, _, _ in extracted:
                is_mcc_str = "Yes" if is_mcc else "No"
                print(f"{cid:<15} {level:<7} {is_mcc_str:<8}")
        if not cids:
            print("No child accounts found.")

    if not args.save_csv and not args.print_cids:
        print(f"Found {len(cids)} child accounts under MCC {clean_id}.")


if __name__ == "__main__":
    main()
