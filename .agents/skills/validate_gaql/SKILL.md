---
name: validate-gaql
description: Validates Google Ads Query Language (GAQL) queries via static analysis and API dry-runs.
---

# Validate GAQL

Use this skill to validate GAQL queries before executing them or presenting them to the user. This prevents runtime errors due to syntax issues, unsupported operators, or resource-specific constraints.

## Protocol

1.  **Schema Discovery:** Always verify field existence, selectability, and filterability using `GoogleAdsFieldService.search_google_ads_fields`.
2.  **Compatibility Check:** Query the primary resource's `selectable_with` attribute to ensure all selected fields can be co-selected.
3.  **Static Analysis:** Manually verify the query against these hard constraints:
    *   `WHERE` fields MUST be in the `SELECT` clause (except for core date segments).
    *   The `OR` operator is **forbidden** in the `WHERE` clause.
    *   Metadata queries (`google_ads_field`) MUST NOT contain a `FROM` clause.
    *   Metadata queries MUST NOT use resource prefixes (e.g., use `name`, not `google_ads_field.name`).
4.  **Runtime Dry Run:** Execute the validator script in the sequestered virtual environment:

    ```bash
    ./.venv/bin/python3 .agents/skills/validate_gaql/scripts/validate_gaql.py --customer_id <customer_id> --api_version <api_version> << 'EOF'
    <YOUR_GAQL_QUERY>
    EOF
    ```

## Examples

### Example 1: Avoiding the Forbidden `OR` Operator
*   **Incorrect (Will Fail):**
    ```sql
    SELECT campaign.id, campaign.status 
    FROM campaign 
    WHERE campaign.status = 'PAUSED' OR campaign.status = 'ENABLED'
    ```
*   **Correct (Use `IN`):**
    ```sql
    SELECT campaign.id, campaign.status 
    FROM campaign 
    WHERE campaign.status IN ('PAUSED', 'ENABLED')
    ```

### Example 2: Metadata Query (No `FROM` clause, No Prefixes)
*   **Incorrect (Will Fail):**
    ```sql
    SELECT google_ads_field.name 
    FROM google_ads_field 
    WHERE google_ads_field.name = 'campaign.id'
    ```
*   **Correct:**
    ```sql
    SELECT name 
    WHERE name = 'campaign.id'
    ```

### Example 3: Date Segment Constraint
*   **Incorrect (Will Fail - selects date segment but has no date filter):**
    ```sql
    SELECT campaign.id, segments.date 
    FROM campaign
    ```
*   **Correct (Include `DURING` or `BETWEEN`):**
    ```sql
    SELECT campaign.id, segments.date 
    FROM campaign 
    WHERE segments.date DURING LAST_30_DAYS
    ```

## Workflow Integration
*   **On Success:** Proceed to integrate the validated query into your code or response.
*   **On Failure:** Analyze the validator output, correct the query, and restart the validation protocol from Step 1.
