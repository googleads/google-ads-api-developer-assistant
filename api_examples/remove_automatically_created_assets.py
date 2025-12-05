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
from google.ads.googleads.v22.enums.asset_field_type_enum.asset_field_type import (
    AssetFieldTypeEnum,
)


def main(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: int,
    asset_resource_name: str,
    field_type: str,
):
    """Removes automatically created assets from a campaign.

    Args:
        client: The Google Ads client.
        customer_id: The ID of the customer managing the campaign.
        campaign_id: The ID of the campaign to remove assets from.
        asset_resource_name: The resource name of the asset to remove.
        field_type: The field type of the asset to remove (e.g., "HEADLINE", "DESCRIPTION").
    """
    automatically_created_asset_removal_service = client.get_service(
        "AutomaticallyCreatedAssetRemovalService"
    )
    campaign_service = client.get_service("CampaignService")

    # [START remove_automatically_created_assets]
    # To find automatically created assets, you need to query the
    # 'campaign_asset' or 'asset' resources, filtering for
    # 'asset.automatically_created = TRUE'.
    # The 'automatically_created_asset' field in the operation should be the
    # resource name of the asset you wish to remove.
    # For example: "customers/{customer_id}/assets/{asset_id}"
    # The 'asset_type' field should correspond to the type of the asset you are
    # removing (e.g., TEXT, IMAGE, VIDEO).

    try:
        field_type_enum = getattr(AssetFieldTypeEnum, field_type.upper())
    except AttributeError:
        print(
            f"Error: Invalid field type '{field_type}'. "
            f"Please use one of: {[e.name for e in AssetFieldTypeEnum if e.name not in ('UNSPECIFIED', 'UNKNOWN')]}"
        )
        sys.exit(1)

    operations = []
    operation = client.get_type("RemoveCampaignAutomaticallyCreatedAssetOperation")
    operation.campaign = campaign_service.campaign_path(customer_id, campaign_id)
    operation.asset = asset_resource_name
    operation.field_type = field_type_enum

    operations.append(operation)

    try:
        request = client.get_type("RemoveCampaignAutomaticallyCreatedAssetRequest")
        request.customer_id = customer_id
        request.operations.append(operation)  # Append the already created operation
        request.partial_failure = False  # Assuming we want to fail all if any fail
        response = automatically_created_asset_removal_service.remove_campaign_automatically_created_asset(
            request=request
        )
        print(f"Removed {len(response.results)} automatically created assets.")
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
    parser = argparse.ArgumentParser(
        description="Removes automatically created assets from a campaign."
    )
    # The following arguments are required.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "-C", "--campaign_id", type=int, required=True, help="The campaign ID."
    )
    parser.add_argument(
        "-a",
        "--asset_resource_name",
        type=str,
        required=True,
        help="The resource name of the asset to remove.",
    )
    parser.add_argument(
        "-f",
        "--field_type",
        type=str,
        required=True,
        help=(
            "The field type of the asset to remove (e.g., HEADLINE, DESCRIPTION). "
            "Refer to the AssetFieldTypeEnum documentation for possible values: "
            "https://developers.google.com/google-ads/api/reference/rpc/v22/AssetFieldTypeEnum"
        ),
    )
    args = parser.parse_args()

    # GoogleAdsClient will read the google-ads.yaml file from the home directory.
    googleads_client = GoogleAdsClient.load_from_storage(version="v22")

    main(
        googleads_client,
        args.customer_id,
        args.campaign_id,
        args.asset_resource_name,
        args.field_type,
    )