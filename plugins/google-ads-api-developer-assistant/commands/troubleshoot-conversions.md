---
description: Investigates conversion upload issues, validates conversion CSVs, and generates diagnostic reports.
argument-description: [customer_id] [csv_path] Optional customer ID and CSV file path to validate
---

# Troubleshoot Conversions (`/troubleshoot-conversions`)

Investigates offline conversion upload failures, validates upload CSV formats, and samples recent GCLIDs.

## Instructions:
1. **Extract Parameters**:
   - Extract `customer_id` and/or `csv_path` from `$ARGUMENTS`.
   - If `customer_id` is not provided, use `config/customer_id` or prompt the user.
   - Resolve API version from `config/api_version.txt`.

2. **Execute Diagnostics**:
   - **If a CSV path is provided**: Validate the conversion upload file:
     ```bash
     python3 skills/troubleshoot-conversions/scripts/validate_conversion_upload.py --csv_path "<csv_path>" --api_version "<api_version>"
     ```
   - **To diagnose upload history & errors**:
     ```bash
     python3 skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py --customer_id "<customer_id>" --api_version "<api_version>"
     ```
   - **To sample recent GCLIDs**:
     ```bash
     python3 skills/troubleshoot-conversions/scripts/get_recent_gclids.py --customer_id "<customer_id>" --api_version "<api_version>"
     ```

3. **Output Format**:
   - Prepend diagnostic output with `"Created by the Google Ads API Developer Assistant"`.
   - Report validation errors (timestamp format `yyyy-mm-dd hh:mm:ss+|-hh:mm`, `conversion_time > click_time` constraint, required columns).
   - Provide actionable remediation steps.
