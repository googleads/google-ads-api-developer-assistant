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

import os
import re


def detect_latest_api_version() -> str:
    """Detects the latest Google Ads API version from local sources or package metadata."""
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Search candidate directories for client_libs/google-ads-python/google/ads/googleads
    candidate_paths = [
        # Relative to .agents/skills/ext_version/scripts/
        os.path.abspath(
            os.path.join(
                script_dir,
                "../../../../client_libs/google-ads-python/google/ads/googleads",
            )
        ),
        # Relative to plugins/google-ads-api-developer-assistant/skills/ext-version/scripts/
        os.path.abspath(
            os.path.join(
                script_dir,
                "../../../client_libs/google-ads-python/google/ads/googleads",
            )
        ),
        # Relative to current working directory
        os.path.abspath("client_libs/google-ads-python/google/ads/googleads"),
    ]

    for candidate in candidate_paths:
        if os.path.isdir(candidate):
            try:
                version_dirs = [
                    d
                    for d in os.listdir(candidate)
                    if os.path.isdir(os.path.join(candidate, d))
                    and re.match(r"^v\d+$", d)
                ]
                if version_dirs:
                    version_dirs.sort(key=lambda x: int(x[1:]))
                    return version_dirs[-1]
            except OSError:
                continue

    # 2. Inspect installed python package if available
    try:
        import google.ads.googleads  # type: ignore

        installed_versions = [
            attr for attr in dir(google.ads.googleads) if re.match(r"^v\d+$", attr)
        ]
        if installed_versions:
            installed_versions.sort(key=lambda x: int(x[1:]))
            return installed_versions[-1]
    except Exception:
        pass

    # 3. Fallback to default version if no local library found
    return "v25"


def main() -> None:
    """Prints the detected latest API version."""
    print(detect_latest_api_version())


if __name__ == "__main__":
    main()
