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

"""Collects diagnostic data for conversion troubleshooting in a structured format."""

import argparse
import os
import sys
import time
from typing import Any, List

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def run_query(client: GoogleAdsClient, customer_id: str, query: str) -> List[Any]:
    """Runs a GAQL query and returns the results."""
    ga_service = client.get_service("GoogleAdsService")
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        results = []
        for batch in response:
            for row in batch.results:
                results.append(row)
        return results
    except GoogleAdsException as ex:
        print(
            f"Request with ID '{ex.request_id}' failed with status "
            f"'{ex.error.code().name}' and includes the following errors:"
        )
        for error in ex.failure.errors:
            print(f"\tError with message '{error.message}'.")
        sys.exit(1)


def main(client: GoogleAdsClient, customer_id: str):
    epoch = int(time.time())
    output_dir = "saved/data"
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"conversions_support_data_{epoch}.txt"
    output_path = os.path.join(output_dir, output_filename)

    summary = []
    errors = []
    details = []

    details.append(f"Diagnostic Report for Customer ID: {customer_id}")
    details.append(f"Timestamp: {time.ctime()} (Epoch: {epoch})")
    details.append("-" * 40)

    # 1. Customer Settings
    details.append("\n[1] Customer Settings")
    customer_query = """
    SELECT
      customer.id,
      customer.descriptive_name,
      customer.conversion_tracking_setting.accepted_customer_data_terms,
      customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled
    FROM customer
    """
    customer_results = run_query(client, customer_id, customer_query)
    for row in customer_results:
        settings = row.customer.conversion_tracking_setting
        details.append(f"Customer Name: {row.customer.descriptive_name}")
        details.append(f"EC for Leads Enabled: {settings.enhanced_conversions_for_leads_enabled}")
        details.append(f"Customer Data Terms Accepted: {settings.accepted_customer_data_terms}")

        if not settings.accepted_customer_data_terms:
            errors.append("CRITICAL: Customer Data Terms NOT accepted.")
        if not settings.enhanced_conversions_for_leads_enabled:
            summary.append("Note: Enhanced Conversions for Leads represents a potential growth area (currently disabled).")

    # 2. Conversion Actions
    details.append("\n[2] Conversion Actions")
    ca_query = """
    SELECT
      conversion_action.id,
      conversion_action.name,
      conversion_action.type,
      conversion_action.status,
      conversion_action.owner_customer
    FROM conversion_action
    WHERE conversion_action.status != 'REMOVED'
    """
    ca_results = run_query(client, customer_id, ca_query)
    upload_clks_found = False
    for row in ca_results:
        ca = row.conversion_action
        details.append(f"- {ca.name} (ID: {ca.id}): Type={ca.type.name}, Status={ca.status.name}")
        if ca.type.name == "UPLOAD_CLICKS":
            upload_clks_found = True

    if not upload_clks_found:
        errors.append("WARNING: No UPLOAD_CLICKS conversion actions found. Mandatory for offline imports.")

    # 3. Offline Conversion Upload Summaries
    details.append("\n[3] Offline Conversion Upload Summaries")

    # Client Summary
    client_summary_query = """
    SELECT
      offline_conversion_upload_client_summary.status,
      offline_conversion_upload_client_summary.successful_event_count,
      offline_conversion_upload_client_summary.total_event_count,
      offline_conversion_upload_client_summary.last_upload_date_time,
      offline_conversion_upload_client_summary.client
    FROM offline_conversion_upload_client_summary
    """
    client_summary_results = run_query(client, customer_id, client_summary_query)
    for row in client_summary_results:
        cs = row.offline_conversion_upload_client_summary
        details.append(
            f"Client: {cs.client.name}, Status={cs.status.name}, Last Upload={cs.last_upload_date_time}, "
            f"Success={cs.successful_event_count}/{cs.total_event_count}"
        )
        if cs.status.name == "NEEDS_ATTENTION":
            errors.append(f"ISSUE: Client '{cs.client.name}' NEEDS_ATTENTION. Check upload logs.")

    # Action Summary
    action_summary_query = """
    SELECT
      offline_conversion_upload_conversion_action_summary.status,
      offline_conversion_upload_conversion_action_summary.successful_event_count,
      offline_conversion_upload_conversion_action_summary.total_event_count,
      offline_conversion_upload_conversion_action_summary.last_upload_date_time,
      offline_conversion_upload_conversion_action_summary.conversion_action_name
    FROM offline_conversion_upload_conversion_action_summary
    """
    action_summary_results = run_query(client, customer_id, action_summary_query)
    for row in action_summary_results:
        asum = row.offline_conversion_upload_conversion_action_summary
        details.append(
            f"Action: {asum.conversion_action_name}, Status={asum.status.name}, Last Upload={asum.last_upload_date_time}, "
            f"Success={asum.successful_event_count}/{asum.total_event_count}"
        )
        if asum.status.name == "NEEDS_ATTENTION":
            errors.append(f"ISSUE: Action '{asum.conversion_action_name}' NEEDS_ATTENTION. High failure rate detected.")

    # Final Summary Construction
    if not errors:
        summary.insert(0, "Overall Status: HEALTHY. No major conversion configuration issues detected.")
    else:
        summary.insert(0, f"Overall Status: UNHEALTHY. {len(errors)} potential issues identified.")

    # Write the file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=== SUMMARY OF FINDINGS ===\n")
        f.write("\n".join(summary) + "\n\n")

        f.write("=== ERRORS FOUND ===\n")
        if not errors:
            f.write("No errors detected.\n")
        else:
            f.write("\n".join(errors) + "\n")
        f.write("\n")

        f.write("=== DETAILS ===\n")
        f.write("\n".join(details) + "\n")

    print(f"Troubleshooting report generated: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collects troubleshooting data for conversions.")
    parser.add_argument("-c", "--customer_id", dest="customer_id", required=True, help="The Google Ads customer ID.")
    args = parser.parse_args()

    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    main(googleads_client, args.customer_id)
