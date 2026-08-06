#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A tool to inspect structural field definitions and types for Google Ads API objects."""

import argparse
import sys
from typing import Dict
from google.ads.googleads.client import GoogleAdsClient

# Mapping of protobuf FieldDescriptor type ints to human-readable names
TYPE_MAPPING: Dict[int, str] = {
    1: "DOUBLE",
    2: "FLOAT",
    3: "INT64",
    4: "UINT64",
    5: "INT32",
    6: "FIXED64",
    7: "FIXED32",
    8: "BOOL",
    9: "STRING",
    10: "GROUP",
    11: "MESSAGE",
    12: "BYTES",
    13: "UINT32",
    14: "ENUM",
    15: "SFIXED32",
    16: "SFIXED64",
    17: "SINT32",
    18: "SINT64",
}


def inspect_structure(object_name: str, api_version: str) -> None:
    """Retrieves and prints structural details for the specified Google Ads API object or Enum.

    Args:
        object_name: The name of the API object/Enum (e.g. 'Campaign' or 'CampaignStatusEnum').
        api_version: The Google Ads API version (e.g. 'v24').
    """
    try:
        client: GoogleAdsClient = GoogleAdsClient.load_from_storage(version=api_version)
    except Exception as e:
        print(f"CRITICAL ERROR: Failed to load Google Ads client: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        obj_type = client.get_type(object_name)
    except Exception as e:
        print(f"ERROR: Object type '{object_name}' not found under version '{api_version}': {e}", file=sys.stderr)
        sys.exit(1)

    descriptor = getattr(obj_type, "DESCRIPTOR", getattr(getattr(obj_type, "_pb", None), "DESCRIPTOR", None))
    if descriptor is None:
        print(f"ERROR: Could not retrieve descriptor for '{object_name}'", file=sys.stderr)
        sys.exit(1)

    # Check if this descriptor represents an Enum or a Message
    if hasattr(descriptor, "values"):
        print(f"\n=== Enum: {object_name} (API Version: {api_version}) ===")
        for value in descriptor.values:
            print(f"  - {value.name:<40} = {value.number}")
    else:
        print(f"\n=== Message: {object_name} (API Version: {api_version}) ===")
        print(f"  {'Field Name':<35} | {'Label':<10} | {'Type Name':<20} | {'Underlying Type'}")
        print(f"  {'-'*35}-+-{'-'*10}-+-{'-'*20}-+-{'-'*15}")
        for field in descriptor.fields:
            label_str: str = "REPEATED" if getattr(field, "is_repeated", False) else "OPTIONAL"
            raw_type: int = int(field.type)
            type_label: str = TYPE_MAPPING.get(raw_type, f"UNKNOWN({raw_type})")
            
            # Message or Enum specific names
            field_type_name: str = ""
            if field.message_type:
                field_type_name = field.message_type.name
            elif field.enum_type:
                field_type_name = field.enum_type.name
            else:
                field_type_name = type_label

            print(f"  - {field.name:<33} | {label_str:<8} | {field_type_name:<18} | {type_label}")


def main() -> None:
    """Command line entrypoint."""
    parser = argparse.ArgumentParser(description="Inspects the exact structural field definitions and types of an object.")
    parser.add_argument("--object_name", required=True, help="Object name to inspect.")
    parser.add_argument("--api_version", required=True, help="API version (e.g. v24).")
    args = parser.parse_args()

    inspect_structure(args.object_name, args.api_version)


if __name__ == "__main__":
    main()
