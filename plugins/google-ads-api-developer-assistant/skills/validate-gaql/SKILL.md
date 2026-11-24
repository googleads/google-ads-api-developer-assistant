---
name: validate-gaql
description: Validates Google Ads Query Language (GAQL) queries via 4-step schema discovery, compatibility checks, static analysis, and live validate_only API dry-runs with local caching. Use before presenting or running any GAQL query. Don't use for mutating Google Ads resources (use execute-mutation) or inspecting single Protobuf enums/messages (use inspect-object).
---

# Validate GAQL Skill

> **API version:** `--api_version` is optional. Omit it to use the active version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package). Pass `--api_version vN` only to override it.

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

Before presenting or running any GAQL query, pass this 4-step sequence:

1. **Schema Discovery:** Verify field existence, selectability, and filterability using `search_google_ads_fields`.
2. **Compatibility Check:** Verify all selected fields are compatible with the primary resource.
3. **Static Analysis:**
   - All fields in `SELECT`, `WHERE`, and `ORDER BY` must be compatible with the `FROM` resource (`WHERE` fields do not need to appear in `SELECT`, while core date segments in `SELECT` such as `segments.date` require a finite date filter in `WHERE`).
   - **NO `OR` operator:** Replace `OR` with `IN` or split into multiple queries.
   - **NO `FROM` in Metadata:** Queries to `GoogleAdsFieldService` MUST NOT contain a `FROM` clause.
   - **Hourly Segment:** Use `segments.hour` (`segments.hour_of_day` is invalid in GAQL and fails with `UNRECOGNIZED_FIELD`).
4. **Runtime Dry Run:** Execute API dry-run search request against target customer ID:
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/validate-gaql/scripts/validate_gaql.py" --query "<query>" --customer_id "<customer_id>"
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

