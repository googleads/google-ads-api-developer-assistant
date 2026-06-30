---
name: troubleshoot-conversions
description: Investigates conversion upload issues, generates structured diagnostic reports, and validates conversion CSVs.
---

# Troubleshoot Conversions

Use this skill to diagnose issues with offline conversion uploads (e.g., GCLID uploads failing, low success rates) and to validate conversion data CSVs before uploading them.

---

## Protocol 1: Diagnostic & Reporting (When troubleshooting existing uploads)

1.  **Identify Customer ID:** Retrieve the `customer_id` from the context or `customer_id.txt`. If missing, ask the user.
2.  **Run Diagnostics:** Execute the diagnostic collector script in the sequestered virtual environment:

    ```bash
    ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py \
      --customer_id <customer_id> \
      --api_version <api_version>
    ```

3.  **Read and Present Report:** 
    *   Locate the generated report at the path printed by the script (e.g., `saved/data/conversion_troubleshooting_report_<epoch>.txt`).
    *   **Mandatory:** Read this file and present its full contents to the user in your response. The report must contain the sections:
        *   `1. Introductory Analysis`
        *   `2. Primary Errors & Critical Issues`
        *   `3. General Health & Technical Findings`
    *   Ensure the output starts with the header: `Created by the Google Ads API Developer Assistant`.

---

## Protocol 2: Pre-Upload CSV Validation (Before uploading new conversions)

1.  **Validate CSV:** Before attempting to upload any conversion CSV, run the validation utility:

    ```bash
    ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py \
      --csv_path <path_to_csv> \
      --api_version <api_version>
    ```

2.  **Handle Output:**
    *   **If Success:** Proceed with the upload process.
    *   **If Failure:** Report the specific row errors to the user and ask them to correct the CSV.

---

## Examples

### Example 1: Running Diagnostics
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py \
      --customer_id 1234567890 \
      --api_version v17
    ```
*   **Console Output:**
    ```
    === Conversion Diagnostic Summary for Customer 1234567890 ===
    ...
    Consolidated troubleshooting report: saved/data/conversion_troubleshooting_report_1719750000.txt
    ```
*   **Agent Action:** Read `saved/data/conversion_troubleshooting_report_1719750000.txt` and display it to the user.

### Example 2: Validating a CSV (Success)
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py \
      --csv_path saved/csv/my_conversions.csv \
      --api_version v17
    ```
*   **Output:**
    ```
    --- Validating Conversion Upload CSV: saved/csv/my_conversions.csv ---
    SUCCESS: Conversion Upload CSV parsed cleanly with valid formatting rules.
    ```
