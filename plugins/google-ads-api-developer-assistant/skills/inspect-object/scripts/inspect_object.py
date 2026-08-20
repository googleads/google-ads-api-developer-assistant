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
import difflib
import glob
import importlib.metadata
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

try:
    from google.ads.googleads.client import GoogleAdsClient
except ImportError:
    GoogleAdsClient = None  # type: ignore


def check_version_parity() -> None:
    """Checks if installed google-ads version matches client_libs version used for protobuf definitions."""
    installed_version = None
    try:
        installed_version = importlib.metadata.version("google-ads")
    except Exception:
        pass

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(script_dir, "../../../client_libs/google-ads-python")),
        os.path.abspath(os.path.join(script_dir, "../../../../client_libs/google-ads-python")),
        os.path.expanduser("~/.gemini/config/plugins/google_ads_assistant_plugin/client_libs/google-ads-python"),
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"),
        os.path.abspath("client_libs/google-ads-python"),
    ]

    client_libs_version = None
    for cand in candidates:
        pyproject = os.path.join(cand, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                with open(pyproject, "r", encoding="utf-8") as f:
                    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', f.read())
                    if m:
                        client_libs_version = m.group(1).strip()
                        break
            except Exception:
                pass
        changelog = os.path.join(cand, "ChangeLog")
        if os.path.isfile(changelog):
            try:
                with open(changelog, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.search(r"^\*\s*([\d\.\w\-]+)", line)
                        if m:
                            client_libs_version = m.group(1).strip()
                            break
                    if client_libs_version:
                        break
            except Exception:
                pass

    if installed_version and client_libs_version:
        v_inst = installed_version.lstrip("v").strip()
        v_cl = client_libs_version.lstrip("v").strip()
        if v_inst != v_cl:
            print(
                f"WARNING: Installed google-ads package version ({installed_version}) does not match "
                f"client_libs/google-ads-python version ({client_libs_version}) used for protobuf inspection. "
                f"Schema inspection or API calls may encounter field discrepancies.",
                file=sys.stderr,
            )


def get_available_types(api_version: str) -> Dict[str, str]:
    """Finds all available message and enum type names and their file paths."""
    version_clean = api_version.lower()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath(os.path.join(script_dir, "../../../client_libs/google-ads-python")),
        os.path.abspath(os.path.join(script_dir, "../../../../client_libs/google-ads-python")),
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"),
    ]
    base_dir = None
    for cand in candidates:
        if os.path.isdir(os.path.join(cand, "google", "ads", "googleads", version_clean)):
            base_dir = cand
            break

    type_map: Dict[str, str] = {}
    if not base_dir:
        return type_map

    v_dir = os.path.join(base_dir, "google", "ads", "googleads", version_clean)
    for py_file in glob.glob(os.path.join(v_dir, "**/types/*.py"), recursive=True):
        if py_file.endswith("__init__.py"):
            continue
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                classes = re.findall(r"class\s+([A-Za-z0-9_]+)\b", content)
                for cls in classes:
                    if cls not in type_map:
                        type_map[cls] = py_file
        except Exception:
            continue
    return type_map


def resolve_type_name(
    object_name: str, available_types: Dict[str, str]
) -> Tuple[Optional[str], List[str]]:
    """Resolves an object name using exact, case-insensitive, normalized, or fuzzy matching."""
    if not available_types:
        return object_name, []

    # Handle dot notation (e.g. CampaignStatusEnum.CampaignStatus)
    target = object_name.split(".")[-1] if "." in object_name else object_name

    # 1. Exact match
    if target in available_types:
        return target, []

    # 2. Case-insensitive match (e.g. campaign -> Campaign)
    lower_map = {k.lower(): k for k in available_types}
    if target.lower() in lower_map:
        return lower_map[target.lower()], []

    # 3. Normalized match: strip underscores, hyphens, and spaces
    norm_input = re.sub(r"[^a-zA-Z0-9]", "", target.lower())
    norm_map = {re.sub(r"[^a-zA-Z0-9]", "", k.lower()): k for k in available_types}
    if norm_input in norm_map:
        return norm_map[norm_input], []

    # 4. Try matching with or without Enum suffix
    if norm_input.endswith("enum"):
        stripped_enum = norm_input[:-4]
        if stripped_enum in norm_map:
            return norm_map[stripped_enum], []
    else:
        if norm_input + "enum" in norm_map:
            return norm_map[norm_input + "enum"], []

    # 5. Fuzzy matching suggestions
    close_matches = difflib.get_close_matches(
        target, available_types.keys(), n=5, cutoff=0.5
    )
    if not close_matches:
        norm_close = difflib.get_close_matches(
            norm_input, norm_map.keys(), n=5, cutoff=0.4
        )
        close_matches = [norm_map[k] for k in norm_close if k in norm_map]

    return None, close_matches


def inspect_from_source(py_file: str, class_name: str) -> bool:
    """Fallback inspector that parses protobuf fields/enums from the Python source definition."""
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"ERROR: Failed to read source file '{py_file}': {e}", file=sys.stderr)
        return False

    in_target_class = False
    class_indent = -1
    fields: List[Tuple[str, str, str]] = []
    enum_values: List[Tuple[str, str]] = []

    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if stripped.startswith("class "):
            class_def = stripped[6:].strip()
            c_name = class_def.split("(")[0].split(":")[0].strip()
            if c_name == class_name:
                in_target_class = True
                class_indent = indent
                continue
            elif in_target_class and indent <= class_indent:
                break

        if in_target_class:
            m = re.match(
                r"^\s*([a-zA-Z0-9_]+)\s*:\s*([^=\n]+)\s*=\s*proto\.(Field|RepeatedField|MapField)\(",
                line,
            )
            if m:
                f_name = m.group(1)
                f_type = m.group(2).strip()
                f_kind = m.group(3)
                label = "REPEATED" if f_kind == "RepeatedField" else "OPTIONAL"
                fields.append((f_name, label, f_type))
            else:
                m_annot = re.match(r"^\s*([a-zA-Z0-9_]+)\s*:\s*([^=\n#]+)", line)
                if (
                    m_annot
                    and not stripped.startswith("def ")
                    and not stripped.startswith("class ")
                    and not stripped.startswith("return ")
                ):
                    f_name = m_annot.group(1)
                    f_type = m_annot.group(2).strip()
                    fields.append((f_name, "OPTIONAL", f_type))
                elif "=" in stripped and not stripped.startswith("#") and not stripped.startswith("def ") and not stripped.startswith("class "):
                    m_enum = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(\d+)", line)
                    if m_enum:
                        enum_values.append((m_enum.group(1), m_enum.group(2)))

    if enum_values and not fields:
        print(f"=== Enum: {class_name} ===")
        for name, num in enum_values:
            print(f"  - {name} = {num}")
        return True
    elif fields:
        print(f"=== Message: {class_name} ===")
        for f_name, label_str, type_name in fields:
            print(f"  - {f_name:<35} [{label_str:<8}] : {type_name}")
        return True
    return False


