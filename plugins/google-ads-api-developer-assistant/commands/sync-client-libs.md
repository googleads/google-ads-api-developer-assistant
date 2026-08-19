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
     python3 skills/sync-client-libs/scripts/sync_client_libs.py
     ```
   - Or pull the specified repository in `client_libs/`.
3. **Report Status**:
   - List updated client library repositories and latest discovered API versions.
