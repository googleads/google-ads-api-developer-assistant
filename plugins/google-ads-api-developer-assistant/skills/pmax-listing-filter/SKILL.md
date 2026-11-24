---
name: pmax-listing-filter
description: Validates and generates Asset Group URL expansion webpage exclusion filters (AssetGroupListingGroupFilter) for Performance Max campaigns. Use when creating or dry-running PMax Asset Group webpage exclusions without Page Feeds. Don't use for Search/AI Max campaigns, general non-PMax mutations (use execute-mutation), or GAQL reporting queries (use validate-gaql).
---

# Performance Max Listing Filter Skill

> **API version:** `--api_version` is optional. Omit it to use the active version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package). Pass `--api_version vN` only to override it.

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

1. **Asset Group URL Filtering:** When asked to filter or restrict URL expansion for specific Asset Groups without using Page Feeds, configure `AssetGroupListingGroupFilter` nodes with `listing_source = WEBPAGE` (`ListingGroupFilterListingSourceEnum.WEBPAGE`) and root-level `UNIT_EXCLUDED` rules (`ListingGroupFilterTypeEnum.UNIT_EXCLUDED`). Note: Shopping product partition trees (`listing_source = SHOPPING`) using `SUBDIVISION` parent nodes require an explicit `"Everything else"` sibling child node.
2. **Correct Scoping:** Do not falsely claim webpage `url_contains` filters are unsupported at the Asset Group level. Avoid recommending campaign-level exclusions when Asset Group-level exclusions are requested.
3. **Standalone Dry-Run Validation (`validate_only=True`):**
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" --customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --url_exclusion "<url_exclusion>"
   ```
4. **HITL Dry-Run Receipt & Live Execution (`run_mutation.py`):**
   To generate the mandatory `saved/data/last_dry_run.json` receipt and execute live after user confirmation, invoke `create_pmax_webpage_filter.py` through `run_mutation.py`:
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/execute-mutation/scripts/run_mutation.py" \
     --script "$GADS_DIR/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" \
     --dry-run \
     --customer-id "<customer_id>" \
     --operation "AssetGroupListingGroupFilterService.mutate_asset_group_listing_group_filters on AssetGroup <asset_group_id>" \
     --before "<Current Asset Group Webpage Filters>" \
     --after "Root-level UNIT_EXCLUDED AssetGroupListingGroupFilter (listing_source = WEBPAGE) matching '<url_exclusion>'" \
     --consequences "Restricts Performance Max URL expansion traffic from landing pages matching '<url_exclusion>'" \
     --reversibility "REVERSIBLE" \
     --script-args '--customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --url_exclusion "<url_exclusion>"'
   ```
