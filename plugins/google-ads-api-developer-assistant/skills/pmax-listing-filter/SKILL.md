---
name: pmax-listing-filter
description: Validates or generates commands to configure Asset Group URL expansion filters (webpage exclusions) for Performance Max campaigns.
---

# Performance Max Listing Filter Skill

1. **Asset Group URL Filtering:** When asked to filter or restrict URL expansion for specific Asset Groups without using Page Feeds, use webpage exclusion listing trees (`vertical = WEBPAGE`).
2. **Correct Scoping:** Do not falsely claim webpage URL contains filters are unsupported at the Asset Group level. Avoid recommending campaign-level exclusions when Asset Group-level exclusions are requested.
3. **Execution Script:**
   ```bash
   python3 "${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}/skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py" --customer_id "<customer_id>" --asset_group_id "<asset_group_id>" --api_version "<api_version>"
   ```
