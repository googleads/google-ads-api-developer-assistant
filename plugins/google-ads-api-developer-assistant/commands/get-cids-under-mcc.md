---
description: Retrieves all child customer account IDs (CIDs) under a Manager Account (MCC).
argument-description: <mcc_customer_id> The Manager Account ID (MCC) to query
---

# Get CIDs Under MCC (`/get-cids-under-mcc`)

Retrieves the complete account hierarchy and child CIDs under a Google Ads Manager Account (MCC).

## Instructions:
1. **Extract Parameters**:
   - Extract the Manager Account ID (MCC) from `$ARGUMENTS`.
   - If not provided, check `config/assistant_config` (`customer_id`) or prompt the user.
   - Omit `--api_version` to use the active API version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest installed version). Pass `--api_version vN` only when the user names a version.
   - The first line of each command sets `GADS_DIR` to the installed plugin directory; run both lines together as one command.

2. **Execute Retrieval**:
   - Run the hierarchy retrieval script:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id "<mcc_customer_id>" --print_cids
     ```
   - If the user requested saving to CSV:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id "<mcc_customer_id>" --save_csv
     ```
   - If the user requested structured JSON output:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id "<mcc_customer_id>" --json
     ```

3. **Output Format**:
   - Total number of child accounts found.
   - Hierarchical list with CID (`customer_client.id`), descriptive name (`customer_client.descriptive_name`), depth level (`customer_client.level`), status (`customer_client.status`), and account type (client vs. sub-manager via `customer_client.manager`).
   - If saved to CSV, provide the file path in `saved/data/`.
