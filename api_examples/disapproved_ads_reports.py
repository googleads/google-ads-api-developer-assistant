# Copyright 2026 Google LLC
"""Reports disapproved ads with policy topic details."""

import argparse
import csv
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str, output_file: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, ad_group_ad.ad.id,
               ad_group_ad.policy_summary.approval_status,
               ad_group_ad.policy_summary.policy_topic_entries
        FROM ad_group_ad
        WHERE ad_group_ad.policy_summary.approval_status = DISAPPROVED"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in stream:
            for row in batch.results:
                topics = [entry.topic for entry in row.ad_group_ad.policy_summary.policy_topic_entries]
                rows.append([row.campaign.id, row.campaign.name, row.ad_group_ad.ad.id,
                             row.ad_group_ad.policy_summary.approval_status.name, "; ".join(topics)])
        
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Campaign ID", "Campaign", "Ad ID", "Status", "Topics"])
            writer.writerows(rows)
        print(f"Disapproved ads report written to {output_file}")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument("-o", "--output", default="saved_csv/disapproved_ads.csv")
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version="v23")
    main(client, args.customer_id, args.output)
