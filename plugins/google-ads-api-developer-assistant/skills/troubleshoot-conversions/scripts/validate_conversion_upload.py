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
import math
import os
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional

try:
    from google.ads.googleads.client import GoogleAdsClient
except ImportError:
    GoogleAdsClient = None  # type: ignore

_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?$"
)
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_IDENTIFIER_HEADERS = (
    "gclid",
    "gbraid",
    "wbraid",
    "hashed_email",
    "hashed_phone_number",
)
_TIME_HEADERS = ("conversion_time", "conversion_date_time")
_CLICK_TIME_HEADERS = ("click_time", "click_date_time")
_CURRENCY_HEADERS = (
    "currency_code",
    "conversion_currency_code",
    "conversion_currency",
)


def _parse_conversion_timestamp(raw_ts: str) -> datetime:
    """Strictly validates and parses a conversion timestamp string."""
    clean = raw_ts.strip()
    if not _TIMESTAMP_RE.fullmatch(clean):
        raise ValueError(f"Invalid timestamp syntax: {raw_ts!r}")
    iso_str = clean.replace("Z", "+00:00")
    # Normalize +HHMM / -HHMM without colon if provided
    if re.search(r"[+-]\d{4}$", iso_str):
        iso_str = f"{iso_str[:-2]}:{iso_str[-2:]}"
    return datetime.fromisoformat(iso_str)


def _timestamps_ordered(click_dt: datetime, conv_dt: datetime) -> bool:
    """Returns True if conv_dt > click_dt, safely handling naive vs aware comparisons."""
    if (click_dt.tzinfo is None) == (conv_dt.tzinfo is None):
        return conv_dt > click_dt
    c_aware = (
        click_dt.replace(tzinfo=timezone.utc)
        if click_dt.tzinfo is None
        else click_dt
    )
    v_aware = (
        conv_dt.replace(tzinfo=timezone.utc) if conv_dt.tzinfo is None else conv_dt
    )
    return v_aware > c_aware


