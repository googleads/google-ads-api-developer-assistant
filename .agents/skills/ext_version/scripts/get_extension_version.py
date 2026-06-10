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
    """Reads agent.json and prints the version."""
    try:
        # Assumes the script is in .agents/skills/ext_version/scripts/
        # agent.json is at the root, so 5 levels up
        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            )
        )
        json_path = os.path.join(base_dir, "agent.json")

        if not os.path.exists(json_path):
            # Fallback: try current directory or one level up if running from root
            if os.path.exists("agent.json"):
                json_path = "agent.json"

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(data.get("version", "Version not found"))

    except FileNotFoundError:
        print("Error: agent.json not found at expected path.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Error: agent.json is not valid JSON.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    get_extension_version()
