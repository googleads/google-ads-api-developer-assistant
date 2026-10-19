---
description: Generates or validates Performance Max Asset Group URL expansion webpage exclusion filters.
argument-description: [customer_id] [asset_group_id] Optional customer ID and Asset Group ID
---

# Performance Max Webpage Filter (`/pmax-filter`)

Configures Asset Group-level URL expansion exclusions (webpage listing filter trees) for Performance Max campaigns without requiring Page Feeds.

## Instructions:
1. **Extract Parameters**:
   - Extract `customer_id`, `asset_group_id`, and `url_exclusion` rules from `$ARGUMENTS`.
   - Resolve API version from `config/assistant_config` (`api_version`).

2. **Execute Script / Filter Generation**:
   - Run the listing filter dry-run validation script (`validate_only=True` by default):
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" --customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --url_exclusion "<url_exclusion>" --api_version "<api_version>"
     ```
   - Ensure the filter uses `vertical = WEBPAGE` and `AssetGroupListingGroupFilter` exclusion trees (`listing_source = ASSET_GROUP`).

3. **Output Format**:
   - Display generated Python code in `saved/code/` configured with `GoogleAdsClient` and `GoogleAdsException` handling.
   - Follow the 4-Step HITL Mutation Verification & Consequence Disclosure Protocol (`execute-mutation` skill) before running any live mutation (`--execute`).
