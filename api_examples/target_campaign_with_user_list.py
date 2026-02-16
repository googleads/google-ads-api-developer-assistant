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

"""This example targets a user list to a campaign.

To get campaigns, run get_campaigns.py.
To get user lists, run get_user_lists.py.
"""

import argparse
import sys

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(
    client: GoogleAdsClient, customer_id: str, campaign_id: str, user_list_id: str
) -> None:
    """Adds a campaign criterion to target a user list to a campaign.

    Args:
        client: The Google Ads client.
        customer_id: The customer ID for which to add the campaign criterion.
        campaign_id: The ID of the campaign to target.
        user_list_id: The ID of the user list to target.
    """
    campaign_criterion_service = client.get_service("CampaignCriterionService")

    # Create a campaign criterion operation.
    campaign_criterion_operation = client.get_type("CampaignCriterionOperation")
    campaign_criterion = campaign_criterion_operation.create

    # Set the campaign resource name.
    campaign_criterion.campaign = client.get_service("CampaignService").campaign_path(
        customer_id, campaign_id
    )

    # Set the user list resource name.
    campaign_criterion.user_list.user_list = client.get_service(
        "UserListService"
    ).user_list_path(customer_id, user_list_id)

    try:
        # Add the campaign criterion.
        campaign_criterion_response = (
            campaign_criterion_service.mutate_campaign_criteria(
                customer_id=customer_id,
                operations=[campaign_criterion_operation],
            )
        )
        print(
            "Added campaign criterion with resource name: "
            f"'{campaign_criterion_response.results[0].resource_name}'"
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
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    google_ads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(
        description="Adds a campaign criterion to target a user list to a campaign."
    )
    # The following argument(s) are required to run the example.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "-C",
        "--campaign_id",
        type=str,
        required=True,
        help="The ID of the campaign to target.",
    )
    parser.add_argument(
        "-u",
        "--user_list_id",
        type=str,
        required=True,
        help="The ID of the user list to target.",
    )
    args = parser.parse_args()

    try:
        main(
            google_ads_client,
            args.customer_id,
            args.campaign_id,
            args.user_list_id,
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
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)
