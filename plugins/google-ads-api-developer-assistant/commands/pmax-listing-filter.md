---
description: Generates or validates Performance Max Asset Group URL expansion webpage exclusion filters.
argument-description: [customer_id] [asset_group_id] Optional customer ID and Asset Group ID
---

# Performance Max Listing Filter (`/pmax-listing-filter`)

Configures Asset Group-level URL expansion exclusions (`AssetGroupListingGroupFilter` with `listing_source = WEBPAGE`) for Performance Max campaigns without requiring Page Feeds.

## Instructions:
1. **Extract Parameters**:
   - Extract `customer_id`, `asset_group_id`, and `url_exclusion` rules from `$ARGUMENTS`.
   - Omit `--api_version` to use the active API version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest installed version). Pass `--api_version vN` only when the user names a version.
   - The first line of each command sets `GADS_DIR` to the installed plugin directory; run both lines together as one command.

2. **Execute Script / Filter Generation**:
   - Run the listing filter dry-run validation via `run_mutation.py` (or directly with `create_pmax_webpage_filter.py` for standalone `validate_only=True` preview) to generate the HITL dry-run receipt:
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
   - Ensure webpage URL exclusions use `listing_source = WEBPAGE` (`ListingGroupFilterListingSourceEnum.WEBPAGE`) and root-level `UNIT_EXCLUDED` `AssetGroupListingGroupFilter` nodes (note: Shopping `SUBDIVISION` nodes require an explicit `"Everything else"` sibling child node).

3. **Output Format**:
   - Display generated Python code in `saved/code/` configured with `GoogleAdsClient` and `GoogleAdsException` handling.
   - Follow the 4-Step HITL Mutation Verification & Consequence Disclosure Protocol (`execute-mutation` skill) before running any live mutation (`run_mutation.py --execute --script-args ...`).
