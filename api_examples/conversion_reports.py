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

"""This example gets conversion reports."""

import argparse
import csv
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException.

    Args:
        exception: an exception of type GoogleAdsException.
    """
    print(
        f'Request with ID "{exception.request_id}" failed with status '
        f'"{exception.error.code().name}" and includes the following errors:"'
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
    """Calculates the start and end dates based on provided arguments.

    Args:
        start_date_str: The start date string (YYYY-MM-DD).
        end_date_str: The end date string (YYYY-MM-DD).
        date_range_preset: A preset date range (e.g., "LAST_30_DAYS").

    Returns:
        A tuple containing the calculated start and end date strings.

    Raises:
        SystemExit: If a valid date range cannot be determined.
    """
    calculated_start_date: Optional[datetime] = None
    calculated_end_date: Optional[datetime] = None

    if date_range_preset:
        today = datetime.now()
        if date_range_preset == "LAST_7_DAYS":
            calculated_start_date = today - timedelta(days=7)
            calculated_end_date = today
        elif date_range_preset == "LAST_10_DAYS":
            calculated_start_date = today - timedelta(days=10)
            calculated_end_date = today
        elif date_range_preset == "LAST_30_DAYS":
            calculated_start_date = today - timedelta(days=30)
            calculated_end_date = today
        elif date_range_preset == "LAST_32_DAYS":
            calculated_start_date = today - timedelta(days=32)
            calculated_end_date = today
        elif date_range_preset == "LAST_MONTH":
            first_day_of_current_month = today.replace(day=1)
            calculated_end_date = first_day_of_current_month - timedelta(days=1)
            calculated_start_date = calculated_end_date.replace(day=1)
        elif date_range_preset == "LAST_6_MONTHS":
            calculated_start_date = today - timedelta(days=180)
            calculated_end_date = today
        elif date_range_preset == "LAST_YEAR":
            calculated_start_date = today - timedelta(days=365)
            calculated_end_date = today
    elif start_date_str and end_date_str:
        calculated_start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        calculated_end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

    if not calculated_start_date or not calculated_end_date:
        print("Error: A date range must be specified either by preset or custom dates.")
        sys.exit(1)

    return (
        calculated_start_date.strftime("%Y-%m-%d"),
        calculated_end_date.strftime("%Y-%m-%d"),
    )


def _process_and_output_results(
    results_data: List[Dict[str, Any]], output_format: str, output_file: str
) -> None:
    """Processes and outputs the results to console or CSV.

    Args:
        results_data: A list of dictionaries containing the report data.
        output_format: The desired output format ("console" or "csv").
        output_file: The path to the output CSV file (if output_format is "csv").
    """
    if not results_data:
        print("No data found matching the criteria.")
        return

    if output_format == "console":
        headers = list(results_data[0].keys())
        column_widths = {header: len(header) for header in headers}
        for row_data in results_data:
            for header, value in row_data.items():
                column_widths[header] = max(column_widths[header], len(str(value)))

        header_line = " | ".join(
            header.ljust(column_widths[header]) for header in headers
        )
        print(header_line)
        print("-" * len(header_line))

        for row_data in results_data:
            print(
                " | ".join(
                    str(row_data[header]).ljust(column_widths[header])
                    for header in headers
                )
            )
    elif output_format == "csv":
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = list(results_data[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results_data)
        print(f"Results successfully written to {output_file}")


def get_conversion_actions_report(
    client: "GoogleAdsClient", customer_id: str, output_file: str
) -> None:
    """Retrieves all conversion actions and writes them to a CSV file.

    Args:
        client: An initialized GoogleAdsClient instance.
        customer_id: The client customer ID.
        output_file: The path to the CSV file to write the results to.
    """
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
      conversion_action.click_through_lookback_window_days,
      conversion_action.view_through_lookback_window_days,
      conversion_action.attribution_model_settings.attribution_model,
      conversion_action.attribution_model_settings.data_driven_model_status
    FROM conversion_action
    """

    stream = ga_service.search_stream(customer_id=customer_id, query=query)

    results_data: List[Dict[str, Any]] = []
    for batch in stream:
        for row in batch.results:
            ca = row.conversion_action
            results_data.append(
                {
                    "ID": ca.id,
                    "Name": ca.name,
                    "Status": ca.status.name,
                    "Type": ca.type.name,
                    "Category": ca.category.name,
                    "Owner": ca.owner_customer,
                    "Include in Conversions Metric": ca.include_in_conversions_metric,
                    "Click-Through Lookback Window": ca.click_through_lookback_window_days,
                    "View-Through Lookback Window": ca.view_through_lookback_window_days,
                    "Attribution Model": ca.attribution_model_settings.attribution_model.name,
                    "Data-Driven Model Status": ca.attribution_model_settings.data_driven_model_status.name,
                }
            )

    _process_and_output_results(results_data, "csv", output_file)


