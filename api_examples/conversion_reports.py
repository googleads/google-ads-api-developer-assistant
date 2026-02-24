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

"""Optimized example to retrieve conversion reports."""

import argparse
import csv
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException."""
    print(
        f'Request with ID "{exception.request_id}" failed with status '
        f'"{exception.error.code().name}" and includes the following errors:'
    )
    for error in exception.failure.errors:
        print(f'\tError with message "{error.message}".')
        if error.location:
            for field_path_element in error.location.field_path_elements:
                print(f"\t\tOn field: {field_path_element.field_name}")
    sys.exit(1)


def _calculate_date_range(
    start_date_str: Optional[str],
    end_date_str: Optional[str],
    date_range_preset: Optional[str],
) -> Tuple[str, str]:
    """Calculates start and end dates with support for presets and custom ranges."""
    today = datetime.now()
    if date_range_preset:
        if date_range_preset.startswith("LAST_") and date_range_preset.endswith("_DAYS"):
            try:
                days = int(date_range_preset.split("_")[1])
                start_date = today - timedelta(days=days)
                return start_date.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
            except ValueError:
                pass

        presets = {
            "LAST_MONTH": (
                (today.replace(day=1) - timedelta(days=1)).replace(day=1),
                today.replace(day=1) - timedelta(days=1),
            ),
            "LAST_YEAR": (today - timedelta(days=365), today),
        }
        if date_range_preset in presets:
            start, end = presets[date_range_preset]
            return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    if start_date_str and end_date_str:
        return start_date_str, end_date_str

    print("Error: Invalid or missing date range. Defaulting to LAST_30_DAYS.")
    return (today - timedelta(days=30)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def _process_and_output_results(
    results_data: List[Dict[str, Any]], output_format: str, output_file: str
) -> None:
    """Outputs results to console or CSV with dynamic column sizing."""
    if not results_data:
        print("No data found.")
        return

    if output_format == "console":
        headers = list(results_data[0].keys())
        widths = {h: max(len(h), max(len(str(r[h])) for r in results_data)) for h in headers}
        header_line = " | ".join(h.ljust(widths[h]) for h in headers)
        print(header_line)
        print("-" * len(header_line))
        for row in results_data:
            print(" | ".join(str(row[h]).ljust(widths[h]) for h in headers))
    elif output_format == "csv":
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=results_data[0].keys())
            writer.writeheader()
            writer.writerows(results_data)
        print(f"Results written to {output_file}")


def get_conversion_actions_report(
    client: GoogleAdsClient, customer_id: str, output_file: str
) -> None:
    """Retrieves conversion action metadata."""
    ga_service = client.get_service("GoogleAdsService")
    query = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.status,
      conversion_action.type,
      conversion_action.category,
      conversion_action.owner_customer,
      conversion_action.include_in_conversions_metric,
      conversion_action.attribution_model_settings.attribution_model
    FROM conversion_action
    WHERE conversion_action.status != 'REMOVED'
    """

    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            ca = row.conversion_action
            results.append({
                "ID": ca.id,
                "Name": ca.name,
                "Status": ca.status.name,
                "Type": ca.type.name,
                "Category": ca.category.name,
                "Attribution": ca.attribution_model_settings.attribution_model.name,
            })
    _process_and_output_results(results, "csv", output_file)


def get_conversion_performance_report(
    client: GoogleAdsClient,
    customer_id: str,
    output_format: str,
    output_file: str,
    start_date: Optional[str],
    end_date: Optional[str],
    date_range_preset: Optional[str],
    metrics: List[str],
    filters: List[str],
    limit: Optional[int],
) -> None:
    """Retrieves conversion performance metrics with mapping-based extraction."""
    ga_service = client.get_service("GoogleAdsService")
    start, end = _calculate_date_range(start_date, end_date, date_range_preset)

    resource_map = {
        "conversions": "metrics.conversions",
        "all_conversions": "metrics.all_conversions",
        "conversions_value": "metrics.conversions_value",
        "clicks": "metrics.clicks",
        "impressions": "metrics.impressions",
    }

    select_fields = ["segments.date", "campaign.id", "campaign.name"]
    from_resource = "campaign"

    if "segments.conversion_action_name" in metrics or any("conversion_action_name" in f for f in filters):
        from_resource = "customer"
        select_fields = ["segments.date", "segments.conversion_action_name"]

    metric_fields = [resource_map[m] for m in metrics if m in resource_map]
    query_fields = list(set(select_fields + metric_fields))

    query = f"SELECT {', '.join(query_fields)} FROM {from_resource} "
    query += f"WHERE segments.date BETWEEN '{start}' AND '{end}' "

    for f in filters:
        if "=" in f:
            key, val = f.split("=")
            query += f"AND {key.strip()} = '{val.strip()}' "

    query += "ORDER BY segments.date DESC "
    if limit:
        query += f"LIMIT {limit}"

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        results_data = []
        for batch in stream:
            for row in batch.results:
                data = {}
                field_mapping = {
                    "segments.date": ("Date", row.segments.date),
                    "segments.conversion_action_name": ("Action", row.segments.conversion_action_name),
                    "campaign.id": ("Campaign ID", row.campaign.id),
                    "campaign.name": ("Campaign", row.campaign.name),
                    "metrics.conversions": ("Conversions", row.metrics.conversions),
                    "metrics.all_conversions": ("All Conv", row.metrics.all_conversions),
                    "metrics.conversions_value": ("Value", row.metrics.conversions_value),
                }
                for f in query_fields:
                    if f in field_mapping:
                        name, val = field_mapping[f]
                        data[name] = val
                results_data.append(data)

        _process_and_output_results(results_data, output_format, output_file)
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversion reporting.")
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("-r", "--report_type", choices=["actions", "performance"], required=True)
    parser.add_argument("-o", "--output_format", choices=["console", "csv"], default="csv")
    parser.add_argument("-f", "--output_file", default="saved_csv/conversion_report.csv")
    parser.add_argument("--date_range_preset", default="LAST_30_DAYS")
    parser.add_argument("--metrics", nargs="+", default=["conversions"])
    parser.add_argument("--filters", nargs="*", default=[])
    parser.add_argument("-v", "--api_version", type=str, default="v23", help="The Google Ads API version.")

    args = parser.parse_args()
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)

    if args.report_type == "actions":
        get_conversion_actions_report(googleads_client, args.customer_id, args.output_file)
    else:
        get_conversion_performance_report(
            googleads_client, args.customer_id, args.output_format, args.output_file,
            None, None, args.date_range_preset, args.metrics, args.filters, args.limit
        )
