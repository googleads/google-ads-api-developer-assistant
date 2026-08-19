---
description: Validates a Google Ads Query Language (GAQL) query via 4-step static analysis and live API dry-runs.
argument-description: <gaql_query> The GAQL query to validate
---

# Validate GAQL (`/validate-gaql`)

Validates Google Ads Query Language (GAQL) queries against Google Ads API schemas using the 4-step validation protocol.

## Instructions:
1. **Extract Parameters**:
   - Extract the query from `$ARGUMENTS`. If not provided, prompt the user for the GAQL query to validate.
   - Resolve the target API version from `config/api_version.txt` or the latest discovered version in `client_libs/`.
   - Resolve the customer ID from `$ARGUMENTS`, `config/customer_id.txt`, or session context.

2. **Execute Validation Protocol**:
   - **Step 1: Schema Discovery** - Verify that all selected and filtered fields exist in the resource schema using `client_libs/google-ads-python` proto definitions or `inspect_object.py`.
   - **Step 2: Compatibility Check** - Verify that all metrics, segments, and attributed resources are selectable together with the primary resource.
   - **Step 3: Static Analysis**:
     - Check that `WHERE` clause fields are in `SELECT` (unless date segments).
     - Ensure **NO `OR` operator** is used (GAQL only supports `AND`; suggest `IN` or separate queries).
     - Ensure **NO `FROM` clause** is used for `GoogleAdsFieldService` metadata queries.
     - Ensure no SQL aggregation functions (`SUM()`, `COUNT()`) are used.
     - Ensure **segment renames** are respected (in v23+, `segments.hour` was renamed to `segments.hour_of_day`).
   - **Step 4: Dry-Run Execution** (if credentials and customer ID are available):
     Run `skills/validate-gaql/scripts/validate_gaql.py`:
     ```bash
     python3 skills/validate-gaql/scripts/validate_gaql.py --query "<query>" --customer_id "<customer_id>" --api_version "<api_version>"
     ```

3. **Output Format**:
   - Report Status: `PASSED` or `FAILED`.
   - List any syntax, schema, or structural errors with exact correction suggestions.
   - Provide the corrected, copy-ready GAQL query in a code block.
