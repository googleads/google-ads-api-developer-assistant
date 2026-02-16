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

"""This example gets the change history of a campaign.

To get campaigns, run get_campaigns.py.
"""

import argparse
import sys
from datetime import datetime, timedelta

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException.

    Args:
        exception: an exception of type GoogleAdsException.
    """
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


def main(
    client: "GoogleAdsClient",
    customer_id: str,
    start_date: str,
    end_date: str,
) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        start_date: the start date of the date range to get change history.
        end_date: the end date of the date range to get change history.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            change_status.resource_name,
            change_status.last_change_date_time,
            change_status.resource_type,
            change_status.resource_status
        FROM
            change_status
        WHERE
            change_status.last_change_date_time BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY
            change_status.last_change_date_time DESC
        LIMIT 10000
    """

    print(
        f"Retrieving change history for customer ID: {customer_id} from {start_date} to {end_date}"
    )
    print("-" * 80)

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        found_changes = False
        for batch in stream:
            for row in batch.results:
                found_changes = True
                change = row.change_status
                print(f"Change Date/Time: {change.last_change_date_time}")
                print(f"  Resource Type: {change.resource_type.name}")
                print(f"  Resource Name: {change.resource_name}")
                print(f"  Resource Status: {change.resource_status.name}")
                print("-" * 80)

        if not found_changes:
            print("No changes found for the specified date range.")

    except GoogleAdsException as ex:
        handle_googleads_exception(ex)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(description="Retrieves Google Ads change history.")
    # The following argument(s) are required to run the example.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "--start_date",
        type=str,
        help="Start date for the change history (YYYY-MM-DD). Defaults to 7 days ago.",
    )
    parser.add_argument(
        "--end_date",
        type=str,
        help="End date for the change history (YYYY-MM-DD). Defaults to today.",
    )

    args = parser.parse_args()

    # Calculate default dates if not provided
    today = datetime.now().date()
    if not args.end_date:
        args.end_date = today.strftime("%Y-%m-%d")
    if not args.start_date:
        args.start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    main(
        googleads_client,
        args.customer_id,
        args.start_date,
        args.end_date,
    )
