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

"""This example gets geo targets.

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
            campaign.id,
            campaign.name,
            campaign_criterion.negative,
            campaign_criterion.criterion_id
        FROM
            campaign_criterion
        WHERE
            campaign_criterion.type = 'LOCATION'"""

    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        print("Geo targets found:")
        for batch in response:
            for row in batch.results:
                campaign = row.campaign
                campaign_criterion = row.campaign_criterion
                criterion_id = campaign_criterion.criterion_id

                geo_target_constant_resource_name = f"geoTargetConstants/{criterion_id}"

                # Query the geo_target_constant resource to get its name
                geo_target_query = f"""
                    SELECT
                        geo_target_constant.name,
                        geo_target_constant.canonical_name,
                        geo_target_constant.country_code
                    FROM
                        geo_target_constant
                    WHERE
                        geo_target_constant.resource_name = '{geo_target_constant_resource_name}'"""

                geo_target_name = "Unknown"
                geo_target_canonical_name = "Unknown"
                geo_target_country_code = "Unknown"

                try:
                    geo_target_response = ga_service.search_stream(
                        customer_id=customer_id, query=geo_target_query
                    )
                    for geo_batch in geo_target_response:
                        for geo_row in geo_batch.results:
                            geo_target_name = geo_row.geo_target_constant.name
                            geo_target_canonical_name = (
                                geo_row.geo_target_constant.canonical_name
                            )
                            geo_target_country_code = (
                                geo_row.geo_target_constant.country_code
                            )
                            break  # Assuming only one result for a given resource name
                        if geo_target_name != "Unknown":
                            break
                except GoogleAdsException as geo_ex:
                    print(
                                                    f"Error retrieving geo target details for {geo_target_constant_resource_name}: {geo_ex.failure.errors[0].message}"
                        
                    )

                print(
                    f"Campaign with ID {campaign.id}, name '{campaign.name}' has geo target '{geo_target_name}' (Canonical Name: '{geo_target_canonical_name}', Country Code: '{geo_target_country_code}', Negative: {campaign_criterion.negative})"
                )
    except GoogleAdsException as ex:
        print(
            f'Request with ID "{ex.request_id}" failed with status "{ex.error.code.name}" and includes the following errors:'
        )
        for error in ex.failure.errors:
            print(f'\tError with message "{error.message}"')
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    google_ads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(
        description="Lists geo targets for all campaigns for a given customer ID."
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
