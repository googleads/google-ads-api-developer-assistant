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
import logging
import os
import sys
import urllib.request

# Setup logging
# Script is in .agents/hooks/
# Log file should be in .agents/
base_dir = os.path.dirname(
    os.path.abspath(__file__)
)  # This is .agents/hooks directory
base_dir = os.path.dirname(base_dir)  # This is .agents directory
log_path = os.path.join(base_dir, "check_github_version.log")

# Create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler (keeps full history)
file_handler = logging.FileHandler(log_path)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(file_handler)

# Stream handler (only shows warnings and errors to user)
stream_handler = logging.StreamHandler(sys.stderr)
stream_handler.setLevel(logging.WARNING)  # Only show WARNING or higher
stream_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)
logger.addHandler(stream_handler)


def get_local_version() -> str | None:
    # agent.json is in the root directory
    # So we need to go up one more level from .agents to find agent.json
    root_dir = os.path.dirname(base_dir)
    json_path = os.path.join(root_dir, "agent.json")

    try:
        with open(json_path, "r") as f:
            data = json.load(f)
            return data.get("version")
    except Exception as e:
        logging.error(f"Error reading local version: {e}")
        return None


def get_remote_version() -> str | None:
    urls = [
        "https://raw.githubusercontent.com/googleads/google-ads-api-developer-assistant/main/agent.json",
        "https://raw.githubusercontent.com/googleads/google-ads-api-developer-assistant/main/manifest.json",
        "https://raw.githubusercontent.com/googleads/google-ads-api-developer-assistant/main/gemini-extension.json",
    ]
    for url in urls:
        try:
            logging.info(f"Attempting to fetch remote version from: {url}")
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    version = data.get("version")
                    if version:
                        return version
        except Exception as e:
            logging.info(f"Could not fetch from {url}: {e}")
    logging.error("Failed to fetch remote version from all known URLs.")
    return None


def parse_version(v_str: str) -> tuple[int, ...]:
    return tuple(map(int, v_str.split(".")))


def main() -> None:
    logging.info("Checking for updates...")
    local_version = get_local_version()
    remote_version = get_remote_version()

    if not local_version or not remote_version:
        logging.info("Could not complete version check.")
        return

    logging.info(
        f"Local version: {local_version}, Remote version: {remote_version}"
    )

    try:
        if parse_version(remote_version) > parse_version(local_version):
            logging.warning(f"A new version is available: {remote_version}")
            logging.warning("Please run `./update.sh` to update.")
        else:
            logging.info("Up to date.")
    except Exception as e:
        logging.error(f"Error comparing versions: {e}")


if __name__ == "__main__":
    main()
