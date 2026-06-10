---
name: troubleshoot-conversions
description: Investigates conversion upload issues and generates a structured diagnostic report based on Google Ads API conversion summaries and alerts.
---

<instructions>

# Troubleshoot Conversions

This skill investigates conversion upload issues and generates a structured diagnostic report by executing the mandatory conversion troubleshooting workflow.

## 1. Execution Instructions [MANDATORY]

When invoked to troubleshoot conversions:
1. Locate the required `customer_id` (from context or `customer_id.txt`). If missing, prompt the user.
2. Execute the mandatory diagnostic collector script within the sequestered virtual environment. As it runs, it will output high-level client and action summaries to stdout to inform your analysis:
```bash
./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py --customer_id <customer_id> --api_version <api_version>
```
3. Note the consolidated troubleshooting report path returned by the script (e.g., `saved/data/conversion_troubleshooting_report_<epoch>.txt`).

## 2. Diagnostic Queries & Calculations

When analyzing conversion data directly:
- **Diagnostic Summaries**: Query both `offline_conversion_upload_client_summary` and `offline_conversion_upload_conversion_action_summary`.
- **Attributes & Totals**: Use `successful_count` and `failed_count`. Calculate daily total as `successful_count + failed_count + pending_count` (top-level `total_event_count` is only available on parent resources).
- **Alert Inspection**: Access `alerts` (OfflineConversionAlert) at the top-level resource. Inspect `alert.error` oneof via `WhichOneof("error_code")` and report `error_percentage`. If summaries are empty, append exactly: `Reason: No standard offline imports detected in last 90 days`.

## 3. Pre-Upload CSV Validation

Before uploading any conversion CSV data file, execute the programmatic validation utility to statically check formatting and timestamp rules:
```bash
./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py --csv_path <path_to_csv> --api_version <api_version>
```

</instructions>

