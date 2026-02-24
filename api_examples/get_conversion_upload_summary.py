# Copyright 2026 Google LLC
"""Summarizes offline conversion uploads with mandatory calculation logic."""

import argparse
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT offline_conversion_upload_client_summary.client,
               offline_conversion_upload_client_summary.status,
               offline_conversion_upload_client_summary.successful_event_count,
               offline_conversion_upload_client_summary.total_event_count,
               offline_conversion_upload_client_summary.daily_summaries
        FROM offline_conversion_upload_client_summary"""

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                s = row.offline_conversion_upload_client_summary
                print(f"Client: {s.client.name}, Status: {s.status.name}")
                print(f"Total: {s.total_event_count}, Success: {s.successful_event_count}")
                for ds in s.daily_summaries:
                    # Mandate: total = success + failed + pending
                    total = ds.successful_count + ds.failed_count
                    print(f"  {ds.upload_date}: {ds.successful_count}/{total} successful")
    except GoogleAdsException as ex:
        print(f"Request ID {ex.request_id} failed: {ex.error.code().name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(client, args.customer_id)
