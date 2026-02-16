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

"""This example gets disapproved ads reports."""

import argparse
import csv
import sys
from typing import TYPE_CHECKING, List, Any

from google.ads.googleads.errors import GoogleAdsException

if TYPE_CHECKING:
    from google.ads.googleads.client import GoogleAdsClient


def _write_to_csv(
    file_path: str, headers: List[str], response_rows: List[List[Any]]
) -> None:
    """Writes the given response rows to a CSV file.

    Args:
        file_path: The path to the CSV file to write to.
        headers: The headers for the CSV file.
        response_rows: The rows of data to write.
    """
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(headers)
        csv_writer.writerows(response_rows)
    print(f"Report written to {file_path}")


def get_all_disapproved_ads(
    client: "GoogleAdsClient", customer_id: str, output_file: str
) -> None:
    """Retrieves all disapproved ads across all campaigns and writes them to a CSV file.

    Args:
        client: An initialized GoogleAdsClient instance.
        customer_id: The client customer ID.
        output_file: The path to the CSV file to write the results to.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
          campaign.name,
          campaign.id,
          ad_group_ad.ad.id,
          ad_group_ad.ad.type,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.policy_summary.policy_topic_entries
        FROM ad_group_ad
        WHERE
          ad_group_ad.policy_summary.approval_status = DISAPPROVED"""

    stream = ga_service.search_stream(customer_id=customer_id, query=query)

    all_rows: List[List[Any]] = []
    for batch in stream:
        for result_row in batch.results:
            ad_group_ad = result_row.ad_group_ad
            ad = ad_group_ad.ad
            policy_summary = ad_group_ad.policy_summary
            campaign_name = result_row.campaign.name
            campaign_id = result_row.campaign.id

            policy_topics = []
            policy_types = []
            evidence_texts = []

            for pol_entry in policy_summary.policy_topic_entries:
                policy_topics.append(pol_entry.topic)
                policy_types.append(pol_entry.type_.name)
                for pol_evidence in pol_entry.evidences:
                    for ev_text in pol_evidence.text_list.texts:
                        evidence_texts.append(ev_text)

            all_rows.append(
                [
                    campaign_name,
                    campaign_id,
                    ad.id,
                    ad.type_.name,
                    policy_summary.approval_status.name,
                    "; ".join(policy_topics),
                    "; ".join(policy_types),
                    "; ".join(evidence_texts),
                ]
            )

    _write_to_csv(
        output_file,
        [
            "Campaign Name",
            "Campaign ID",
            "Ad ID",
            "Ad Type",
            "Approval Status",
            "Policy Topic",
            "Policy Type",
            "Evidence Text",
        ],
        all_rows,
    )


def get_disapproved_ads_for_campaign(
    client: "GoogleAdsClient",
    customer_id: str,
    campaign_id: str,
    output_file: str | None = None,
) -> None:
    """Retrieves disapproved ads for a specific campaign.

    Args:
        client: An initialized GoogleAdsClient instance.
        customer_id: The client customer ID.
        campaign_id: The ID of the campaign to check.
        output_file: Optional path to the CSV file to write the results to. If None, prints to console.
    """
    ga_service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
          ad_group_ad.ad.id,
          ad_group_ad.ad.type,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.policy_summary.policy_topic_entries,
          campaign.name
        FROM ad_group_ad
        WHERE
          campaign.id = {campaign_id}
          AND ad_group_ad.policy_summary.approval_status = DISAPPROVED"""

    stream = ga_service.search_stream(customer_id=customer_id, query=query)

    all_rows: List[List[Any]] = []
    for batch in stream:
        for result_row in batch.results:
            ad_group_ad = result_row.ad_group_ad
            ad = ad_group_ad.ad
            policy_summary = ad_group_ad.policy_summary
            campaign_name = result_row.campaign.name

            policy_topics = []
            policy_types = []
            evidence_texts = []

            for pol_entry in policy_summary.policy_topic_entries:
                policy_topics.append(pol_entry.topic)
                policy_types.append(pol_entry.type_.name)
                for pol_evidence in pol_entry.evidences:
                    for ev_text in pol_evidence.text_list.texts:
                        evidence_texts.append(ev_text)

            row_data = [
                campaign_name,
                campaign_id,
                ad.id,
                ad.type_.name,
                policy_summary.approval_status.name,
                "; ".join(policy_topics),
                "; ".join(policy_types),
                "; ".join(evidence_texts),
            ]
            all_rows.append(row_data)

            if output_file is None:
                print(
                    f"Campaign Name: {campaign_name}, Campaign ID: {campaign_id}, "
                    f"Ad ID: {ad.id}, Ad Type: {ad.type_.name}, "
                    f"Approval Status: {policy_summary.approval_status.name}, "
                    f"Policy Topic: {'; '.join(policy_topics)}, "
                    f"Policy Type: {'; '.join(policy_types)}, "
                    f"Evidence Text: {'; '.join(evidence_texts)}"
                )

    if output_file:
        _write_to_csv(
            output_file,
            [
                "Campaign Name",
                "Campaign ID",
                "Ad ID",
                "Ad Type",
                "Approval Status",
                "Policy Topic",
                "Policy Type",
                "Evidence Text",
            ],
            all_rows,
        )
    elif not all_rows:
        print(f"No disapproved ads found for campaign ID: {campaign_id}")


def main(
    client: "GoogleAdsClient",
    customer_id: str,
    report_type: str,
    output_file: str | None = None,
    campaign_id: str | None = None,
) -> None:
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        report_type: the type of report to generate ("all" or "single").
        output_file: the path to the output CSV file.
        campaign_id: the ID of the campaign to check (required for "single" report_type).
    """
    try:
        if report_type == "all":
            if not output_file:
                output_file = "saved_csv/disapproved_ads_all_campaigns.csv"
            get_all_disapproved_ads(client, customer_id, output_file)
        elif report_type == "single":
            if not campaign_id:
                raise ValueError("Campaign ID is required for 'single' report type.")
            if not output_file:
                print(
                    f"No output file specified. Printing results for campaign {campaign_id} to console."
                )
            get_disapproved_ads_for_campaign(
                client, customer_id, campaign_id, output_file
            )
        else:
            print(f"Unknown report type: {report_type}")
            sys.exit(1)
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
    except ValueError as ve:
        print(f"Error: {ve}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetches disapproved ads data.")
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
        choices=["all", "single"],
        help="The type of report to generate ('all' for all campaigns, 'single' for a specific campaign).",
    )
    parser.add_argument(
        "-o",
        "--output_file",
        type=str,
        help="Optional: The name of the CSV file to write the results to. If not specified for 'single' report type, results are printed to console.",
    )
    parser.add_argument(
        "-i",
        "--campaign_id",
        type=str,
        help="Required for 'single' report type: The ID of the campaign to check.",
    )
    args = parser.parse_args()

    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    main(
        googleads_client,
        args.customer_id,
        args.report_type,
        args.output_file,
        args.campaign_id,
    )