def get_conversion_performance_report(
    client: "GoogleAdsClient",
    customer_id: str,
    output_format: str,
    output_file: str,
    start_date: Optional[str],
    end_date: Optional[str],
    date_range_preset: Optional[str],
    metrics: List[str],
    filters: List[str],
    order_by: Optional[str],
    limit: Optional[int],
) -> None:
    """Retrieves and lists Google Ads conversion performance metrics.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        output_format: the output format for the report.
        output_file: the path to the output CSV file.
        start_date: the start date of the date range to get conversion data.
        end_date: the end date of the date range to get conversion data.
        date_range_preset: a preset date range to get conversion data.
        metrics: a list of metrics to retrieve.
        filters: a list of filters to apply to the report.
        order_by: a field to order the report by.
        limit: the number of results to limit the report to.
    """
    ga_service = client.get_service("GoogleAdsService")

    start_date_str, end_date_str = _calculate_date_range(
        start_date, end_date, date_range_preset
    )

    select_fields: List[str] = ["segments.date"]
    from_resource = "campaign"

    # Determine the FROM resource and initial select fields
    if "segments.conversion_action_name" in metrics or any(
        f.startswith("conversion_action_name=") for f in filters
    ):
        from_resource = "customer"
        select_fields.append("segments.conversion_action_name")
    else:
        select_fields.extend(["campaign.id", "campaign.name"])

    metric_fields: List[str] = []

    for metric in metrics:
        if metric == "conversions":
            metric_fields.append("metrics.conversions")
        elif metric == "all_conversions":
            metric_fields.append("metrics.all_conversions")
        elif metric == "conversions_value":
            metric_fields.append("metrics.conversions_value")
        elif metric == "all_conversions_value":
            metric_fields.append("metrics.all_conversions_value")
        elif metric == "clicks":
            metric_fields.append("metrics.clicks")
        elif metric == "impressions":
            metric_fields.append("metrics.impressions")

    all_select_fields = list(set(select_fields + metric_fields))

    query_parts = [f"SELECT {', '.join(all_select_fields)} FROM {from_resource}"]

    where_clauses = [f"segments.date BETWEEN '{start_date_str}' AND '{end_date_str}'"]

    for f in filters:
        if f.startswith("conversion_action_name="):
            where_clauses.append(
                f"segments.conversion_action_name = '{f.split('=')[1]}'"
            )
        elif f.startswith("min_conversions="):
            where_clauses.append(f"metrics.conversions > {float(f.split('=')[1])}")
        elif f.startswith("campaign_id="):
            where_clauses.append(f"campaign.id = {f.split('=')[1]}")
        elif f.startswith("campaign_name_like="):
            where_clauses.append(f"campaign.name LIKE '%{f.split('=')[1]}%'")

    if where_clauses:
        query_parts.append("WHERE " + " AND ".join(where_clauses))

    if order_by:
        order_by_field = (
            f"metrics.{order_by}"
            if order_by
            in [
                "conversions",
                "all_conversions",
                "conversions_value",
                "all_conversions_value",
                "clicks",
                "impressions",
            ]
            else order_by
        )
        query_parts.append(f"ORDER BY {order_by_field} DESC")

    if limit:
        query_parts.append(f"LIMIT {limit}")

    query = " ".join(query_parts)

    # --- Execute Query and Process Results ---
    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        results_data: List[Dict[str, Any]] = []
        for batch in stream:
            for row in batch.results:
                row_data: Dict[str, Any] = {}
                if "segments.date" in all_select_fields:
                    row_data["Date"] = row.segments.date
                if "segments.conversion_action_name" in all_select_fields:
                    row_data["Conversion Action Name"] = (
                        row.segments.conversion_action_name
                    )
                if "campaign.id" in all_select_fields:
                    row_data["Campaign ID"] = row.campaign.id
                if "campaign.name" in all_select_fields:
                    row_data["Campaign Name"] = row.campaign.name
                if "metrics.conversions" in all_select_fields:
                    row_data["Conversions"] = row.metrics.conversions
                if "metrics.all_conversions" in all_select_fields:
                    row_data["All Conversions"] = row.metrics.all_conversions
                if "metrics.conversions_value" in all_select_fields:
                    row_data["Conversions Value"] = row.metrics.conversions_value
                if "metrics.all_conversions_value" in all_select_fields:
                    row_data["All Conversions Value"] = (
                        row.metrics.all_conversions_value
                    )
                if "metrics.clicks" in all_select_fields:
                    row_data["Clicks"] = row.metrics.clicks
                if "metrics.impressions" in all_select_fields:
                    row_data["Impressions"] = row.metrics.impressions

                results_data.append(row_data)

        _process_and_output_results(results_data, output_format, output_file)

    except GoogleAdsException as ex:
        handle_googleads_exception(ex)


