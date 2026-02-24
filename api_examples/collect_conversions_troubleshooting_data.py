# Created by the Google Ads API Developer Assistant
# Copyright 2026 Google LLC

"""Mandatory diagnostic collector for conversion troubleshooting."""

import argparse
import glob
import os
import time
from typing import Any, List

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def run_query(client: GoogleAdsClient, customer_id: str, query: str) -> List[Any]:
    """Runs a GAQL query with standardized error logging."""
    ga_service = client.get_service("GoogleAdsService")
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        return [row for batch in response for row in batch.results]
    except GoogleAdsException as ex:
        print(f"ERROR: Query failed (Request ID: {ex.request_id})")
        for error in ex.failure.errors:
            print(f"\t- {error.message}")
        return []


def merge_previous_findings(output_dir: str) -> List[str]:
    """Reads findings from existing support packages to maintain context."""
    findings = []
    prev_files = sorted(glob.glob(os.path.join(output_dir, "conversions_support_data_*.txt")), reverse=True)
    if prev_files:
        for pf in prev_files[:2]:
            try:
                with open(pf, "r") as f:
                    content = f.read()
                    if "=== SUMMARY OF FINDINGS ===" in content:
                        summary_part = content.split("=== ERRORS FOUND ===")[0]
                        findings.append(f"Historical Finding (from {os.path.basename(pf)}):\n{summary_part.strip()}")
            except Exception:
                pass
    return findings


def main(client: GoogleAdsClient, customer_id: str):
    epoch = int(time.time())
    output_dir = "saved/data"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"conversions_support_data_{epoch}.txt")

    summary = []
    errors = []
    details = [
        f"Diagnostic Report for Customer ID: {customer_id}",
        f"Timestamp: {time.ctime()} (Epoch: {epoch})",
        "-" * 40
    ]

    customer_query = """
    SELECT
      customer.descriptive_name,
      customer.conversion_tracking_setting.accepted_customer_data_terms,
      customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled
    FROM customer
    """
    results = run_query(client, customer_id, customer_query)
    for row in results:
        cts = row.customer.conversion_tracking_setting
        details.append(f"Customer: {row.customer.descriptive_name}")
        if not cts.accepted_customer_data_terms:
            errors.append("CRITICAL: Customer Data Terms NOT accepted.")

    details.append("\n[2] Conversion Health (Last 7 Days)")
    summary_query = """
    SELECT
      offline_conversion_upload_conversion_action_summary.conversion_action_name,
      offline_conversion_upload_conversion_action_summary.successful_event_count,
      offline_conversion_upload_conversion_action_summary.total_event_count,
      offline_conversion_upload_conversion_action_summary.daily_summaries
    FROM offline_conversion_upload_conversion_action_summary
    """
    results = run_query(client, customer_id, summary_query)
    if not results:
        details.append("No offline conversion summaries detected in last 90 days.")
    else:
        for row in results:
            asum = row.offline_conversion_upload_conversion_action_summary
            details.append(f"Action: {asum.conversion_action_name} (Total Success: {asum.successful_event_count}/{asum.total_event_count})")
            for ds in asum.daily_summaries:
                details.append(f"  - {ds.upload_date}: Success={ds.successful_count}, Fail={ds.failed_count}")

    history = merge_previous_findings(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Created by the Google Ads API Developer Assistant\n")
        f.write("=== SUMMARY OF FINDINGS ===\n")
        f.write("\n".join(summary if summary else ["Status: Diagnostics completed."]) + "\n\n")

        if history:
            f.write("=== HISTORICAL CONTEXT ===\n")
            f.write("\n".join(history) + "\n\n")

        f.write("=== ERRORS FOUND ===\n")
        f.write("\n".join(errors if errors else ["No blocking errors detected."]) + "\n\n")

        f.write("=== DETAILS ===\n")
        f.write("\n".join(details) + "\n")

    print(f"Consolidated troubleshooting report: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--api_version", type=str, default="v23", help="The Google Ads API version.")
    args = parser.parse_args()
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(googleads_client, args.customer_id)
