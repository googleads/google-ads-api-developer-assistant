---
description: Validates a Google Ads Query Language (GAQL) query via 4-step static analysis and live API dry-runs.
argument-description: <gaql_query> The GAQL query to validate
---

# Validate GAQL (`/validate-gaql`)

Validates Google Ads Query Language (GAQL) queries against Google Ads API schemas using the 4-step validation protocol.

## Instructions:
1. **Extract Parameters**:
   - Extract the query from `$ARGUMENTS`. If not provided, prompt the user for the GAQL query to validate.
   - Omit `--api_version` to use the active API version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest installed version). Pass `--api_version vN` only when the user names a version.
   - The first line of each command sets `GADS_DIR` to the installed plugin directory; run both lines together as one command.
   - Resolve the customer ID from `$ARGUMENTS`, `config/assistant_config` (`customer_id`), or session context.

2. **Execute Validation Protocol**:
   - **Step 1: Schema Discovery** - Verify that all selected and filtered fields exist in the resource schema using `client_libs/google-ads-python` proto definitions or `inspect_object.py`.
   - **Step 2: Compatibility Check** - Verify that all metrics, segments, and attributed resources are selectable together with the primary resource.
   - **Step 3: Static Analysis**:
     - Verify that all fields in `SELECT`, `WHERE`, and `ORDER BY` are compatible with the `FROM` resource (`WHERE` fields do not need to appear in `SELECT`, while core date segments in `SELECT` such as `segments.date` require a finite date filter in `WHERE`).
     - Ensure **NO `OR` operator** is used (GAQL only supports `AND`; suggest `IN` or separate queries).
     - Ensure **NO `FROM` clause** is used for `GoogleAdsFieldService` metadata queries.
     - Ensure no SQL aggregation functions (`SUM()`, `COUNT()`) are used.
     - Ensure valid **hourly segmentation** (`segments.hour` is the valid GAQL field; `segments.hour_of_day` is invalid).
   - **Step 4: Dry-Run Execution** (if credentials and customer ID are available):
     Run `skills/validate-gaql/scripts/validate_gaql.py` (validation results are cached locally keyed by `SHA-256(query + api_version)` in `saved/data/gaql_validation_cache.json`; pass `--no-cache` to bypass or `--clear-cache` to invalidate):
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/validate-gaql/scripts/validate_gaql.py" --query "<query>" --customer_id "<customer_id>"
     ```

3. **Output Format**:
   - Report Status: `PASSED` or `FAILED`.
   - List any syntax, schema, or structural errors with exact correction suggestions.
   - Provide the corrected, copy-ready GAQL query in a code block.
