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

import json
import os
import sys


def get_extension_version() -> None:
    """Reads agent.json or plugin.json and prints the version."""
    try:
        # Search for plugin.json or agent.json in parent directories
        current_dir = os.path.dirname(os.path.abspath(__file__))
        target_files = ["plugin.json", "agent.json"]
        
        found = False
        while current_dir and current_dir != os.path.dirname(current_dir):
            for file_name in target_files:
                candidate = os.path.join(current_dir, file_name)
                if os.path.exists(candidate):
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        print(data.get("version", "Version not found"))
                        found = True
                        break
            if found:
                break
            current_dir = os.path.dirname(current_dir)

        if not found:
            print("Unknown")

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    get_extension_version()
