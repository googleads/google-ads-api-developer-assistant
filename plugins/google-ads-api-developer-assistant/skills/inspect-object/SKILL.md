---
name: inspect-object
description: Inspects the structure of any Google Ads API Protobuf resource, nested message, or Enum.
---

# Inspect Object Skill

> **API version:** `--api_version` is optional. Omit it to use the active version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest version in local `client_libs` and the installed `google-ads` package). Pass `--api_version vN` only to override it.

> **Plugin directory:** Every command starts with a `GADS_DIR=...` line that finds the installed plugin: `CLAUDE_PLUGIN_ROOT` or `GOOGLE_ADS_ASSISTANT_DIR` when set, otherwise the Claude Code install (`~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant`) when running in Claude Code or when the Antigravity install (`~/.gemini/config/plugins/google-ads-api-developer-assistant`) is missing. Run both lines together in one command.

NEVER guess the structure of an API object or Enum type.

1. **Mandatory Inspection:** Use the object inspector to dynamically inspect any resource, message, or Enum structure.
2. **Usage:** Verify selectable fields, nested protobuf messages, and enum values before generating queries or code.
3. **Version Parity Check:** If the installed `google-ads` package version does not match the `client_libs/google-ads-python` version used for protobuf inspection, issue a warning to the user regarding potential schema differences.
4. **CLI Inspection:**
   ```bash
   GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
   python3 "$GADS_DIR/skills/inspect-object/scripts/inspect_object.py" --object_name <resource_or_enum>
   ```
