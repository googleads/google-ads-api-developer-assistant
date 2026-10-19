---
description: Synchronizes and updates cloned Google Ads API client libraries from GitHub.
argument-description: [language] Optional language: python, php, ruby, java, dotnet, or all
---

# Sync Client Libraries (`/sync-client-libs`)

Updates and synchronizes Google Ads API client libraries in `client_libs/`.

## Instructions:
1. **Extract Parameters**:
   - Extract target language from `$ARGUMENTS` (`python`, `php`, `ruby`, `java`, `dotnet`, or `all`).
2. **Execute Sync**:
   - Run the client library synchronization script:
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/sync-client-libs/scripts/sync_client_libs.py"
     ```
   - Or pull the specified repository in `client_libs/`.
3. **Verify System Site-Directory & Alert**:
   - When a new version of the python client library or `google-ads` is discovered, check the installed version in the Python system site-directory (e.g. via `site.getsitepackages()` and `importlib.metadata.version('google-ads')`).
   - If the system site-directory version does not match the latest discovered release, immediately alert the user to the mismatch.
   - Ask the user if they would like Gemini to upgrade the system version.
   - If the user replies yes, update the system package for them (`python3 -m pip install --upgrade google-ads` or `sync_client_libs.py --upgrade_system`).
4. **Report Status**:
   - List updated client library repositories, system site-directory package status, and latest discovered API versions.
