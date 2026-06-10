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

"""Protobuf Object and Enum Inspection Skill Script."""

import argparse
import sys
from typing import Optional

from google.ads.googleads.client import GoogleAdsClient


def inspect_protobuf(object_name: str, api_version: str, client: Optional[GoogleAdsClient] = None) -> None:
    """Inspects any Google Ads API Protobuf resource, message or enum."""
    if client is None:
        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        # Attempt to load the type using the dynamic loader in client
        obj_type = client.get_type(object_name)
    except Exception as e:
        print(f"ERROR: Protobuf object '{object_name}' not found under version '{api_version}': {e}", file=sys.stderr)
        sys.exit(1)

    descriptor = getattr(obj_type, "DESCRIPTOR", getattr(getattr(obj_type, "_pb", None), "DESCRIPTOR", None))
    if descriptor is None:
        print(f"ERROR: Could not retrieve descriptor for '{object_name}'", file=sys.stderr)
        sys.exit(1)

    # Determine if it is an Enum or a Message
    # Note: descriptors for enums are EnumDescriptor
    if hasattr(descriptor, "values"):
        print(f"=== Enum: {object_name} ===")
        for value in descriptor.values:
            print(f"  - {value.name} = {value.number}")
    else:
        print(f"=== Message: {object_name} ===")
        for field in descriptor.fields:
            label_str = "REPEATED" if getattr(field, "is_repeated", False) else "OPTIONAL"
            type_name = field.message_type.name if field.message_type else field.type
            print(f"  - {field.name:<35} [{label_str:<8}] : {type_name}")


def main() -> None:
    """Parses command line arguments and runs inspection."""
    parser = argparse.ArgumentParser(description="Inspects a Google Ads API Protobuf type structure.")
    parser.add_argument("--object_name", required=True, help="Protobuf type name (e.g. Campaign, AdGroup).")
    parser.add_argument("--api_version", required=True, help="API version (e.g. v24).")
    args = parser.parse_args()

    inspect_protobuf(args.object_name, args.api_version)


if __name__ == "__main__":
    main()
