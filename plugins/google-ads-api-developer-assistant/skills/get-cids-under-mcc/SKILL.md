---
name: get-cids-under-mcc
description: Retrieves a list of all child customer account IDs (CIDs) under a given Manager Account (MCC).
---

# Get CIDs Under MCC

> **API version:** `--api_version` is optional. Omit it to use the active version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package). Pass `--api_version vN` only to override it.

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

Use this skill to retrieve the hierarchy of child accounts under a Google Ads Manager Account (MCC). This is useful when you need to perform operations across multiple client accounts or understand the account structure.

## Protocol

1. **Identify MCC ID:** Search the session context or user prompt for the Manager Account ID (MCC). If not explicitly provided, ask the user to provide the MCC ID before proceeding.

2. **Execute Retrieval:** Run the retrieval script in the python environment:

    * **To get a summary count only:**
        ```bash
        GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
        python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id <mcc_id>
        ```

    * **To print the detailed list to console:**
        ```bash
        GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
        python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id <mcc_id> --print_cids
        ```

    * **To save the list to a CSV file (saved in `saved/data/`):**
        ```bash
        GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
        python3 "$GADS_DIR/skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py" --customer_id <mcc_id> --save_csv
        ```

3. **Output Processing:**
    * If `--print_cids` was used, parse the console output to get the CIDs, their depth level, and whether they are sub-managers.
    * If `--save_csv` was used, verify the file was created.
