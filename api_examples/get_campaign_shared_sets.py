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

"""This example gets campaign shared sets.

To create a campaign shared set, run create_campaign_shared_set.py.
"""

import argparse
import sys

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(client: GoogleAdsClient, customer_id: str) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign_shared_set.shared_set,
            shared_set.id,
            shared_set.name,
            shared_set.type
        FROM
            campaign_shared_set
        ORDER BY
            campaign.id"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        print("Campaign Shared Sets:")
        print("---------------------")
        for batch in stream:
            for row in batch.results:
                campaign = row.campaign
                shared_set = row.shared_set
                print(
                    f"Campaign ID: {campaign.id}, "
                    f"Campaign Name: {campaign.name}, "
                    f"Shared Set ID: {shared_set.id}, "
                    f"Shared Set Name: {shared_set.name}, "
                    f"Shared Set Type: {shared_set.type.name}"
                )
    except GoogleAdsException as ex:
        print(
            f"Request with ID '{ex.request_id}' failed with status "
            f"'{ex.error.code().name}' and includes the following errors:"
        )
        for error in ex.failure.errors:
            print(f"	Error with message '{error.message}'.")
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"		On field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    google_ads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(
        description="Lists campaign shared sets for a given customer ID."
    )
    # The following argument(s) are required to run the example.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    args = parser.parse_args()
    main(google_ads_client, args.customer_id)
