---
name: validate-gaql
description: Validates Google Ads Query Language (GAQL) queries via 4-step static analysis and live API dry-runs.
---

# Validate GAQL Skill

Before presenting or running any GAQL query, pass this 4-step sequence:

1. **Schema Discovery:** Verify field existence, selectability, and filterability using `search_google_ads_fields`.
2. **Compatibility Check:** Verify all selected fields are compatible with the primary resource.
3. **Static Analysis:**
   - `WHERE` fields MUST be in `SELECT` (unless date segments).
   - **NO `OR` operator:** Replace `OR` with `IN` or split into multiple queries.
   - **NO `FROM` in Metadata:** Queries to `GoogleAdsFieldService` MUST NOT contain a `FROM` clause.
   - **Segment Renames:** In v23+, `segments.hour` was renamed to `segments.hour_of_day`.
4. **Runtime Dry Run:** Execute API dry-run search request against target customer ID:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/validate-gaql/scripts/validate_gaql.py" --query "<query>" --customer_id "<customer_id>" --api_version "<api_version>"
   ```

## Local Response Caching

`validate_gaql.py` caches successful query validation results locally in both an in-memory dictionary and an on-disk JSON store (`saved/data/gaql_validation_cache.json`, or overridden via `GAQL_CACHE_PATH` / `--cache-path`):

- **Cache Key:** Keyed by the SHA-256 hex digest of the normalized `(query + api_version)` pair (`SHA-256("<trimmed_query>|<normalized_api_version>")`).
- **Cache Hit Behavior:** When a valid, non-expired entry matches `(query, api_version)`, `validate_gaql.py` skips redundant API dry-run calls and immediately returns `SUCCESS: GAQL query is structurally valid. (cached)`.
- **Cache Expiration (TTL):** Entries expire after 24 hours (`86400` seconds) by default, configurable via `--cache-ttl <seconds>`.
- **Cache Control Flags:**
  - `--no-cache` (`--no_cache`): Bypass the local validation cache and force a fresh dry-run.
  - `--clear-cache` (`--clear_cache`): Invalidate and clear all cached validation entries before running.
  - `--cache-path <path>` (`--cache_path`): Custom file path for the JSON validation cache.
  - `--cache-ttl <seconds>` (`--cache_ttl`): Custom TTL in seconds for cached entries.