def inspect_protobuf(
    object_name: str, api_version: str, client: Optional[GoogleAdsClient] = None
) -> None:
    """Inspects any Google Ads API Protobuf resource, message or enum."""
    check_version_parity()
    available_types = get_available_types(api_version)
    resolved_name, suggestions = resolve_type_name(object_name, available_types)

    if not resolved_name:
        print(
            f"ERROR: Protobuf object '{object_name}' not found under version '{api_version}'.",
            file=sys.stderr,
        )
        if suggestions:
            print("\nDid you mean one of these?", file=sys.stderr)
            for s in suggestions:
                print(f"  - {s}", file=sys.stderr)
        sys.exit(1)

    if resolved_name != object_name:
        print(f"Note: Resolved '{object_name}' -> '{resolved_name}'")

    target_name = resolved_name

    # First attempt: Using GoogleAdsClient if available and loaded
    if client is None and GoogleAdsClient is not None:
        try:
            client = GoogleAdsClient.load_from_storage(version=api_version)
        except Exception:
            client = None

    if client is not None:
        try:
            obj_type = client.get_type(target_name)
            descriptor = getattr(
                obj_type,
                "DESCRIPTOR",
                getattr(getattr(obj_type, "_pb", None), "DESCRIPTOR", None),
            )
            if descriptor is not None:
                if hasattr(descriptor, "values"):
                    print(f"=== Enum: {target_name} ===")
                    for value in descriptor.values:
                        print(f"  - {value.name} = {value.number}")
                    return
                else:
                    print(f"=== Message: {target_name} ===")
                    for field in descriptor.fields:
                        label_str = (
                            "REPEATED"
                            if getattr(field, "is_repeated", False)
                            else "OPTIONAL"
                        )
                        type_name = (
                            field.message_type.name
                            if field.message_type
                            else field.type
                        )
                        print(f"  - {field.name:<35} [{label_str:<8}] : {type_name}")
                    return
        except Exception:
            pass

    # Fallback attempt: Parse directly from source file in client_libs
    py_file = available_types.get(target_name)
    if py_file and inspect_from_source(py_file, target_name):
        return

    print(
        f"ERROR: Could not inspect descriptor or definition for '{target_name}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    """Parses command line arguments and runs inspection."""
    parser = argparse.ArgumentParser(
        description="Inspects a Google Ads API Protobuf type structure."
    )
    parser.add_argument(
        "--object_name",
        "-n",
        required=True,
        help="Protobuf type name (e.g. Campaign, campaign, AdGroup).",
    )
    parser.add_argument(
        "--api_version",
        "-v",
        required=True,
        help="API version (e.g. v25).",
    )
    args = parser.parse_args()

    inspect_protobuf(args.object_name, args.api_version)


if __name__ == "__main__":
    main()
