---
description: Displays the current version of the Google Ads API Developer Assistant and active API version.
argument-description: 
---

# Extension Version (`/ext-version`)

Retrieves and prints the current Google Ads API Developer Assistant version and active API version.

## Instructions:
1. **Retrieve Versions**:
   - Run the version retrieval script:
     ```bash
     python3 skills/ext-version/scripts/get_extension_version.py
     ```
   - Run the latest API version script:
     ```bash
     python3 skills/ext-version/scripts/get_latest_api_version.py
     ```
   - Or read `plugin.json` and `config/api_version.txt`.

2. **Output Format**:
   - Assistant Plugin Version.
   - Active Google Ads API Version.
