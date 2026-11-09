---
name: ext-version
description: Retrieves the current version of the Google Ads API Developer Assistant from plugin.json.
---

# Get Extension Version

Use this skill to retrieve the version of the Google Ads API Developer Assistant and the active Google Ads API version. This is useful when diagnosing issues, verifying the environment, or when the user explicitly asks for version details.

## Protocol

1. **Execution:** Run the version extraction scripts in the Python environment:

    * **Assistant plugin version (`plugin.json`):**
      ```bash
      python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/ext-version/scripts/get_extension_version.py"
      ```

    * **Active Google Ads API version (read-only, without mutating config):**
      ```bash
      python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/ext-version/scripts/get_latest_api_version.py" --no-update
      ```

2. **Output Handling:**
    * `get_extension_version.py` prints the assistant plugin version string (e.g., `4.1.0`) to `stdout` (or exits with code `1` on `stderr` if `plugin.json` is missing or invalid).
    * `get_latest_api_version.py --no-update` prints the resolved active Google Ads API version (e.g., `v26`) without modifying `config/assistant_config`.

## When to Use

* When the user asks "What version are you?" or "What is the assistant or API version?".
* Before generating diagnostic reports (to include the version in the report header as per rules).
* When troubleshooting environment-specific issues.
