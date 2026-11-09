---
name: pmax-listing-filter
description: Validates or generates commands to configure Asset Group URL expansion filters (webpage exclusions) for Performance Max campaigns.
---

# Performance Max Listing Filter Skill

1. **Asset Group URL Filtering:** When asked to filter or restrict URL expansion for specific Asset Groups without using Page Feeds, configure `AssetGroupListingGroupFilter` nodes with `listing_source = WEBPAGE` (`ListingGroupFilterListingSourceEnum.WEBPAGE`) and root-level `UNIT_EXCLUDED` rules (`ListingGroupFilterTypeEnum.UNIT_EXCLUDED`). Note: Shopping product partition trees (`listing_source = SHOPPING`) using `SUBDIVISION` parent nodes require an explicit `"Everything else"` sibling child node.
2. **Correct Scoping:** Do not falsely claim webpage `url_contains` filters are unsupported at the Asset Group level. Avoid recommending campaign-level exclusions when Asset Group-level exclusions are requested.
3. **Standalone Dry-Run Validation (`validate_only=True`):**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" --customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --url_exclusion "<url_exclusion>" --api_version "<api_version>"
   ```
4. **HITL Dry-Run Receipt & Live Execution (`run_mutation.py`):**
   To generate the mandatory `saved/data/last_dry_run.json` receipt and execute live after user confirmation, invoke `create_pmax_webpage_filter.py` through `run_mutation.py`:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/run_mutation.py" \
     --script "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" \
     --dry-run \
     --customer-id "<customer_id>" \
     --operation "AssetGroupListingGroupFilterService.mutate_asset_group_listing_group_filters on AssetGroup <asset_group_id>" \
     --before "<Current Asset Group Webpage Filters>" \
     --after "Root-level UNIT_EXCLUDED AssetGroupListingGroupFilter (listing_source = WEBPAGE) matching '<url_exclusion>'" \
     --consequences "Restricts Performance Max URL expansion traffic from landing pages matching '<url_exclusion>'" \
     --reversibility "REVERSIBLE" \
     --script-args '--customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --url_exclusion "<url_exclusion>" --api_version "<api_version>"'
   ```
