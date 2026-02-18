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

"""This example gets AI Max performance reports."""

import argparse
import sys

from garf.community.google.ads import GoogleAdsApiReportFetcher
from garf.community.google.ads.api_clients import GoogleAdsApiClient
from garf.io.writers.csv_writer import CsvWriter
from google.ads.googleads.client import GoogleAdsClient

campaign_details = """
SELECT
  campaign.id AS Campaign Id,
  campaign.name AS Campaign Name,
  expanded_landing_page_view.expanded_final_url AS Expanded Landing Page URL,
  campaign.ai_max_setting.enable_ai_max AS AI Max Enabled
FROM
  expanded_landing_page_view
WHERE
  campaign.ai_max_setting.enable_ai_max = TRUE
ORDER BY
  campaign.id
"""

landing_page_matches = """
SELECT
  campaign.id AS Campaign ID,
  campaign.name AS Campaign Name,
  expanded_landing_page_view.expanded_final_url AS Expanded Landing Page URL,
  campaign.ai_max_setting.enable_ai_max AS AI Max Enabled
FROM
  expanded_landing_page_view
WHERE
  campaign.ai_max_setting.enable_ai_max = TRUE
ORDER BY
  campaign.id
"""

search_terms = """
SELECT
  campaign.id AS Campaign ID,
  campaign.name AS Campaign Name,
  ai_max_search_term_ad_combination_view.search_term AS Search Term,
  metrics.impressions AS Impressions,
  metrics.clicks AS Clicks,
  metrics.cost_micros / 1e6 AS Cost,
  metrics.conversions AS Conversions
FROM
  ai_max_search_term_ad_combination_view
WHERE
  segments.date BETWEEN '{start_date}' AND '{end_date}'
ORDER BY
  metrics.impressions DESC
"""


def main(client: "GoogleAdsClient", customer_id: str, report_type: str) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        report_type: the type of report to generate.
    """
    csv_writer = CsvWriter(destination_folder="saved_csv")
    api_client = GoogleAdsApiClient.from_googleads_client(client)
    fetcher = GoogleAdsApiReportFetcher(api_client=api_client)

    if report_type == "campaign_details":
        report = fetcher.fetch(
            campaign_details, title=report_type, account=customer_id
        )
    elif report_type == "landing_page_matches":
        report = fetcher.fetch(
            landing_page_matches, title=report_type, account=customer_id
        )
    elif report_type == "search_terms":
        report = fetcher.fetch(
            search_terms,
            title=report_type,
            account=customer_id,
            args={
                "macro": {
                    "start_date": ":YYYYMMDD-30",
                    "end_date": ":YYYYMMDD-1",
                }
            },
        )
    else:
        print(f"Unknown report type: {report_type}")
        sys.exit(1)
    csv_writer.write(report, report_type)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetches AI Max performance data."
    )
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
        choices=["campaign_details", "landing_page_matches", "search_terms"],
        help="The type of report to generate.",
    )
    args = parser.parse_args()

    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    main(googleads_client, args.customer_id, args.report_type)
