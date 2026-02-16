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
import csv
from datetime import datetime, timedelta
import sys
from typing import List, TYPE_CHECKING

from google.ads.googleads.errors import GoogleAdsException

if TYPE_CHECKING:
  from google.ads.googleads.client import GoogleAdsClient
  from google.ads.googleads.v23.services.types.google_ads_service import (
      SearchGoogleAdsStreamResponse,
  )


def _write_to_csv(
    file_path: str,
    headers: List[str],
    response: "SearchGoogleAdsStreamResponse",
) -> None:
  """Writes the given response to a CSV file.

  Args:
      file_path: The path to the CSV file to write to.
      headers: The headers for the CSV file.
      response: The response from the Google Ads API.
  """
  with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
    csv_writer = csv.writer(csvfile)
    csv_writer.writerow(headers)

    for batch in response:
      for row in batch.results:
        csv_writer.writerow(list(row))

  print(f"Report written to {file_path}")


def get_campaign_details(client: "GoogleAdsClient", customer_id: str) -> None:
  """Gets AI Max campaign details and writes them to a CSV file.

  Args:
      client: An initialized GoogleAdsClient instance.
      customer_id: The client customer ID.
  """
  ga_service = client.get_service("GoogleAdsService")

  query = """
        SELECT
            campaign.id,
            campaign.name,
            expanded_landing_page_view.expanded_final_url,
            campaign.ai_max_setting.enable_ai_max
        FROM
            expanded_landing_page_view
        WHERE
            campaign.ai_max_setting.enable_ai_max = TRUE
        ORDER BY
            campaign.id"""

  response = ga_service.search_stream(customer_id=customer_id, query=query)

  _write_to_csv(
      "saved_csv/ai_max_campaign_details.csv",
      [
          "Campaign ID",
          "Campaign Name",
          "Expanded Landing Page URL",
          "AI Max Enabled",
      ],
      response,
  )


def get_landing_page_matches(
    client: "GoogleAdsClient", customer_id: str
) -> None:
  """Gets AI Max landing page matches and writes them to a CSV file.

  Args:
      client: An initialized GoogleAdsClient instance.
      customer_id: The client customer ID.
  """
  ga_service = client.get_service("GoogleAdsService")

  query = """
        SELECT
            campaign.id,
            campaign.name,
            expanded_landing_page_view.expanded_final_url
        FROM
            expanded_landing_page_view
        WHERE
            campaign.ai_max_setting.enable_ai_max = TRUE
        ORDER BY
            campaign.id"""

  response = ga_service.search_stream(customer_id=customer_id, query=query)

  _write_to_csv(
      "saved_csv/ai_max_landing_page_matches.csv",
      ["Campaign ID", "Campaign Name", "Expanded Landing Page URL"],
      response,
  )


def get_search_terms(client: "GoogleAdsClient", customer_id: str) -> None:
  """Gets AI Max search terms and writes them to a CSV file.

  Args:
      client: An initialized GoogleAdsClient instance.
      customer_id: The client customer ID.
  """
  ga_service = client.get_service("GoogleAdsService")

  end_date = datetime.now()
  start_date = end_date - timedelta(days=30)

  gaql_query = f"""
        SELECT
            campaign.id,
            campaign.name,
            ai_max_search_term_ad_combination_view.search_term,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM
            ai_max_search_term_ad_combination_view
        WHERE
            segments.date BETWEEN '{start_date.strftime("%Y-%m-%d")}' AND '{end_date.strftime("%Y-%m-%d")}'
        ORDER BY
            metrics.impressions DESC
    """

  stream = ga_service.search_stream(customer_id=customer_id, query=gaql_query)

  _write_to_csv(
      "saved_csv/ai_max_search_terms.csv",
      [
          "Campaign ID",
          "Campaign Name",
          "Search Term",
          "Impressions",
          "Clicks",
          "Cost (micros)",
          "Conversions",
      ],
      stream,
  )


def main(client: "GoogleAdsClient", customer_id: str, report_type: str) -> None:
  """The main method that creates all necessary entities for the example.

  Args:
      client: an initialized GoogleAdsClient instance.
      customer_id: a client customer ID.
      report_type: the type of report to generate.
  """
  try:
    if report_type == "campaign_details":
      get_campaign_details(client, customer_id)
    elif report_type == "landing_page_matches":
      get_landing_page_matches(client, customer_id)
    elif report_type == "search_terms":
      get_search_terms(client, customer_id)
    else:
      print(f"Unknown report type: {report_type}")
      sys.exit(1)
  except GoogleAdsException as ex:
    print(
        f"Request with ID '{ex.request_id}' failed with status "
        f"'{ex.error.code.name}' and includes the following errors:"
    )
    for error in ex.failure.errors:
      print(f"\tError with message '{error.message}'.")
      if error.location:
        for field_path_element in error.location.field_path_elements:
          print(f"\t\tOn field: {field_path_element.field_name}")
    sys.exit(1)


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