def main(
    client: "GoogleAdsClient",
    customer_id: str,
    report_type: str,
    output_format: str,
    output_file: str,
    start_date: Optional[str],
    end_date: Optional[str],
    date_range_preset: Optional[str],
    metrics: List[str],
    filters: List[str],
    order_by: Optional[str],
    limit: Optional[int],
) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        report_type: the type of report to generate ("actions" or "performance").
        output_format: the output format for the report.
        output_file: the path to the output CSV file.
        start_date: the start date of the date range to get conversion data.
        end_date: the end date of the date range to get conversion data.
        date_range_preset: a preset date range to get conversion data.
        metrics: a list of metrics to retrieve.
        filters: a list of filters to apply to the report.
        order_by: a field to order the report by.
        limit: the number of results to limit the report to.
    """
    try:
        if report_type == "actions":
            get_conversion_actions_report(client, customer_id, output_file)
        elif report_type == "performance":
            get_conversion_performance_report(
                client,
                customer_id,
                output_format,
                output_file,
                start_date,
                end_date,
                date_range_preset,
                metrics,
                filters,
                order_by,
                limit,
            )
        else:
            print(f"Unknown report type: {report_type}")
            sys.exit(1)
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
    except ValueError as ve:
        print(f"Error: {ve}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetches Google Ads conversion data.")
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "-r",
        "--report_type",
        type=str,
        required=True,
        choices=["actions", "performance"],
        help="The type of report to generate ('actions' for conversion actions, 'performance' for conversion performance).",
    )
    parser.add_argument(
        "-o",
        "--output_format",
        type=str,
        choices=["console", "csv"],
        default="csv",
        help="Output format: 'console' or 'csv' (default).",
    )
    parser.add_argument(
        "-f",
        "--output_file",
        type=str,
        default="saved_csv/conversion_report.csv",
        help="Output CSV file name (only used with --output_format csv).",
    )
    parser.add_argument(
        "--start_date",
        type=str,
        help="Start date for the report (YYYY-MM-DD). Required if --date_range_preset is not used.",
    )
    parser.add_argument(
        "--end_date",
        type=str,
        help="End date for the report (YYYY-MM-DD). Required if --date_range_preset is not used.",
    )
    parser.add_argument(
        "--date_range_preset",
        type=str,
        choices=[
            "LAST_7_DAYS",
            "LAST_10_DAYS",
            "LAST_30_DAYS",
            "LAST_32_DAYS",
            "LAST_MONTH",
            "LAST_6_MONTHS",
            "LAST_YEAR",
        ],
        help="Preset date range (e.g., LAST_30_DAYS). Overrides --start_date and --end_date.",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        default=["conversions"],
        choices=[
            "conversions",
            "all_conversions",
            "conversions_value",
            "all_conversions_value",
            "clicks",
            "impressions",
        ],
        help="Metrics to retrieve. Default is conversions.",
    )
    parser.add_argument(
        "--filters",
        nargs="*",
        default=[],
        help="Filters to apply (e.g., conversion_action_name=Website_Sale, min_conversions=10, campaign_id=123, campaign_name_like=test).",
    )
    parser.add_argument(
        "--order_by",
        type=str,
        choices=[
            "conversions",
            "all_conversions",
            "conversions_value",
            "all_conversions_value",
            "clicks",
            "impressions",
            "segments.conversion_action_name",
            "campaign.id",
            "campaign.name",
        ],
        help="Field to order results by (e.g., conversions, conversions_value). Default is no specific order.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit the number of results.",
    )

    args = parser.parse_args()

    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    main(
        googleads_client,
        args.customer_id,
        args.report_type,
        args.output_format,
        args.output_file,
        args.start_date,
        args.end_date,
        args.date_range_preset,
        args.metrics,
        args.filters,
        args.order_by,
        args.limit,
    )
