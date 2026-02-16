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

"""This example lists PMax campaigns.

To get campaigns, run get_campaigns.py.
"""

import argparse
import sys

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(client: "GoogleAdsClient", customer_id: str) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            campaign.name,
            campaign.advertising_channel_type
        FROM
            campaign
        WHERE
            campaign.advertising_channel_type = 'PERFORMANCE_MAX'"""

    # Issues a search request using streaming.
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    try:
        for batch in response:
            for row in batch.results:
                print(
                    f'Campaign with name "{row.campaign.name}" '
                    f"is a {row.campaign.advertising_channel_type.name} campaign."
                )
    except GoogleAdsException as ex:
        print(
            f"Request with ID '{ex.request_id}' failed with status "
            f"'{ex.error.code().name}' and includes the following errors:"
        )
        for error in ex.failure.errors:
            print(f"\tError with message '{error.message}'.")
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: '{field_path_element.field_name}'")
        sys.exit(1)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(description="Lists Performance Max campaigns.")
    # The following argument(s) are required to run the example.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    args = parser.parse_args()

    try:
        main(googleads_client, args.customer_id)
    except GoogleAdsException as ex:
        print(
            f"Request with ID '{ex.request_id}' failed with status "
            f"'{ex.error.code().name}' and includes the following errors:"
        )
        for error in ex.failure.errors:
            print(f"\tError with message '{error.message}'.")
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: '{field_path_element.field_name}'")
        sys.exit(1)
