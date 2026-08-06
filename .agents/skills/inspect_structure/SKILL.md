---
name: inspect-structure
description: Provides exact structural field definitions and types for Google Ads API objects.
---

# Inspect Object Structure

Use this skill to view the exact structural field definitions, types, labels (repeated vs. optional), and enum mappings for any Google Ads API resource or object.

## Protocol

1. **Identify the Target Object:** Determine the name of the message resource or enum you need to inspect (e.g., `Campaign`, `AdGroupStatusEnum`).
2. **Retrieve API Version:** Make sure you know the current API version (cached in [api_version.txt](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/config/api_version.txt)).
3. **Execute the Inspect Structure Utility:** Run the utility script [inspect_structure.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/inspect_structure/scripts/inspect_structure.py):
   ```bash
   ./.venv/bin/python3 .agents/skills/inspect_structure/scripts/inspect_structure.py --object_name <ObjectName> --api_version <api_version>
   ```
4. **Analyze the Structured Output:**
   - **Enums:** Displays the name of each value alongside its corresponding integer value.
   - **Messages:** Displays a formatted table of all fields containing:
     - **Field Name:** The programmatic field name.
     - **Label:** Whether the field is `OPTIONAL` or `REPEATED`.
     - **Type Name:** The specific message name or enum class (if nested/referenced) or the underlying scalar type.
     - **Underlying Type:** The primitive type representation (e.g. `STRING`, `INT64`, `BOOL`, `ENUM`).
