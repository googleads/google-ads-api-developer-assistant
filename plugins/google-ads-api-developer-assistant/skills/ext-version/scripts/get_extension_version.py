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


def get_extension_version() -> bool:
    """Reads plugin.json or agent.json, prints the version (or 'Unknown'), and returns True if found."""
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        target_files = [
            "plugin.json",
            "plugin.json.disabled",
            "agent.json",
            os.path.join("plugins", "google-ads-api-developer-assistant", "plugin.json"),
            os.path.join(
                "plugins", "google-ads-api-developer-assistant", "plugin.json.disabled"
            ),
        ]

        candidate_roots: list[str] = []
        walk_dir = current_dir
        while walk_dir and walk_dir != os.path.dirname(walk_dir):
            candidate_roots.append(walk_dir)
            walk_dir = os.path.dirname(walk_dir)

        for env_key in ("GOOGLE_ADS_ASSISTANT_DIR", "CLAUDE_PLUGIN_ROOT"):
            env_dir = os.environ.get(env_key, "").strip()
            if env_dir:
                candidate_roots.append(env_dir)

        candidate_roots.extend(
            [
                os.path.expanduser(
                    "~/.gemini/config/plugins/google-ads-api-developer-assistant"
                ),
                os.path.expanduser(
                    "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
                ),
            ]
        )

        for root in candidate_roots:
            for file_name in target_files:
                candidate = os.path.join(root, file_name)
                if os.path.exists(candidate):
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        ver = str(data.get("version") or "").strip()
                        if ver:
                            print(ver)
                            return True
                    except Exception:
                        continue

        print("Unknown")
        return False

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if not get_extension_version():
        sys.exit(1)
