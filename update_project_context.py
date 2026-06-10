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

"""Helper script to update project configuration JSON files with context paths."""

import glob
import json
import os
import sys


def add_context_path(project_dir: str, context_path: str) -> None:
    """Verifies and adds context path to the project config file."""
    # 1. Verify path is accessible
    abs_context_path = os.path.abspath(os.path.expanduser(context_path))
    if not os.path.exists(abs_context_path):
        print(
            f"Error: Path '{abs_context_path}' does not exist or is not accessible.",
            file=sys.stderr,
        )
        sys.exit(1)
    if not os.path.isdir(abs_context_path):
        print(
            f"Error: Path '{abs_context_path}' is not a directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    abs_project_dir = os.path.abspath(os.path.expanduser(project_dir))

    # 2. Locate project configuration file
    projects_dir = os.path.expanduser("~/.gemini/config/projects")
    project_files = glob.glob(os.path.join(projects_dir, "*.json"))

    matching_file = None
    for file_path in project_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("name") == abs_project_dir:
                    matching_file = file_path
                    break
        except Exception:  # pylint: disable=broad-except
            continue

    if not matching_file:
        print(
            f"Error: Could not find project configuration for '{abs_project_dir}' in '{projects_dir}'.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Found project configuration file: {matching_file}")

    # Read, update and save configuration
    with open(matching_file, "r", encoding="utf-8") as f:
        config = json.load(f)

    resources = (
        config.setdefault("projectResources", {})
        .setdefault("resources", [])
    )

    # Check if context_path is already in resources
    target_uri = f"file://{abs_context_path}"
    found = False
    for res in resources:
        git_folder = res.get("gitFolder", {})
        if git_folder.get("folderUri") == target_uri:
            found = True
            break
        # Also check simple folderUri resource
        if res.get("folderUri") == target_uri:
            found = True
            break

    if found:
        print(
            f"Path '{abs_context_path}' is already registered in the project configuration."
        )
        return

    # Append new gitFolder resource
    resources.append(
        {"gitFolder": {"folderUri": target_uri, "allowWrite": True}}
    )

    with open(matching_file, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    print(f"Successfully added '{abs_context_path}' to project configuration.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: update_project_context.py <project_dir> <context_path>",
            file=sys.stderr,
        )
        sys.exit(1)
    add_context_path(sys.argv[1], sys.argv[2])
