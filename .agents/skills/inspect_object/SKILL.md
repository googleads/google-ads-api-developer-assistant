---
name: inspect-object
description: Inspects any Google Ads API Protobuf resource, nested message or Enum structure.
---

# Inspect Protobuf Object or Enum

This skill enables you to dynamically inspect any Google Ads API resource structure, message type, or Enum values. It must be used whenever you need to verify the structural fields and enums of API objects rather than guessing.

## Usage

Execute the inspection utility script in the virtual environment:

```bash
./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name <object_name> --api_version <api_version>
```

### Examples

1. To inspect the `Campaign` resource structure:
```bash
./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name Campaign --api_version v24
```

2. To inspect the `CampaignStatusEnum` enums:
```bash
./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name CampaignStatusEnum --api_version v24
```
