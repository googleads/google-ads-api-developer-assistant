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
import re
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore

    class GoogleAdsException(Exception):  # type: ignore[no-redef]
        pass


_ACTIVE_QUERY_ERRORS: Optional[List[str]] = None


def _normalize_api_version(api_version: str) -> str:
    clean = str(api_version or "").strip().lower()
    if clean and not clean.startswith("v") and clean.isdigit():
        clean = f"v{clean}"
    return clean


def _get_config_path() -> str:
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path:
        expanded_env = os.path.abspath(os.path.expanduser(config_path))
        raw_home_yaml = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
        if expanded_env != raw_home_yaml and os.path.isfile(expanded_env):
            return config_path if os.path.isfile(config_path) else expanded_env

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    candidates = [
        os.path.abspath("config/google-ads.yaml"),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath(os.path.join(script_dir, "../../../../config/google-ads.yaml")),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        if plugin_root not in sys.path and os.path.isdir(plugin_root):
            sys.path.insert(0, plugin_root)
        from config.config_init import sync_and_set_config_kv

        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


def _record_query_error(msg: str, errors_out: Optional[List[str]] = None) -> None:
    if errors_out is not None and msg not in errors_out:
        errors_out.append(msg)
    if _ACTIVE_QUERY_ERRORS is not None and msg not in _ACTIVE_QUERY_ERRORS:
        _ACTIVE_QUERY_ERRORS.append(msg)


def run_query(
    client: Any,
    customer_id: str,
    query: str,
    errors_out: Optional[List[str]] = None,
) -> List[Any]:
    """Runs a GAQL query with standardized error logging."""
    clean_cid = re.sub(r"\D", "", str(customer_id or "")) or str(customer_id)
    ga_service = client.get_service("GoogleAdsService")
    try:
        response = ga_service.search_stream(customer_id=clean_cid, query=query)
        return [row for batch in response for row in batch.results]
    except GoogleAdsException as ex:
        req_id = getattr(ex, "request_id", None) or "N/A"
        print(f"ERROR: Query failed (Request ID: {req_id})", file=sys.stderr)
        err_messages: List[str] = []
        failure = getattr(ex, "failure", None)
        if failure is not None and hasattr(failure, "errors"):
            for error in failure.errors:
                emsg = str(getattr(error, "message", error))
                print(f"\t- {emsg}", file=sys.stderr)
                err_messages.append(emsg)
        detail = "; ".join(err_messages) if err_messages else str(ex)
        _record_query_error(
            f"API Query Error (Request ID: {req_id}): {detail}", errors_out
        )
        return []
    except Exception as ex:
        print(f"ERROR: Query execution failed: {ex}", file=sys.stderr)
        _record_query_error(f"API Query Error: {ex}", errors_out)
        return []


def merge_previous_findings(
    output_dir: str,
    customer_id: Optional[str] = None,
    exclude_path: Optional[str] = None,
) -> List[str]:
    """Reads findings from existing support packages for the same customer to maintain context."""
    findings: List[str] = []
    clean_target_cid = (
        re.sub(r"\D", "", str(customer_id)) if customer_id is not None else None
    )
    abs_exclude = os.path.abspath(exclude_path) if exclude_path else None

    prev_files = sorted(
        glob.glob(os.path.join(output_dir, "conversion_troubleshooting_report_*.txt")),
        reverse=True,
    )
    for pf in prev_files:
        if len(findings) >= 2:
            break
        if abs_exclude and os.path.abspath(pf) == abs_exclude:
            continue
        try:
            # Cap file read at 64KB to avoid unbounded memory allocation
            with open(pf, "r", encoding="utf-8") as f:
                content = f.read(65536)
            if clean_target_cid:
                m_cid = re.search(r"Customer ID:\s*([0-9-]+)", content)
                if m_cid and re.sub(r"\D", "", m_cid.group(1)) != clean_target_cid:
                    continue
            if "1. Introductory Analysis" in content:
                summary_part = content.split("2. Primary Errors & Critical Issues")[0]
                # Strip nested historical context to prevent exponential growth across runs
                if "=== HISTORICAL CONTEXT ===" in summary_part:
                    summary_part = summary_part.split("=== HISTORICAL CONTEXT ===")[0]
                findings.append(
                    f"Historical Finding (from {os.path.basename(pf)}):\n{summary_part.strip()}"
                )
        except Exception:
            pass
    return findings


def _extract_enum_label(parent_obj: Any, field_name: str, default: str = "UNKNOWN") -> str:
    """Safely extracts enum name across proto-plus, raw protobuf (use_proto_plus=False), and mocks."""
    raw_val = getattr(parent_obj, field_name, default)
    name_attr = getattr(raw_val, "name", None)
    if isinstance(name_attr, str) and name_attr:
        return name_attr
    if isinstance(raw_val, int) and not isinstance(raw_val, bool):
        desc = getattr(parent_obj, "DESCRIPTOR", None)
        fields_by_name = getattr(desc, "fields_by_name", None) if desc else None
        if fields_by_name and field_name in fields_by_name:
            enum_desc = getattr(fields_by_name[field_name], "enum_type", None)
            values_by_num = getattr(enum_desc, "values_by_number", None)
            if values_by_num and raw_val in values_by_num:
                return str(values_by_num[raw_val].name)
    return str(raw_val)


def _extract_alert_error_name(alert: Any) -> str:
    """Extracts error code name from OfflineConversionAlert across proto-plus, raw protobuf, and mocks."""
    err = getattr(alert, "error", None)
    if err is None:
        return "UNKNOWN"
    if isinstance(err, str):
        return err

    # 1. Try proto-plus .pb(...) wrapper
    pb_fn = getattr(type(err), "pb", None)
    if callable(pb_fn):
        try:
            pb_msg = pb_fn(err)
            oneof_field = pb_msg.WhichOneof("error_code")
            if oneof_field:
                error_val = getattr(err, oneof_field)
                val_name = getattr(error_val, "name", None)
                if isinstance(val_name, str) and val_name:
                    return val_name
                return str(error_val)
        except Exception:
            pass

    # 2. Try raw protobuf WhichOneof("error_code") (use_proto_plus=False)
    which_fn = getattr(err, "WhichOneof", None)
    if callable(which_fn):
        try:
            oneof_field = which_fn("error_code")
            if isinstance(oneof_field, str) and oneof_field:
                return _extract_enum_label(err, oneof_field, default="UNKNOWN")
        except Exception:
            pass

    name_attr = getattr(err, "name", None)
    if isinstance(name_attr, str) and name_attr:
        return name_attr
    return str(err)


def _safe_nonneg_int(val: Any) -> int:
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return max(0, int(val))
    return 0


def _append_error(
    msg: str, errors: List[str], structured_data: Dict[str, Any]
) -> None:
    if msg not in errors:
        errors.append(msg)
    if msg not in structured_data["primary_errors"]:
        structured_data["primary_errors"].append(msg)


def troubleshoot_conversions(
    client: Any,
    customer_id: str,
    json_output: bool = False,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Collects and reports conversion upload diagnostics."""
    global _ACTIVE_QUERY_ERRORS
    clean_cid = re.sub(r"\D", "", str(customer_id or ""))
    if not clean_cid:
        print(f"ERROR: Invalid customer ID '{customer_id}'.", file=sys.stderr)
        sys.exit(1)

    epoch = int(time.time())
    if not output_dir:
        output_dir = os.environ.get(
            "CONVERSION_OUTPUT_DIR", os.path.abspath(os.path.join("saved", "data"))
        )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir, f"conversion_troubleshooting_report_{epoch}.txt"
    )

    summary: List[str] = []
    errors: List[str] = []
    details: List[str] = [
        "\n[1] Customer Account Information",
        f"Diagnostic Report for Customer ID: {clean_cid}",
        f"Timestamp: {time.ctime()} (Epoch: {epoch})",
        "-" * 40,
    ]

    structured_data: Dict[str, Any] = {
        "customer_id": clean_cid,
        "timestamp": time.ctime(),
        "epoch": epoch,
        "customer_info": {},
        "client_summaries": [],
        "conversion_action_summaries": [],
        "recent_gclids": [],
        "primary_errors": [],
        "report_path": output_path,
    }

    query_errors: List[str] = []
    prev_active_errors = _ACTIVE_QUERY_ERRORS
    _ACTIVE_QUERY_ERRORS = query_errors
    try:
        customer_query = """
        SELECT
          customer.descriptive_name,
          customer.conversion_tracking_setting.accepted_customer_data_terms,
          customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled
        FROM customer
        """
        results = run_query(client, clean_cid, customer_query)
        for row in results:
            cts = row.customer.conversion_tracking_setting
            cust_name = getattr(row.customer, "descriptive_name", "N/A")
            terms_accepted = bool(getattr(cts, "accepted_customer_data_terms", False))
            enhanced_leads = bool(
                getattr(cts, "enhanced_conversions_for_leads_enabled", False)
            )

            details.append(f"Customer: {cust_name}")
            details.append(f"Accepted Customer Data Terms: {terms_accepted}")
            details.append(
                f"Enhanced Conversions for Leads Enabled: {enhanced_leads}"
            )
            structured_data["customer_info"] = {
                "name": cust_name,
                "accepted_customer_data_terms": terms_accepted,
                "enhanced_conversions_for_leads_enabled": enhanced_leads,
            }
            if not terms_accepted:
                _append_error(
                    "CRITICAL: Customer Data Terms NOT accepted.",
                    errors,
                    structured_data,
                )

        details.append("\n[2] Client Summary (Overall Health)")
        client_query = """
        SELECT
          offline_conversion_upload_client_summary.client,
          offline_conversion_upload_client_summary.status,
          offline_conversion_upload_client_summary.successful_event_count,
          offline_conversion_upload_client_summary.pending_event_count,
          offline_conversion_upload_client_summary.total_event_count,
          offline_conversion_upload_client_summary.daily_summaries,
          offline_conversion_upload_client_summary.alerts
        FROM offline_conversion_upload_client_summary
        """
        results = run_query(client, clean_cid, client_query)
        if not json_output:
            print("Created by the Google Ads API Developer Assistant")
            print(f"\n=== Conversion Diagnostic Summary for Customer {clean_cid} ===")
            print("1. Client Summary (Overall Health):")

        if not results:
            details.append("Reason: No standard offline imports detected in last 90 days")
            if not json_output:
                print("  No standard offline imports detected in last 90 days.")
            summary.append(
                f"For Customer ID: {clean_cid}, no standard offline imports were detected in the last 90 days."
            )
        else:
            intro_lines = [
                f"For Customer ID: {clean_cid}, the overall conversion upload health summary across clients:"
            ]
            for row in results:
                csum = row.offline_conversion_upload_client_summary
                total_count = int(getattr(csum, "total_event_count", 0) or 0)
                success_count = int(getattr(csum, "successful_event_count", 0) or 0)
                pending_count = _safe_nonneg_int(
                    getattr(csum, "pending_event_count", 0)
                )
                failed_count = max(0, total_count - success_count - pending_count)
                fail_rate = (failed_count / total_count) if total_count > 0 else 0.0

                client_name = _extract_enum_label(csum, "client", default="UNKNOWN")
                if "/" in client_name:
                    client_name = client_name.split("/")[-1]

                status_name = _extract_enum_label(csum, "status", default="UNKNOWN")

                intro_lines.append(
                    f"  - {client_name}: {status_name} ({success_count}/{total_count} successful, {fail_rate:.2%} failure rate)"
                )
                details.append(
                    f"Client Status: {status_name} (Total Success: {success_count}/{total_count}, Pending: {pending_count})"
                )

                if fail_rate > 0.10:
                    _append_error(
                        f"WARNING: High failure rate for client {client_name}: {fail_rate:.2%} ({failed_count}/{total_count} failed).",
                        errors,
                        structured_data,
                    )

                client_dict: Dict[str, Any] = {
                    "client": client_name,
                    "status": status_name,
                    "total_event_count": total_count,
                    "successful_event_count": success_count,
                    "pending_event_count": pending_count,
                    "failure_rate": fail_rate,
                    "daily_summaries": [],
                    "alerts": [],
                }

                if not json_output:
                    print(f"  Client: {client_name}, Status: {status_name}")
                    print(f"  Total Events: {total_count}, Successful: {success_count}")

                for ds in getattr(csum, "daily_summaries", []):
                    s_cnt = int(getattr(ds, "successful_count", 0) or 0)
                    f_cnt = int(getattr(ds, "failed_count", 0) or 0)
                    p_cnt = int(getattr(ds, "pending_count", 0) or 0)
                    total = s_cnt + f_cnt + p_cnt
                    u_date = str(getattr(ds, "upload_date", ""))
                    details.append(
                        f"  - {u_date}: Success={s_cnt}/{total}, Fail={f_cnt}, Pending={p_cnt}"
                    )
                    if not json_output:
                        print(f"    {u_date}: {s_cnt}/{total} successful")
                    client_dict["daily_summaries"].append(
                        {
                            "upload_date": u_date,
                            "successful_count": s_cnt,
                            "failed_count": f_cnt,
                            "pending_count": p_cnt,
                            "total": total,
                        }
                    )

                for alert in getattr(csum, "alerts", []):
                    alert_error = _extract_alert_error_name(alert)
                    err_pct = float(getattr(alert, "error_percentage", 0.0) or 0.0)
                    details.append(
                        f"  - Alert ({client_name}): {alert_error} ({err_pct:.2%})"
                    )
                    _append_error(
                        f"Client Alert ({client_name}): {alert_error} ({err_pct:.2%})",
                        errors,
                        structured_data,
                    )
                    if not json_output:
                        print(f"    Alert: {alert_error} ({err_pct:.2%})")
                    client_dict["alerts"].append(
                        {
                            "error": alert_error,
                            "error_percentage": err_pct,
                        }
                    )

                structured_data["client_summaries"].append(client_dict)

            summary.append("\n".join(intro_lines))

        details.append("\n[3] Conversion Action Summaries (Last 90 Days)")
        summary_query = """
        SELECT
          offline_conversion_upload_conversion_action_summary.conversion_action_name,
          offline_conversion_upload_conversion_action_summary.successful_event_count,
          offline_conversion_upload_conversion_action_summary.pending_event_count,
          offline_conversion_upload_conversion_action_summary.total_event_count,
          offline_conversion_upload_conversion_action_summary.daily_summaries,
          offline_conversion_upload_conversion_action_summary.alerts
        FROM offline_conversion_upload_conversion_action_summary
        """
        results = run_query(client, clean_cid, summary_query)
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
                act_total = int(getattr(asum, "total_event_count", 0) or 0)
                act_success = int(getattr(asum, "successful_event_count", 0) or 0)
                act_pending = _safe_nonneg_int(
                    getattr(asum, "pending_event_count", 0)
                )
                act_failed = max(0, act_total - act_success - act_pending)
                act_fail_rate = (act_failed / act_total) if act_total > 0 else 0.0

                details.append(
                    f"Action: {act_name} (Total Success: {act_success}/{act_total})"
                )
                if not json_output:
                    print(f"  Action: {act_name} (Success: {act_success}/{act_total})")

                if act_fail_rate > 0.10:
                    _append_error(
                        f"WARNING: High failure rate for conversion action '{act_name}': {act_fail_rate:.2%} ({act_failed}/{act_total} failed).",
                        errors,
                        structured_data,
                    )

                action_dict: Dict[str, Any] = {
                    "conversion_action_name": act_name,
                    "total_event_count": act_total,
                    "successful_event_count": act_success,
                    "pending_event_count": act_pending,
                    "failure_rate": act_fail_rate,
                    "daily_summaries": [],
                    "alerts": [],
                }

                for ds in getattr(asum, "daily_summaries", []):
                    s_cnt = int(getattr(ds, "successful_count", 0) or 0)
                    f_cnt = int(getattr(ds, "failed_count", 0) or 0)
                    p_cnt = int(getattr(ds, "pending_count", 0) or 0)
                    total = s_cnt + f_cnt + p_cnt
                    u_date = str(getattr(ds, "upload_date", ""))
                    details.append(
                        f"  - {u_date}: Success={s_cnt}/{total}, Fail={f_cnt}, Pending={p_cnt}"
                    )
                    if not json_output:
                        print(f"    {u_date}: {s_cnt}/{total} successful")
                    action_dict["daily_summaries"].append(
                        {
                            "upload_date": u_date,
                            "successful_count": s_cnt,
                            "failed_count": f_cnt,
                            "pending_count": p_cnt,
                            "total": total,
                        }
                    )

                for alert in getattr(asum, "alerts", []):
                    alert_error = _extract_alert_error_name(alert)
                    err_pct = float(getattr(alert, "error_percentage", 0.0) or 0.0)
                    details.append(f"  - Alert: {alert_error} ({err_pct:.2%})")
                    _append_error(
                        f"Action Alert ({act_name}): {alert_error} ({err_pct:.2%})",
                        errors,
                        structured_data,
                    )
                    if not json_output:
                        print(f"    Alert: {alert_error} ({err_pct:.2%})")
                    action_dict["alerts"].append(
                        {
                            "error": alert_error,
                            "error_percentage": err_pct,
                        }
                    )

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
            results = run_query(client, clean_cid, gclid_query)
            if results:
                for row in results:
                    g_val = str(getattr(row.click_view, "gclid", ""))
                    gclids_found.append(
                        {"gclid": g_val, "date": query_date, "age_days": i}
                    )
                if len(gclids_found) >= 10:
                    break
    finally:
        _ACTIVE_QUERY_ERRORS = prev_active_errors

    for q_err in query_errors:
        _append_error(q_err, errors, structured_data)

    structured_data["recent_gclids"] = gclids_found

    if not gclids_found:
        details.append("Reason: No recent GCLIDs found in click_view for the last 7 days")
    else:
        for g_entry in gclids_found:
            details.append(
                f"  - GCLID: {g_entry['gclid']} | Date: {g_entry['date']} | Status: VALID ({g_entry['age_days']} day(s) old)"
            )

    history = merge_previous_findings(
        output_dir, customer_id=clean_cid, exclude_path=output_path
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("Created by the Google Ads API Developer Assistant\n\n")
        f.write("1. Introductory Analysis\n")
        f.write(
            "\n".join(
                summary
                if summary
                else [f"Diagnostic Report for Customer ID: {clean_cid}"]
            )
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
    parser = argparse.ArgumentParser(
        description="Conversion troubleshooting diagnostic collector."
    )
    parser.add_argument(
        "-c", "--customer_id", required=True, help="The Google Ads customer ID."
    )
    parser.add_argument(
        "-v", "--api_version", type=str, required=True, help="The Google Ads API version."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="If set, outputs structured diagnostic JSON to stdout.",
    )
    args = parser.parse_args()

    if GoogleAdsClient is None:
        print("CRITICAL ERROR: google-ads package is not installed.", file=sys.stderr)
        sys.exit(1)

    try:
        cfg_path = _get_config_path()
        norm_ver = _normalize_api_version(args.api_version)
        googleads_client = GoogleAdsClient.load_from_storage(
            path=cfg_path, version=norm_ver
        )
    except Exception as e:
        print(
            f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    troubleshoot_conversions(
        googleads_client, args.customer_id, json_output=args.json
    )


if __name__ == "__main__":
    main()
