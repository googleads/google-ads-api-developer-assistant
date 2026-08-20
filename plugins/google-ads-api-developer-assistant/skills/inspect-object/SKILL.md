---
name: inspect-object
description: Inspects the structure of any Google Ads API Protobuf resource, nested message, or Enum.
---

# Inspect Object Skill

NEVER guess the structure of an API object or Enum type.

1. **Mandatory Inspection:** Use the object inspector to dynamically inspect any resource, message, or Enum structure.
2. **Usage:** Verify selectable fields, nested protobuf messages, and enum values before generating queries or code.
3. **Version Parity Check:** If the installed `google-ads` package version does not match the `client_libs/google-ads-python` version used for protobuf inspection, issue a warning to the user regarding potential schema differences.
