---
name: troubleshoot-conversions
description: Investigates conversion upload issues, generates structured diagnostic reports, and validates conversion CSVs.
---

# Troubleshoot Conversions

Use this skill when investigating offline conversion upload failures, validating conversion upload CSV files, or generating conversion health diagnostic reports.

## Protocol

1. **Diagnostic Collection:** Run the `troubleshoot_conversions.py` script:
   ```bash
   python3 skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py --customer_id <customer_id> --api_version <api_version>
   ```

2. **CSV Pre-Validation:** Before attempting conversion uploads, validate the CSV format:
   ```bash
   python3 skills/troubleshoot-conversions/scripts/validate_conversion_upload.py --csv_path <path_to_csv> --api_version <api_version>
   ```

3. **Retrieve Recent GCLIDs:**
   ```bash
   python3 skills/troubleshoot-conversions/scripts/get_recent_gclids.py --customer_id <customer_id> --api_version <api_version>
   ```

4. **Reporting Mandate:**
   - Diagnostic outputs must be prepended with `"Created by the Google Ads API Developer Assistant"`.
   - Results are generated in `saved/data/conversion_troubleshooting_report_<epoch>.txt`.
