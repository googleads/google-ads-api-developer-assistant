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

"""Mandatory diagnostic collector for conversion troubleshooting."""

import argparse
import glob
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore
    GoogleAdsException = Exception  # type: ignore


def run_query(client: Any, customer_id: str, query: str) -> List[Any]:
    """Runs a GAQL query with standardized error logging."""
    ga_service = client.get_service("GoogleAdsService")
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        return [row for batch in response for row in batch.results]
    except GoogleAdsException as ex:
        print(f"ERROR: Query failed (Request ID: {getattr(ex, 'request_id', 'N/A')})", file=sys.stderr)
        if hasattr(ex, "failure") and hasattr(ex.failure, "errors"):
            for error in ex.failure.errors:
                print(f"\t- {error.message}", file=sys.stderr)
        return []


def merge_previous_findings(output_dir: str) -> List[str]:
    """Reads findings from existing support packages to maintain context."""
    findings = []
    prev_files = sorted(
        glob.glob(os.path.join(output_dir, "conversion_troubleshooting_report_*.txt")),
        reverse=True,
    )
    if prev_files:
        for pf in prev_files[:2]:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "1. Introductory Analysis" in content:
                        summary_part = content.split("2. Primary Errors & Critical Issues")[0]
                        findings.append(
                            f"Historical Finding (from {os.path.basename(pf)}):\n{summary_part.strip()}"
                        )
            except Exception:
                pass
    return findings


