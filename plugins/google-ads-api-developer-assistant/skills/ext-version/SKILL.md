---
name: ext-version
description: Retrieves the current Google Ads API Developer Assistant plugin version from plugin.json and the active Google Ads API version. Use when verifying the assistant version, active API version, or environment diagnostics. Don't use for upgrading client libraries (use sync-client-libs) or running GAQL queries (use validate-gaql).
---

# Get Extension Version

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

Use this skill to retrieve the version of the Google Ads API Developer Assistant and the active Google Ads API version. This is useful when diagnosing issues, verifying the environment, or when the user explicitly asks for version details.

## Protocol

1. **Execution:** Run the version extraction scripts in the Python environment:

    * **Assistant plugin version (`plugin.json`):**
      ```bash
      GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
      python3 "$GADS_DIR/skills/ext-version/scripts/get_extension_version.py"
      ```

    * **Active Google Ads API version (read-only, without mutating config):**
      ```bash
      GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
      python3 "$GADS_DIR/skills/ext-version/scripts/get_latest_api_version.py" --active
      ```

2. **Output Handling:**
    * `get_extension_version.py` prints the assistant plugin version string (e.g., `4.1.0`) to `stdout` (or exits with code `1` on `stderr` if `plugin.json` is missing or invalid).
    * `get_latest_api_version.py --active` (alias `--no-update`) prints the active Google Ads API version (`v<N>`) that the skill scripts use, without modifying `config/assistant_config`. It checks, in order: `GOOGLE_ADS_API_VERSION`, `api_version` in the active `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package.
    * `get_latest_api_version.py --installed` prints the highest installed version (local `client_libs` and the installed `google-ads` package) without modifying config. With no flag, the script detects that version and writes it to `config/assistant_config`.
    * If the two differ, the scripts use the `--active` value. To make them match, unset `GOOGLE_ADS_API_VERSION` or update `api_version` in `config/assistant_config`.

## When to Use

* When the user asks "What version are you?" or "What is the assistant or API version?".
* Before generating diagnostic reports (to include the version in the report header as per rules).
* When troubleshooting environment-specific issues.
