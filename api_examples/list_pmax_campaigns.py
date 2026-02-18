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

from garf.community.google.ads import GoogleAdsApiReportFetcher
from garf.community.google.ads.api_clients import GoogleAdsApiClient
from garf.io.writers.console_writer import ConsoleWriter
from google.ads.googleads.client import GoogleAdsClient

query = """
SELECT
  campaign.name AS Campaign Name,
  campaign.advertising_channel_type AS Campaign Type
FROM
  campaign
WHERE
  campaign.advertising_channel_type = PERFORMANCE_MAX
"""

if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(
        description="Lists Performance Max campaigns."
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

    console_writer = ConsoleWriter()
    api_client = GoogleAdsApiClient.from_googleads_client(googleads_client)
    fetcher = GoogleAdsApiReportFetcher(api_client=api_client)

    report = fetcher.fetch(query, account=args.customer_id)

    console_writer.write(report, "pmax_campaigns")
