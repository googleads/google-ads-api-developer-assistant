---
description: Inspects Google Ads API Protobuf resources, messages, fields, and Enum types.
argument-description: <object_name> The resource, message, or Enum name to inspect (e.g., Campaign, CampaignStatusEnum)
---

# Inspect Object (`/inspect-object`)

Dynamically inspects the fields, data types, nested messages, and Enum values of any Google Ads API object using `client_libs/google-ads-python` proto definitions.

## Instructions:
1. **Extract Parameters**:
   - Extract the object name from `$ARGUMENTS` (e.g. `Campaign`, `AdGroupCriterion`, `CampaignStatusEnum`, `AdGroupAd`, `BiddingStrategy`).
   - If not provided, prompt the user for the object, message, or Enum name to inspect.
   - Omit `--api_version` to use the active API version (`GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the highest installed version). Pass `--api_version vN` only when the user names a version.
   - The first line of each command sets `GADS_DIR` to the installed plugin directory; run both lines together as one command.

2. **Execute Inspection**:
   - Run the inspection script:
     ```bash
     GADS_DIR="${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-}}"; if [ -z "$GADS_DIR" ]; then GADS_DIR="$HOME/.gemini/config/plugins/google-ads-api-developer-assistant"; if [ -n "${CLAUDECODE:-}" ] || [ ! -d "$GADS_DIR" ]; then GADS_DIR="$HOME/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"; fi; fi
     python3 "$GADS_DIR/skills/inspect-object/scripts/inspect_object.py" --object_name "$ARGUMENTS"
     ```
   - If the script is unavailable in the environment, inspect the proto files directly in `client_libs/google-ads-python/google/ads/googleads/<api_version>/`.

3. **Output Format**:
   - **Object Type**: Identify whether the symbol is a Resource, Message, or Enum.
   - **Selectable / Filterable Fields**: List core fields with data types and descriptions.
   - **Enum Values**: For Enum types, list all possible values and their meanings.
   - **Nested Protobuf Messages**: Show the structure of sub-messages.
