---
name: troubleshoot-conversions
description: Investigates Google Ads offline conversion upload issues, validates conversion CSV files, samples recent GCLIDs, and generates diagnostic reports. Use when debugging conversion upload errors or pre-validating conversion CSV payloads. Don't use for general GAQL query validation (use validate-gaql) or mutating campaigns/budgets (use execute-mutation).
---

# Troubleshoot Conversions

> **API version:** `--api_version` is optional. Omit it to use the active version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package). Pass `--api_version vN` only to override it.

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

Use this skill when investigating offline conversion upload failures, validating conversion upload CSV files, or generating conversion health diagnostic reports.

## Protocol

1. **Diagnostic Collection:** Run the `troubleshoot_conversions.py` script:
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py" --customer_id <customer_id>
   ```

2. **CSV Pre-Validation:** Before attempting conversion uploads, validate the CSV format:
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/validate_conversion_upload.py" --csv_path <path_to_csv>
   ```

3. **Retrieve Recent GCLIDs:**
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/troubleshoot-conversions/scripts/get_recent_gclids.py" --customer_id <customer_id>
   ```

4. **Reporting Mandate:**
   - Diagnostic outputs must be prepended with `"Created by the Google Ads API Developer Assistant"`.
   - Results are generated in `saved/data/conversion_troubleshooting_report_<epoch>.txt`.
   - `troubleshoot_conversions.py` masks GCLIDs (first and last 6 characters) in the console output, the report file, and `--json` output. Add `--show-gclids` only when the user asks for full GCLIDs.
