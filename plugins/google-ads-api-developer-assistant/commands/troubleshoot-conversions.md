---
description: Investigates conversion upload issues, validates conversion CSVs, and generates diagnostic reports.
argument-description: [customer_id] [csv_path] Optional customer ID and CSV file path to validate
---

# Troubleshoot Conversions (`/troubleshoot-conversions`)

Investigates offline conversion upload failures, validates upload CSV formats, and samples recent GCLIDs.

## Instructions:
1. **Extract Parameters**:
   - Extract `customer_id` and/or `csv_path` from `$ARGUMENTS`.
   - If `customer_id` is not provided, use `config/assistant_config` (`customer_id`) or prompt the user.
   - Omit `--api_version` to use the active API version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest installed version). Pass `--api_version vN` only when the user names a version.
   - The first line of each command sets `GADS_DIR` to the installed plugin directory; run both lines together as one command.

2. **Execute Diagnostics**:
   - **If a CSV path is provided**: Validate the conversion upload file:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/validate_conversion_upload.py" --csv_path "<csv_path>"
     ```
   - **To diagnose upload history & errors**:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py" --customer_id "<customer_id>"
     ```
   - **To sample recent GCLIDs**:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/get_recent_gclids.py" --customer_id "<customer_id>"
     ```

3. **Output Format**:
   - Prepend diagnostic output with `"Created by the Google Ads API Developer Assistant"`.
   - Report validation errors (timestamp format `yyyy-mm-dd hh:mm:ss+|-hh:mm`, `conversion_time > click_time` constraint, required columns).
   - Provide actionable remediation steps.
