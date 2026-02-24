# Copyright 2026 Google LLC
"""Optimized AI Max performance reporting."""

import argparse
import csv
from datetime import datetime, timedelta
from typing import Any, List

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def _write_to_csv(file_path: str, headers: List[str], rows: List[List[Any]]) -> None:
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    print(f"Report written to {file_path}")

def get_campaign_details(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.id, campaign.name, expanded_landing_page_view.expanded_final_url,
               campaign.ai_max_setting.enable_ai_max
        FROM expanded_landing_page_view
        WHERE campaign.ai_max_setting.enable_ai_max = TRUE
        ORDER BY campaign.id"""
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    rows = [[r.campaign.id, r.campaign.name, r.expanded_landing_page_view.expanded_final_url, r.campaign.ai_max_setting.enable_ai_max]
            for b in stream for r in b.results]
    _write_to_csv("saved_csv/ai_max_details.csv", ["ID", "Name", "URL", "Enabled"], rows)

def get_search_terms(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    query = f"""
        SELECT campaign.id, campaign.name, ai_max_search_term_ad_combination_view.search_term,
               metrics.impressions, metrics.clicks, metrics.conversions
        FROM ai_max_search_term_ad_combination_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY metrics.impressions DESC"""
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    rows = [[r.campaign.id, r.campaign.name, r.ai_max_search_term_ad_combination_view.search_term,
             r.metrics.impressions, r.metrics.clicks, r.metrics.conversions]
            for b in stream for r in b.results]
    _write_to_csv("saved_csv/ai_max_search_terms.csv", ["ID", "Name", "Term", "Impr", "Clicks", "Conv"], rows)

def main(client: GoogleAdsClient, customer_id: str, report_type: str) -> None:
    try:
        if report_type == "campaign_details":
            get_campaign_details(client, customer_id)
        elif report_type == "search_terms":
            get_search_terms(client, customer_id)
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument(
        "-r",
        "--report_type",
        choices=["campaigns", "search_terms"],
        default="campaigns",
        help="The type of AI Max report to generate.",
    )
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id, args.report_type)
