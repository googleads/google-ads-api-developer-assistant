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

"""This example captures a GCLID for an ad click."""

import argparse
import sys

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(
    client: GoogleAdsClient, customer_id: str, gclid: str, conversion_date_time: str
) -> None:
    """Uploads a click conversion for a given GCLID.

    Args:
        client: An initialized GoogleAdsClient instance.
        customer_id: The client customer ID.
        gclid: The GCLID for the ad click.
        conversion_date_time: The date and time of the conversion.
    """
    conversion_upload_service = client.get_service("ConversionUploadService")
    click_conversion = client.get_type("ClickConversion")
    click_conversion.gclid = gclid
    # Creates a ConversionActionService client.
    conversion_action_service = client.get_service("ConversionActionService")
    # Retrieves all conversion actions.
    response = conversion_action_service.search_conversion_actions(
        customer_id=customer_id
    )
    try:
        conversion_action = next(iter(response)).resource_name
    except StopIteration:
        print("No conversion actions found. Please create one.")
        sys.exit(1)

    click_conversion.conversion_action = conversion_action
    click_conversion.conversion_date_time = conversion_date_time
    click_conversion.conversion_value = 23.41
    click_conversion.currency_code = "USD"

    # Creates a request message.
    request = client.get_type("UploadClickConversionsRequest")
    request.customer_id = customer_id
    request.conversions.append(click_conversion)
    request.partial_failure = True
    conversion_upload_response = conversion_upload_service.upload_click_conversions(
        request=request,
    )
    print(conversion_upload_response)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Uploads a click conversion for a given GCLID."
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
        "-g",
        "--gclid",
        type=str,
        required=True,
        help="The GCLID for the ad click.",
    )
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()

    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)

    try:
        main(
            googleads_client,
            args.customer_id,
            args.gclid,
            args.conversion_date_time,
        )
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