def validate_conversion_csv(
    csv_path: str,
    api_version: str,
    client: Optional[GoogleAdsClient] = None,
) -> None:
    """Validates that conversion upload records conform to formatting, PII, and time rules."""
    if not os.path.isfile(csv_path):
        print(f"ERROR: CSV file not found at '{csv_path}'.", file=sys.stderr)
        sys.exit(1)

    print(f"--- Validating Conversion Upload CSV: {csv_path} ---")
    errors_found = 0

    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = (
                {h.strip().lower(): h for h in reader.fieldnames if h is not None}
                if reader.fieldnames
                else {}
            )

            missing: List[str] = []
            present_id_cols = [h for h in _IDENTIFIER_HEADERS if h in headers]
            if not present_id_cols:
                missing.append("gclid")

            time_col_key = next((h for h in _TIME_HEADERS if h in headers), None)
            if time_col_key is None:
                missing.append("conversion_time")

            if "conversion_value" not in headers:
                missing.append("conversion_value")

            if missing:
                print(
                    f"ERROR: Missing required CSV headers: {', '.join(missing)}",
                    file=sys.stderr,
                )
                sys.exit(1)

            click_col_key = next(
                (h for h in _CLICK_TIME_HEADERS if h in headers), None
            )
            currency_col_keys = [h for h in _CURRENCY_HEADERS if h in headers]

            row_idx = 1
            for row in reader:
                row_idx += 1
                conv_time_str = (row.get(headers[time_col_key]) or "").strip()  # type: ignore[index]
                conv_dt: Optional[datetime] = None
                try:
                    conv_dt = _parse_conversion_timestamp(conv_time_str)
                except ValueError:
                    print(
                        f"  [Row {row_idx}] ERROR: Invalid conversion_time format '{conv_time_str}'. "
                        "Use 'YYYY-MM-DD HH:MM:SS-HH:MM'."
                    )
                    errors_found += 1

                if click_col_key is not None:
                    click_time_str = (row.get(headers[click_col_key]) or "").strip()
                    if click_time_str:
                        try:
                            click_dt = _parse_conversion_timestamp(click_time_str)
                            if conv_dt is not None and not _timestamps_ordered(
                                click_dt, conv_dt
                            ):
                                print(
                                    f"  [Row {row_idx}] ERROR: conversion_time '{conv_time_str}' "
                                    f"must be strictly after click_time '{click_time_str}'."
                                )
                                errors_found += 1
                        except ValueError:
                            print(
                                f"  [Row {row_idx}] ERROR: Invalid click_time format '{click_time_str}'. "
                                "Use 'YYYY-MM-DD HH:MM:SS-HH:MM'."
                            )
                            errors_found += 1

                # Validate conversion identifiers (do not skip even if timestamp had an error)
                has_any_valid_id = False
                gclid_val = (
                    (row.get(headers["gclid"]) or "").strip()
                    if "gclid" in headers
                    else ""
                )
                other_id_populated = any(
                    bool((row.get(headers[c]) or "").strip())
                    for c in present_id_cols
                    if c != "gclid"
                )

                if "gclid" in headers and (gclid_val or not other_id_populated):
                    if not gclid_val or len(gclid_val) < 10:
                        print(
                            f"  [Row {row_idx}] ERROR: GCLID is too short or empty: '{gclid_val}'"
                        )
                        errors_found += 1
                    else:
                        has_any_valid_id = True

                for braid_col in ("gbraid", "wbraid"):
                    if braid_col in headers:
                        b_val = (row.get(headers[braid_col]) or "").strip()
                        if b_val:
                            if len(b_val) < 5 or any(ch.isspace() for ch in b_val):
                                print(
                                    f"  [Row {row_idx}] ERROR: Invalid {braid_col} value: '{b_val}'"
                                )
                                errors_found += 1
                            else:
                                has_any_valid_id = True

                for pii_col in ("hashed_email", "hashed_phone_number"):
                    if pii_col in headers:
                        p_val = (row.get(headers[pii_col]) or "").strip()
                        if p_val:
                            if "@" in p_val or "+" in p_val:
                                print(
                                    f"  [Row {row_idx}] ERROR: Unhashed raw PII detected in {pii_col} "
                                    f"('{p_val}'). Must be SHA-256 hex digest (64 hex chars)."
                                )
                                errors_found += 1
                            elif not _SHA256_HEX_RE.fullmatch(p_val):
                                print(
                                    f"  [Row {row_idx}] ERROR: Invalid {pii_col} '{p_val}'. "
                                    "Expected 64-character hexadecimal SHA-256 hash."
                                )
                                errors_found += 1
                            else:
                                has_any_valid_id = True

                if "gclid" not in headers and not has_any_valid_id and not other_id_populated:
                    print(
                        f"  [Row {row_idx}] ERROR: Row has no conversion identifier "
                        f"({', '.join(present_id_cols)})."
                    )
                    errors_found += 1

                # Validate conversion_value when non-empty
                conv_val_str = (row.get(headers["conversion_value"]) or "").strip()
                if conv_val_str != "":
                    try:
                        val_num = float(conv_val_str)
                        if not math.isfinite(val_num) or val_num < 0:
                            raise ValueError("non-finite or negative")
                    except ValueError:
                        print(
                            f"  [Row {row_idx}] ERROR: Invalid conversion_value '{conv_val_str}'. "
                            "Must be a finite number >= 0."
                        )
                        errors_found += 1

                # Validate optional currency code column(s)
                for curr_col in currency_col_keys:
                    curr_val = (row.get(headers[curr_col]) or "").strip()
                    if curr_val and not _CURRENCY_RE.fullmatch(curr_val):
                        print(
                            f"  [Row {row_idx}] ERROR: Invalid {curr_col} '{curr_val}'. "
                            "Expected 3-letter uppercase ISO 4217 code (e.g., 'USD')."
                        )
                        errors_found += 1

        if errors_found == 0:
            print(
                "SUCCESS: Conversion Upload CSV parsed cleanly with valid formatting rules."
            )
        else:
            print(f"FAILURE: Pre-validation failed with {errors_found} error(s).")
            sys.exit(1)

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to parse CSV: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(description="Validates a conversion upload CSV.")
    parser.add_argument(
        "--csv_path", required=True, help="Path to the conversion CSV file."
    )
    parser.add_argument(
        "--api_version", required=True, help="API Version (e.g., v26)."
    )
    args = parser.parse_args()

    validate_conversion_csv(args.csv_path, args.api_version)


if __name__ == "__main__":
    main()
