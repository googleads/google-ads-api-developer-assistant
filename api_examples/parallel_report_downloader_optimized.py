# Copyright 2025 Google LLC
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

"""This example downloads multiple reports in parallel."""

import argparse
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Maximum number of worker threads to use for parallel downloads.
# Adjust this based on your system's capabilities and network conditions.
MAX_WORKERS = 5


def _get_date_range_strings() -> Tuple[str, str]:
    """Calculates and returns the start and end date strings for reports.

    Returns:
        A tuple containing the start date string and the end date string in
        "YYYY-MM-DD" format.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def fetch_report_threaded(
    client: GoogleAdsClient, customer_id: str, query: str, report_name: str
) -> Tuple[str, Optional[List[Any]], Optional[GoogleAdsException]]:
    """Fetches a single Google Ads API report in a separate thread.

    Args:
        client: An initialized GoogleAdsClient instance.
        customer_id: The ID of the customer to retrieve data for.
        query: The GAQL query for the report.
        report_name: A descriptive name for the report.

    Returns:
        A tuple containing:
        - report_name (str): The name of the report.
        - rows (List[Any] | None): A list of GoogleAdsRow objects if successful, None otherwise.
        - exception (GoogleAdsException | None): The exception if an error occurred, None otherwise.
    """
    googleads_service = client.get_service("GoogleAdsService")
    print(f"[{report_name}] Starting report fetch for customer {customer_id}...")
    rows = []
    exception = None
    try:
        stream = googleads_service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                rows.append(row)
        print(f"[{report_name}] Finished report fetch. Found {len(rows)} rows.")
    except GoogleAdsException as ex:
        print(
            f"[{report_name}] Request with ID '{ex.request_id}' failed with status "
            f"'{ex.error.code().name}' and includes the following errors:"
        )
        for error in ex.failure.errors:
            print(f"\tError with message '{error.message}'.")
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        exception = ex
    return report_name, rows, exception


def main(customer_ids: List[str], login_customer_id: Optional[str]) -> None:
    """Main function to run multiple reports concurrently using threads.

    Args:
        customer_ids: A list of customer IDs to run reports for.
        login_customer_id: The login customer ID to use (optional).
    """
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    if login_customer_id:
        googleads_client.login_customer_id = login_customer_id

    start_date_str, end_date_str = _get_date_range_strings()

    # Each dictionary represents a report to be run.
    # You can add more reports here.
    report_definitions = [
        {
            "name": "Campaign Performance (Last 30 Days)",
            "query": f"""
                SELECT
                    campaign.id,
                    campaign.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros
                FROM
                    campaign
                WHERE
                    segments.date BETWEEN '{start_date_str}' AND '{end_date_str}'
                ORDER BY
                    metrics.clicks DESC
                LIMIT 10
            """,
        },
        {
            "name": "Ad Group Performance (Last 30 Days)",
            "query": f"""
                SELECT
                    ad_group.id,
                    ad_group.name,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros
                FROM
                    ad_group
                WHERE
                    segments.date BETWEEN '{start_date_str}' AND '{end_date_str}'
                ORDER BY
                    metrics.clicks DESC
                LIMIT 10
            """,
        },
        {
            "name": "Keyword Performance (Last 30 Days)",
            "query": f"""
                SELECT
                    ad_group_criterion.keyword.text,
                    ad_group_criterion.keyword.match_type,
                    metrics.clicks,
                    metrics.impressions,
                    metrics.cost_micros
                FROM
                    keyword_view
                WHERE
                    segments.date BETWEEN '{start_date_str}' AND '{end_date_str}'
                ORDER BY
                    metrics.clicks DESC
                LIMIT 10
            """,
        },
    ]

    all_results: Dict[str, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for cust_id in customer_ids:
            for report_def in report_definitions:
                report_name_with_customer = (
                    f"{report_def['name']} (Customer: {cust_id})"
                )
                future = executor.submit(
                    fetch_report_threaded,
                    googleads_client,
                    cust_id,
                    report_def["query"],
                    report_name_with_customer,
                )
                futures[future] = report_name_with_customer

        for future in as_completed(futures):
            report_name_with_customer = futures[future]
            report_name, rows, exception = future.result()
            all_results[report_name_with_customer] = {
                "rows": rows,
                "exception": exception,
            }

    # Process and print all collected results
    for report_name_with_customer, result_data in all_results.items():
        rows = result_data["rows"]
        exception = result_data["exception"]

        print(f"\n--- Results for {report_name_with_customer} ---")
        if exception:
            print(f"Report failed with exception: {exception}")
        elif not rows:
            print("No data found.")
        else:
            # Print a few sample rows for demonstration
            for i, row in enumerate(rows):
                if i >= 3:  # Limit to first 3 rows for brevity
                    print(f"... ({len(rows) - 3} more rows)")
                    break
                # Generic printing for demonstration; you'd parse 'row' based on your query
                print(f"  Row {i + 1}: {row}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Downloads multiple Google Ads API reports in parallel using threads."
    )
    parser.add_argument(
        "-c",
        "--customer_ids",
        nargs="+",
        type=str,
        required=True,
        help="The Google Ads customer IDs (can provide multiple).",
    )
    parser.add_argument(
        "-l",
        "--login_customer_id",
        type=str,
        help="The login customer ID (optional).",
    )
    args = parser.parse_args()

    main(args.customer_ids, args.login_customer_id)
