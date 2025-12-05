# Copyright 2024 Google LLC
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

import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")

    # Query for offline_conversion_upload_client_summary
    client_summary_query = """
        SELECT
            offline_conversion_upload_client_summary.alerts,
            offline_conversion_upload_client_summary.client,
            offline_conversion_upload_client_summary.daily_summaries,
            offline_conversion_upload_client_summary.job_summaries,
            offline_conversion_upload_client_summary.last_upload_date_time,
            offline_conversion_upload_client_summary.resource_name,
            offline_conversion_upload_client_summary.status,
            offline_conversion_upload_client_summary.success_rate,
            offline_conversion_upload_client_summary.successful_event_count,
            offline_conversion_upload_client_summary.total_event_count
        FROM
            offline_conversion_upload_client_summary
    """

    # Query for offline_conversion_upload_conversion_action_summary
    conversion_action_summary_query = """
        SELECT
            offline_conversion_upload_conversion_action_summary.alerts,
            offline_conversion_upload_conversion_action_summary.conversion_action_name,
            offline_conversion_upload_conversion_action_summary.daily_summaries,
            offline_conversion_upload_conversion_action_summary.job_summaries,
            offline_conversion_upload_conversion_action_summary.resource_name,
            offline_conversion_upload_conversion_action_summary.successful_event_count,
            offline_conversion_upload_conversion_action_summary.status,
            offline_conversion_upload_conversion_action_summary.total_event_count
        FROM
            offline_conversion_upload_conversion_action_summary
    """

    try:
        # Fetch and print client summary
        client_stream = ga_service.search_stream(
            customer_id=customer_id, query=client_summary_query
        )
        print("=" * 80)
        print("Offline Conversion Upload Client Summary:")
        print("=" * 80)
        for batch in client_stream:
            for row in batch.results:
                summary = row.offline_conversion_upload_client_summary
                print(f"Resource Name: {summary.resource_name}")
                print(f"Status: {summary.status.name}")
                print(f"Total Event Count: {summary.total_event_count}")
                print(f"Successful Event Count: {summary.successful_event_count}")
                print(f"Success Rate: {summary.success_rate}")
                print(f"Last Upload Time: {summary.last_upload_date_time}")
                if summary.alerts:
                    print("Alerts:")
                    for alert in summary.alerts:
                        print(
                            f"  Error Code: {alert.error.conversion_upload_error.name}"
                        )
                if summary.daily_summaries:
                    print("Daily Summaries:")
                    for daily_summary in summary.daily_summaries:
                        print(f"  Date: {daily_summary.upload_date}")
                        print(f"  Successful Count: {daily_summary.successful_count}")
                        print(f"  Failed Count: {daily_summary.failed_count}")
                if summary.job_summaries:
                    print("Job Summaries:")
                    for job_summary in summary.job_summaries:
                        print(f"  Job ID: {job_summary.job_id}")
                        print(f"  Successful Count: {job_summary.successful_count}")
                        print(f"  Failed Count: {job_summary.failed_count}")
                        print(f"  Upload Time: {job_summary.upload_date}")
                print("-" * 80)

        # Fetch and print conversion action summary
        action_stream = ga_service.search_stream(
            customer_id=customer_id, query=conversion_action_summary_query
        )
        print("\n" + "=" * 80)
        print("Offline Conversion Upload Conversion Action Summary:")
        print("=" * 80)
        for batch in action_stream:
            for row in batch.results:
                summary = row.offline_conversion_upload_conversion_action_summary
                print(f"Resource Name: {summary.resource_name}")
                print(f"Conversion Action Name: {summary.conversion_action_name}")
                print(f"Status: {summary.status.name}")
                print(f"Total Event Count: {summary.total_event_count}")
                print(f"Successful Event Count: {summary.successful_event_count}")
                print(
                    f"Failed Event Count: {summary.total_event_count - summary.successful_event_count}"
                )
                if summary.alerts:
                    print("Alerts:")
                    for alert in summary.alerts:
                        print(
                            f"  Error Code: {alert.error.conversion_upload_error.name}"
                        )
                if summary.daily_summaries:
                    print("Daily Summaries:")
                    for daily_summary in summary.daily_summaries:
                        print(f"  Date: {daily_summary.upload_date}")
                        print(f"  Successful Count: {daily_summary.successful_count}")
                        print(f"  Failed Count: {daily_summary.failed_count}")
                if summary.job_summaries:
                    print("Job Summaries:")
                    for job_summary in summary.job_summaries:
                        print(f"  Job ID: {job_summary.job_id}")
                        print(f"  Successful Count: {job_summary.successful_count}")
                        print(f"  Failed Count: {job_summary.failed_count}")
                        print(f"  Upload Time: {job_summary.upload_date}")
                print("-" * 80)

    except GoogleAdsException as ex:
        print(
            f'Request with ID "{ex.request_id}" failed with status '
            f'"{ex.error.code().name}" and includes the following errors:'
        )
        for error in ex.failure.errors:
            print(f'\tError with message "{error.message}".')
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get offline conversion upload client and conversion action summaries."
    )
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    args = parser.parse_args()

    # The GoogleAdsClient.load_from_storage method takes the API version as a parameter.
    # The version parameter is a string that specifies the API version to be used.
    # For example, "v22".
    # This value has been user-confirmed and saved to the agent's memory.
    googleads_client = GoogleAdsClient.load_from_storage(version="v22")

    try:
        main(googleads_client, args.customer_id)
    except GoogleAdsException as ex:
        print(
            f'Request with ID "{ex.request_id}" failed with status '
            f'"{ex.error.code().name}" and includes the following errors:'
        )
        for error in ex.failure.errors:
            print(f'\tError with message "{error.message}".')
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)

