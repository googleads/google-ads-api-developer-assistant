---
name: validate-gaql
description: Performs a dry-run validation of a GAQL query using the Google Ads API validate_only parameter.
---

# Validate GAQL

This skill validates a GAQL query by performing a dry-run execution against the Google Ads API.

## Usage

1. **Schema Discovery:** Use `GoogleAdsFieldService.search_google_ads_fields` to verify field existence, selectability, and filterability.
2. **Compatibility Check:** Query the primary resource's `selectable_with` attribute. Verify all selected fields are compatible.
3. **Static Analysis:**
    - `WHERE` fields MUST be in `SELECT` (unless core date segments).
    - `OR` is forbidden. Use `IN` or multiple queries.
    - No `FROM` clause in metadata queries.
    - **Metadata Field Names:** When using `GoogleAdsFieldService.search_google_ads_fields`, field names MUST NOT be prefixed with the resource name (e.g., use `name`, not `google_ads_field.name`). Do NOT use `GoogleAdsService` to query `google_ads_field`. Failure results in `UNRECOGNIZED_FIELD`.
4. **Runtime Dry Run:** Execute the following command:

```bash
./.venv/bin/python3 .agents/skills/validate_gaql/scripts/validate_gaql.py --customer_id <customer_id> --api_version <api_version> << 'EOF'
SELECT campaign.id, campaign.name FROM campaign
EOF
```

- **Success:** Proceed to implementation.
- **Failure:** Fix query based on validator output and restart from Step 1.
