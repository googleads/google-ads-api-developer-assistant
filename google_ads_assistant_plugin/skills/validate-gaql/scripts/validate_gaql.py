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

"""GAQL Query Validator Skill.

This script performs a dry-run validation of a GAQL query using the
validate_only=True parameter. It reads the query from stdin to avoid
shell-escaping issues with complex SQL strings.
"""

import argparse
import importlib
import re
import sys
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException."""
    print(f"FAILURE: Query validation failed with Request ID {exception.request_id}")
    for error in exception.failure.errors:
        print(f"  - {error.message}")
        if error.location:
            for element in error.location.field_path_elements:
                print(f"    On field: {element.field_name}")


def validate_gaql(
    customer_id: str,
    api_version: str,
    query: str,
    client: Optional[GoogleAdsClient] = None,
) -> None:
    """Validates a GAQL query by performing a dry run against the API."""
    if client is None:
        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}")
            sys.exit(1)

    if not query:
        print("Error: No query provided.")
        sys.exit(1)

    # Static Analysis
    query_upper = query.upper()
    has_from = " FROM " in query_upper or query_upper.strip().startswith("SELECT") and "FROM" in query_upper

    # Check for forbidden OR operator in WHERE clause
    where_match = re.search(
        r"\bWHERE\b(.*?)(\bORDER\s+BY\b|\bLIMIT\b|$)",
        query_upper,
        re.DOTALL,
    )
    if where_match:
        where_clause = where_match.group(1)
        if re.search(r"\bOR\b", where_clause):
            print("FAILURE: GAQL query contains forbidden OR operator in WHERE clause.")
            print("  - GAQL does not support the OR operator. Use IN or execute separate queries instead.")
            sys.exit(1)

    # Check for forbidden aggregate functions
    agg_funcs = ["COUNT", "SUM", "AVG", "MIN", "MAX"]
    for func in agg_funcs:
        if re.search(r"\b" + func + r"\b\s*\(", query_upper):
            print(f"FAILURE: GAQL query contains forbidden aggregate function '{func}'.")
            print("  - GAQL does not support standard SQL aggregate functions.")
            sys.exit(1)

    # Check for forbidden date/time functions
    date_funcs = ["NOW", "CURRENT_DATE"]
    for func in date_funcs:
        if re.search(r"\b" + func + r"\b", query_upper):
            print(f"FAILURE: GAQL query contains forbidden date/time function '{func}'.")
            print("  - GAQL does not support SQL date/time functions like NOW() or CURRENT_DATE().")
            sys.exit(1)

    # Core date segment check
    select_match = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", query_upper, re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)
        date_segs = [
            "SEGMENTS.DATE",
            "SEGMENTS.WEEK",
            "SEGMENTS.MONTH",
            "SEGMENTS.QUARTER",
            "SEGMENTS.YEAR",
            "SEGMENTS.DAY_OF_WEEK",
        ]
        has_date_segment = any(re.search(r"\b" + seg + r"\b", select_clause) for seg in date_segs)
        if has_date_segment:
            if not where_match or not any(op in where_match.group(1) for op in [" DURING ", " BETWEEN ", " = ", " >= ", " <= "]):
                print("FAILURE: GAQL query selects a date segment but does not specify a finite date filter (DURING or BETWEEN) in the WHERE clause.")
                sys.exit(1)

    # click_view check
    if "FROM CLICK_VIEW" in query_upper:
        if not where_match:
            print("FAILURE: Queries against 'click_view' require a single-day filter on segments.date.")
            sys.exit(1)
        where_clause = where_match.group(1)
        if not re.search(r"SEGMENTS\.DATE\s*=\s*['\"][0-9]{4}-[0-9]{2}-[0-9]{2}['\"]", where_clause):
            print("FAILURE: Queries against 'click_view' require a single-day filter using equal operator (e.g., WHERE segments.date = 'YYYY-MM-DD').")
            sys.exit(1)

    # change_status check
    if "FROM CHANGE_STATUS" in query_upper:
        if not where_match:
            print("FAILURE: Queries against 'change_status' require a finite BETWEEN filter on last_change_date_time.")
            sys.exit(1)
        where_clause = where_match.group(1)
        if "LAST_CHANGE_DATE_TIME" not in where_clause or " BETWEEN " not in where_clause:
            print("FAILURE: Queries against 'change_status' require a finite BETWEEN filter on last_change_date_time.")
            sys.exit(1)
        limit_match = re.search(r"\bLIMIT\s+(\d+)", query_upper)
        if not limit_match:
            print("FAILURE: Queries against 'change_status' require a LIMIT clause.")
            sys.exit(1)
        limit_val = int(limit_match.group(1))
        if limit_val > 10000:
            print("FAILURE: Queries against 'change_status' support a maximum LIMIT of 10,000.")
            sys.exit(1)

    # Metadata query pitfalls
    if "GOOGLE_ADS_FIELD" in query_upper:
        if has_from:
            print("FAILURE: Metadata queries (google_ads_field) MUST NOT contain a FROM clause.")
            print("  - Incorrect: SELECT name FROM google_ads_field")
            print("  - Correct: SELECT name")
            sys.exit(1)
        if any(prefix in query_upper for prefix in ["GOOGLE_ADS_FIELD.", "METRICS.", "SEGMENTS."]):
            print("FAILURE: Metadata queries MUST NOT use resource/segment prefixes (e.g., use 'name', not 'google_ads_field.name').")
            sys.exit(1)

    api_version_lower = api_version.lower()
    module_path = (
        f"google.ads.googleads.{api_version_lower}.services.types.google_ads_service"
    )
    try:
        module = importlib.import_module(module_path)
        search_request_type = getattr(module, "SearchGoogleAdsRequest")
    except (ImportError, AttributeError):
        print(
            f"CRITICAL ERROR: Could not import SearchGoogleAdsRequest for {api_version}."
        )
        sys.exit(1)

    ga_service = client.get_service("GoogleAdsService")
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))

    try:
        print(f"--- [DRY RUN] Validating Query for {clean_customer_id} ---")
        request = search_request_type(
            customer_id=clean_customer_id, query=query, validate_only=True
        )
        ga_service.search(request=request)
        print("SUCCESS: GAQL query is structurally valid.")
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)


def main() -> None:
    """Parses command line arguments and calls validate_gaql."""
    parser = argparse.ArgumentParser(description="Validates a GAQL query.")
    parser.add_argument("--customer_id", required=True, help="Google Ads Customer ID.")
    parser.add_argument(
        "--api_version",
        required=True,
        help="API Version (e.g., v24).",
    )
    args = parser.parse_args()

    query = sys.stdin.read().strip()
    validate_gaql(args.customer_id, args.api_version, query)


if __name__ == "__main__":
    main()