def troubleshoot_conversions(
    client: Any, customer_id: str, json_output: bool = False
) -> Dict[str, Any]:
    """Collects and reports conversion upload diagnostics."""
    epoch = int(time.time())
    output_dir = os.path.expanduser(os.path.join("~", "saved", "data"))
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"conversion_troubleshooting_report_{epoch}.txt")

    summary: List[str] = []
    errors: List[str] = []
    details: List[str] = [
        "\n[1] Customer Account Information",
        f"Diagnostic Report for Customer ID: {customer_id}",
        f"Timestamp: {time.ctime()} (Epoch: {epoch})",
        "-" * 40,
    ]

    structured_data: Dict[str, Any] = {
        "customer_id": customer_id,
        "timestamp": time.ctime(),
        "epoch": epoch,
        "customer_info": {},
        "client_summaries": [],
        "conversion_action_summaries": [],
        "recent_gclids": [],
        "primary_errors": [],
        "report_path": output_path,
    }

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
        cust_name = getattr(row.customer, "descriptive_name", "N/A")
        terms_accepted = bool(getattr(cts, "accepted_customer_data_terms", False))
        enhanced_leads = bool(getattr(cts, "enhanced_conversions_for_leads_enabled", False))

        details.append(f"Customer: {cust_name}")
        structured_data["customer_info"] = {
            "name": cust_name,
            "accepted_customer_data_terms": terms_accepted,
            "enhanced_conversions_for_leads_enabled": enhanced_leads,
        }
        if not terms_accepted:
            err_msg = "CRITICAL: Customer Data Terms NOT accepted."
            errors.append(err_msg)
            structured_data["primary_errors"].append(err_msg)

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
    if not json_output:
        print(f"\n=== Conversion Diagnostic Summary for Customer {customer_id} ===")
        print("1. Client Summary (Overall Health):")

    if not results:
        details.append("Reason: No standard offline imports detected in last 90 days")
        if not json_output:
            print("  No standard offline imports detected in last 90 days.")
        summary.append(
            f"For Customer ID: {customer_id}, no standard offline imports were detected in the last 90 days."
        )
    else:
        intro_lines = [
            f"For Customer ID: {customer_id}, the overall conversion upload health summary across clients:"
        ]
        for row in results:
            csum = row.offline_conversion_upload_client_summary
            total_count = int(getattr(csum, "total_event_count", 0))
            success_count = int(getattr(csum, "successful_event_count", 0))
            fail_rate = 0.0
            if total_count > 0:
                fail_rate = (total_count - success_count) / total_count

            client_raw = getattr(csum, "client", "UNKNOWN")
            client_name = getattr(client_raw, "name", str(client_raw))
            if "/" in client_name:
                client_name = client_name.split("/")[-1]

            status_raw = getattr(csum, "status", "UNKNOWN")
            status_name = getattr(status_raw, "name", str(status_raw))

            intro_lines.append(
                f"  - {client_name}: {status_name} ({success_count}/{total_count} successful, {fail_rate:.2%} failure rate)"
            )
            details.append(
                f"Client Status: {status_name} (Total Success: {success_count}/{total_count})"
            )

            client_dict: Dict[str, Any] = {
                "client": client_name,
                "status": status_name,
                "total_event_count": total_count,
                "successful_event_count": success_count,
                "failure_rate": fail_rate,
                "daily_summaries": [],
                "alerts": [],
            }

            if not json_output:
                print(f"  Client: {client_name}, Status: {status_name}")
                print(f"  Total Events: {total_count}, Successful: {success_count}")

            for ds in getattr(csum, "daily_summaries", []):
                s_cnt = int(getattr(ds, "successful_count", 0))
                f_cnt = int(getattr(ds, "failed_count", 0))
                p_cnt = int(getattr(ds, "pending_count", 0))
                total = s_cnt + f_cnt + p_cnt
                u_date = str(getattr(ds, "upload_date", ""))
                details.append(f"  - {u_date}: Success={s_cnt}/{total}, Fail={f_cnt}, Pending={p_cnt}")
                if not json_output:
                    print(f"    {u_date}: {s_cnt}/{total} successful")
                client_dict["daily_summaries"].append({
                    "upload_date": u_date,
                    "successful_count": s_cnt,
                    "failed_count": f_cnt,
                    "pending_count": p_cnt,
                    "total": total,
                })

            for alert in getattr(csum, "alerts", []):
                alert_error = "UNKNOWN"
                try:
                    error_type = type(alert.error).pb(alert.error).WhichOneof("error_code")
                    error_val = getattr(alert.error, error_type)
                    alert_error = getattr(error_val, "name", str(error_val))
                except Exception:
                    alert_error = str(getattr(alert, "error", "UNKNOWN"))

                err_pct = float(getattr(alert, "error_percentage", 0.0))
                details.append(f"  - Alert ({client_name}): {alert_error} ({err_pct:.2%})")
                errors.append(f"Client Alert ({client_name}): {alert_error} ({err_pct:.2%})")
                if not json_output:
                    print(f"    Alert: {alert_error} ({err_pct:.2%})")
                client_dict["alerts"].append({
                    "error": alert_error,
                    "error_percentage": err_pct,
                })

            structured_data["client_summaries"].append(client_dict)

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
    if not json_output:
        print("\n2. Conversion Action Summaries:")

    if not results:
        details.append("Reason: No standard offline imports detected in last 90 days")
        if not json_output:
            print("  No standard offline imports detected in last 90 days.")
    else:
        for row in results:
            asum = row.offline_conversion_upload_conversion_action_summary
            act_name = str(getattr(asum, "conversion_action_name", "UNKNOWN"))
            act_total = int(getattr(asum, "total_event_count", 0))
            act_success = int(getattr(asum, "successful_event_count", 0))

            details.append(f"Action: {act_name} (Total Success: {act_success}/{act_total})")
            if not json_output:
                print(f"  Action: {act_name} (Success: {act_success}/{act_total})")

            action_dict: Dict[str, Any] = {
                "conversion_action_name": act_name,
                "total_event_count": act_total,
                "successful_event_count": act_success,
                "daily_summaries": [],
                "alerts": [],
            }

            for ds in getattr(asum, "daily_summaries", []):
                s_cnt = int(getattr(ds, "successful_count", 0))
                f_cnt = int(getattr(ds, "failed_count", 0))
                p_cnt = int(getattr(ds, "pending_count", 0))
                total = s_cnt + f_cnt + p_cnt
                u_date = str(getattr(ds, "upload_date", ""))
                details.append(f"  - {u_date}: Success={s_cnt}/{total}, Fail={f_cnt}, Pending={p_cnt}")
                if not json_output:
                    print(f"    {u_date}: {s_cnt}/{total} successful")
                action_dict["daily_summaries"].append({
                    "upload_date": u_date,
                    "successful_count": s_cnt,
                    "failed_count": f_cnt,
                    "pending_count": p_cnt,
                    "total": total,
                })

            for alert in getattr(asum, "alerts", []):
                alert_error = "UNKNOWN"
                try:
                    error_type = type(alert.error).pb(alert.error).WhichOneof("error_code")
                    error_val = getattr(alert.error, error_type)
                    alert_error = getattr(error_val, "name", str(error_val))
                except Exception:
                    alert_error = str(getattr(alert, "error", "UNKNOWN"))

                err_pct = float(getattr(alert, "error_percentage", 0.0))
                details.append(f"  - Alert: {alert_error} ({err_pct:.2%})")
                errors.append(f"Action Alert ({act_name}): {alert_error} ({err_pct:.2%})")
                if not json_output:
                    print(f"    Alert: {alert_error} ({err_pct:.2%})")
                action_dict["alerts"].append({
                    "error": alert_error,
                    "error_percentage": err_pct,
                })

            structured_data["conversion_action_summaries"].append(action_dict)

    details.append("\n[4] Recent GCLID Validation (Last 7 Days)")
    gclids_found: List[Dict[str, Any]] = []
    for i in range(1, 8):
        query_date = (datetime.now() - timedelta(i)).strftime("%Y-%m-%d")
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
                g_val = str(getattr(row.click_view, "gclid", ""))
                gclids_found.append({"gclid": g_val, "date": query_date, "age_days": i})
            if len(gclids_found) >= 10:
                break

    structured_data["recent_gclids"] = gclids_found

    if not gclids_found:
        details.append("Reason: No recent GCLIDs found in click_view for the last 7 days")
    else:
        for g_entry in gclids_found:
            details.append(
                f"  - GCLID: {g_entry['gclid']} | Date: {g_entry['date']} | Status: VALID ({g_entry['age_days']} day(s) old)"
            )

    history = merge_previous_findings(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Created by the Google Ads API Developer Assistant\n\n")
        f.write("1. Introductory Analysis\n")
        f.write(
            "\n".join(summary if summary else [f"Diagnostic Report for Customer ID: {customer_id}"])
            + "\n\n"
        )

        if history:
            f.write("=== HISTORICAL CONTEXT ===\n")
            f.write("\n".join(history) + "\n\n")

        f.write("2. Primary Errors & Critical Issues\n")
        f.write(
            "\n".join(errors if errors else ["No blocking errors detected."]) + "\n\n"
        )

        f.write("3. General Health & Technical Findings\n")
        f.write("\n".join(details) + "\n\n")

    if json_output:
        print(json.dumps(structured_data, indent=2, default=str))
    else:
        print(f"\nConsolidated troubleshooting report: {output_path}")

    return structured_data


def main() -> None:
    """Parses command line arguments and runs conversion troubleshooting."""
    parser = argparse.ArgumentParser(description="Conversion troubleshooting diagnostic collector.")
    parser.add_argument("-c", "--customer_id", required=True, help="The Google Ads customer ID.")
    parser.add_argument("-v", "--api_version", type=str, required=True, help="The Google Ads API version.")
    parser.add_argument("--json", action="store_true", default=False, help="If set, outputs structured diagnostic JSON to stdout.")
    args = parser.parse_args()

    if GoogleAdsClient is None:
        print("CRITICAL ERROR: google-ads package is not installed.", file=sys.stderr)
        sys.exit(1)

    try:
        googleads_client = GoogleAdsClient.load_from_storage(version=args.api_version)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}", file=sys.stderr)
        sys.exit(1)

    troubleshoot_conversions(googleads_client, args.customer_id, json_output=args.json)


if __name__ == "__main__":
    main()
