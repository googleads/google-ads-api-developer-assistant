# Copyright 2026 Google LLC
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

# Created by the Google Ads API Developer Assistant

"""Mandatory diagnostic collector for conversion troubleshooting."""

import argparse
from datetime import datetime, timedelta
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
    prev_files = sorted(glob.glob(os.path.join(output_dir, "conversion_troubleshooting_report_*.txt")), reverse=True)
    if prev_files:
        for pf in prev_files[:2]:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "1. Introductory Analysis" in content:
                        summary_part = content.split("2. Primary Errors & Critical Issues")[0]
                        findings.append(f"Historical Finding (from {os.path.basename(pf)}):\n{summary_part.strip()}")
            except Exception:
                pass
    return findings


def main(client: GoogleAdsClient, customer_id: str) -> None:
    epoch = int(time.time())
    output_dir = os.path.join(os.getcwd(), "saved", "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"conversion_troubleshooting_report_{epoch}.txt")

    summary = []
    errors = []
    details = [
        "\n[1] Customer Account Information",
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

    details.append("\n[2] Client Summary (Overall Health)")
    client_query = """
    SELECT
      offline_conversion_upload_client_summary.client,
      offline_conversion_upload_client_summary.status,
      offline_conversion_upload_client_summary.successful_event_count,
      offline_conversion_upload_client_summary.total_event_count,
      offline_conversion_upload_client_summary.daily_summaries,
      offline_conversion_upload_client_summary.alerts
    FROM offline_conversion_upload_client_summary
    """
    results = run_query(client, customer_id, client_query)
    print(f"\n=== Conversion Diagnostic Summary for Customer {customer_id} ===")
    print("1. Client Summary (Overall Health):")
    if not results:
        details.append("Reason: No standard offline imports detected in last 90 days")
        print("  No standard offline imports detected in last 90 days.")
        summary.append(f"For Customer ID: {customer_id}, no standard offline imports were detected in the last 90 days.")
    else:
        intro_lines = [f"For Customer ID: {customer_id}, the overall conversion upload health summary across clients:"]
        for row in results:
            csum = row.offline_conversion_upload_client_summary
            fail_rate = 0.0
            if csum.total_event_count > 0:
                fail_rate = (csum.total_event_count - csum.successful_event_count) / csum.total_event_count
            client_name = csum.client.name.split("/")[-1] if "/" in csum.client.name else csum.client.name
            intro_lines.append(f"  - {client_name}: {csum.status.name} ({csum.successful_event_count}/{csum.total_event_count} successful, {fail_rate:.2%} failure rate)")
            
            details.append(f"Client Status: {csum.status.name} (Total Success: {csum.successful_event_count}/{csum.total_event_count})")
            print(f"  Client: {csum.client.name}, Status: {csum.status.name}")
            print(f"  Total Events: {csum.total_event_count}, Successful: {csum.successful_event_count}")
            for ds in csum.daily_summaries:
                total = ds.successful_count + ds.failed_count + ds.pending_count
                details.append(f"  - {ds.upload_date}: Success={ds.successful_count}/{total}, Fail={ds.failed_count}, Pending={ds.pending_count}")
                print(f"    {ds.upload_date}: {ds.successful_count}/{total} successful")
            for alert in csum.alerts:
                try:
                    error_type = type(alert.error).pb(alert.error).WhichOneof("error_code")
                    error_val = getattr(alert.error, error_type)
                    error_name = error_val.name
                    details.append(f"  - Alert ({client_name}): {error_name} ({alert.error_percentage:.2%})")
                    errors.append(f"Client Alert ({client_name}): {error_name} ({alert.error_percentage:.2%})")
                    print(f"    Alert: {error_name} ({alert.error_percentage:.2%})")
                except Exception:
                    details.append(f"  - Alert ({client_name}): {alert.error} ({alert.error_percentage:.2%})")
                    print(f"    Alert: {alert.error} ({alert.error_percentage:.2%})")
        summary.append("\n".join(intro_lines))

    details.append("\n[3] Conversion Action Summaries (Last 7 Days)")
    summary_query = """
    SELECT
      offline_conversion_upload_conversion_action_summary.conversion_action_name,
      offline_conversion_upload_conversion_action_summary.successful_event_count,
      offline_conversion_upload_conversion_action_summary.total_event_count,
      offline_conversion_upload_conversion_action_summary.daily_summaries,
      offline_conversion_upload_conversion_action_summary.alerts
    FROM offline_conversion_upload_conversion_action_summary
    """
    results = run_query(client, customer_id, summary_query)
    print("\n2. Conversion Action Summaries:")
    if not results:
        details.append("Reason: No standard offline imports detected in last 90 days")
        print("  No standard offline imports detected in last 90 days.")
    else:
        for row in results:
            asum = row.offline_conversion_upload_conversion_action_summary
            details.append(f"Action: {asum.conversion_action_name} (Total Success: {asum.successful_event_count}/{asum.total_event_count})")
            print(f"  Action: {asum.conversion_action_name} (Success: {asum.successful_event_count}/{asum.total_event_count})")
            for ds in asum.daily_summaries:
                total = ds.successful_count + ds.failed_count + ds.pending_count
                details.append(f"  - {ds.upload_date}: Success={ds.successful_count}/{total}, Fail={ds.failed_count}, Pending={ds.pending_count}")
                print(f"    {ds.upload_date}: {ds.successful_count}/{total} successful")
            for alert in asum.alerts:
                try:
                    error_type = type(alert.error).pb(alert.error).WhichOneof("error_code")
                    error_val = getattr(alert.error, error_type)
                    error_name = error_val.name
                    details.append(f"  - Alert: {error_name} ({alert.error_percentage:.2%})")
                    errors.append(f"Action Alert ({asum.conversion_action_name}): {error_name} ({alert.error_percentage:.2%})")
                    print(f"    Alert: {error_name} ({alert.error_percentage:.2%})")
                except Exception:
                    details.append(f"  - Alert: {alert.error} ({alert.error_percentage:.2%})")
                    print(f"    Alert: {alert.error} ({alert.error_percentage:.2%})")
    details.append("\n[4] Recent GCLID Validation (Last 7 Days)")
    gclids_found = []
    for i in range(1, 8):
        query_date = (datetime.now() - timedelta(i)).strftime('%Y-%m-%d')
        gclid_query = f"""
        SELECT
          click_view.gclid,
          segments.date
        FROM click_view
        WHERE segments.date = '{query_date}'
        LIMIT 5
        """
        results = run_query(client, customer_id, gclid_query)
        if results:
            for row in results:
                gclids_found.append((row.click_view.gclid, query_date, i))
            if len(gclids_found) >= 10:
                break

    if not gclids_found:
        details.append("Reason: No recent GCLIDs found in click_view for the last 7 days")
    else:
        for gclid, date_str, age in gclids_found:
            details.append(f"  - GCLID: {gclid} | Date: {date_str} | Status: VALID ({age} day(s) old)")

    history = merge_previous_findings(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Created by the Google Ads API Developer Assistant\n\n")
        f.write("1. Introductory Analysis\n")
        f.write("\n".join(summary if summary else [f"Diagnostic Report for Customer ID: {customer_id}"]) + "\n\n")

        if history:
            f.write("=== HISTORICAL CONTEXT ===\n")
            f.write("\n".join(history) + "\n\n")

        f.write("2. Primary Errors & Critical Issues\n")
        f.write("\n".join(errors if errors else ["No blocking errors detected."]) + "\n\n")

        f.write("3. General Health & Technical Findings\n")
        f.write("\n".join(details) + "\n\n")

    print(f"Consolidated troubleshooting report: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--customer_id", required=True, help="The Google Ads customer ID.")
    parser.add_argument("-v", "--api_version", type=str, required=True, help="The Google Ads API version.")
    args = parser.parse_args()
    googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)
    main(googleads_client, args.customer_id)
