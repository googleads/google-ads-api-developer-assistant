---
description: Generates or validates Performance Max Asset Group URL expansion webpage exclusion filters.
argument-description: [customer_id] [asset_group_id] Optional customer ID and Asset Group ID
---

# Performance Max Webpage Filter (`/pmax-filter`)

Configures Asset Group-level URL expansion exclusions (webpage listing filter trees) for Performance Max campaigns without requiring Page Feeds.

## Instructions:
1. **Extract Parameters**:
   - Extract `customer_id`, `asset_group_id`, or URL exclusion rules from `$ARGUMENTS`.
   - Resolve API version from `config/api_version.txt`.

2. **Execute Script / Filter Generation**:
   - Run the listing filter generation script:
     ```bash
     python3 skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py --customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --api_version "<api_version>"
     ```
   - Ensure the filter uses `vertical = WEBPAGE` and `AssetGroupListingGroupFilter` exclusion trees (`listing_source = ASSET_GROUP`).

3. **Output Format**:
   - Display generated Python code configured with `GoogleAdsClient` and `GoogleAdsException` handling.
   - Remind the user of the NO MUTATE policy: code is saved to `~/saved/code/` for review and manual execution.
