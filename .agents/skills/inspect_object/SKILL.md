---
name: inspect-object
description: Inspects the structure of any Google Ads API Protobuf resource, nested message, or Enum.
---

# Inspect Protobuf Object or Enum

Use this skill to dynamically inspect the fields, types, and values of any Google Ads API resource, message, or Enum. 

**CRITICAL:** You MUST NOT guess the structure of any API object or Enum. Always use this skill to verify the schema before generating code or writing GAQL queries.

## Protocol

1.  **Identify Target:** Determine the name of the Protobuf message or Enum you need to inspect (e.g., `Campaign`, `AdGroupStatusEnum`).
2.  **Execute Inspection:** Run the utility script in the sequestered virtual environment, passing the object name and the confirmed API version.

    ```bash
    ./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name <object_name> --api_version <api_version>
    ```

3.  **Analyze Output:**
    *   **For Messages:** The output will list all fields, their labels (`OPTIONAL` or `REPEATED`), and their types. Use this to verify field names and nesting.
    *   **For Enums:** The output will list all valid enum names and their corresponding integer values. Use this to verify valid status or type values.

---

## Examples

### Example 1: Inspecting a Message Resource
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name Campaign --api_version v17
    ```
*   **Output (Truncated):**
    ```
    === Message: Campaign ===
      - resource_name                       [OPTIONAL] : 9
      - id                                  [OPTIONAL] : 3
      - name                                [OPTIONAL] : 9
      - status                              [OPTIONAL] : CampaignStatusEnum
      - advertising_channel_type            [OPTIONAL] : AdvertisingChannelTypeEnum
    ```

### Example 2: Inspecting an Enum
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name CampaignStatusEnum --api_version v17
    ```
*   **Output:**
    ```
    === Enum: CampaignStatusEnum ===
      - UNSPECIFIED = 0
      - UNKNOWN = 1
      - ENABLED = 2
      - PAUSED = 3
      - REMOVED = 4
    ```
