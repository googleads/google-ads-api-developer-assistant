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
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/ext-version/scripts/get_extension_version.py"
     ```
   - Run the active API version script (read-only; prints the version the skill scripts use):
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/ext-version/scripts/get_latest_api_version.py" --active
     ```
   - Or read `plugin.json` and `config/assistant_config`.

2. **Output Format**:
   - Assistant Plugin Version.
   - Active Google Ads API Version.
