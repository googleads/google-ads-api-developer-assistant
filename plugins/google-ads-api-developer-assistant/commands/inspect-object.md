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
   - Resolve API version from `config/api_version.txt` or default to the latest discovered version.

2. **Execute Inspection**:
   - Run the inspection script:
     ```bash
     python3 skills/inspect-object/scripts/inspect_object.py --name "$ARGUMENTS" --api_version "<api_version>"
     ```
   - If the script is unavailable in the environment, inspect the proto files directly in `client_libs/google-ads-python/google/ads/googleads/<api_version>/`.

3. **Output Format**:
   - **Object Type**: Identify whether the symbol is a Resource, Message, or Enum.
   - **Selectable / Filterable Fields**: List core fields with data types and descriptions.
   - **Enum Values**: For Enum types, list all possible values and their meanings.
   - **Nested Protobuf Messages**: Show the structure of sub-messages.
