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

import argparse
import os
import re
from typing import List, Optional


def update_assistant_config_api_version(
    latest_version: str,
    config_dir: Optional[str] = None,
) -> List[str]:
    """Updates api_version in config/assistant_config (TOML), preserving customer_id and execute_mutates."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ver_clean = latest_version.strip().strip("'\"")
    if ver_clean and not ver_clean.startswith("v") and ver_clean.isdigit():
        ver_clean = f"v{ver_clean}"

    if config_dir:
        candidate_configs = [
            os.path.join(os.path.abspath(config_dir), "assistant_config")
        ]
    else:
        candidate_configs = [
            os.path.abspath("config/assistant_config"),
            os.path.abspath(
                os.path.join(script_dir, "../../../config/assistant_config")
            ),
            os.path.abspath(
                os.path.join(script_dir, "../../../../../config/assistant_config")
            ),
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config"
            ),
        ]

    updated_paths: List[str] = []
    seen: set[str] = set()
    for cfg_path in candidate_configs:
        norm_path = os.path.normpath(cfg_path)
        if norm_path in seen:
            continue
        seen.add(norm_path)

        cfg_parent = os.path.dirname(norm_path)
        if not config_dir and not os.path.isdir(cfg_parent):
            continue
        os.makedirs(cfg_parent, exist_ok=True)

        cid = "12345678"
        exec_mutates_str = "false"
        if os.path.isfile(norm_path):
            try:
                with open(norm_path, "r", encoding="utf-8") as f:
                    existing_text = f.read()
                m_cid = re.search(
                    r'(?m)^\s*customer_id\s*=\s*["\']?([^"\'\s#]+)["\']?',
                    existing_text,
                )
                if m_cid:
                    cid = m_cid.group(1).strip()
                m_em = re.search(
                    r'(?m)^\s*execute_mutates\s*=\s*["\']?(true|false)["\']?',
                    existing_text,
                    re.IGNORECASE,
                )
                if m_em:
                    exec_mutates_str = m_em.group(1).lower()
            except OSError:
                pass

        if cid == "12345678":
            for legacy_name in ("customer_id", "customer_id.txt"):
                legacy_file = os.path.join(cfg_parent, legacy_name)
                if os.path.isfile(legacy_file):
                    try:
                        with open(legacy_file, "r", encoding="utf-8") as lf:
                            legacy_cid = lf.read().strip().strip("'\"")
                        if legacy_cid and legacy_cid != "12345678":
                            cid = legacy_cid
                            break
                    except OSError:
                        pass

        try:
            with open(norm_path, "w", encoding="utf-8") as f:
                f.write(
                    f'api_version = "{ver_clean}"\n'
                    f'customer_id = "{cid}"\n'
                    f"execute_mutates = {exec_mutates_str}\n"
                )
            updated_paths.append(norm_path)
        except OSError:
            continue

    return updated_paths


def _extract_version_dirs(base_dir: str) -> List[str]:
    """Returns sorted v<N> directory names inside base_dir."""
    if not base_dir or not os.path.isdir(base_dir):
        return []
    try:
        v_dirs = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
            and re.match(r"^v\d+$", d)
        ]
        v_dirs.sort(key=lambda x: int(x[1:]))
        return v_dirs
    except OSError:
        return []


def detect_latest_api_version(
    update_config: bool = False,
    config_dir: Optional[str] = None,
) -> str:
    """Detects the latest Google Ads API version from local sources or package metadata.

    If update_config is True or config_dir is provided, automatically writes the
    detected api_version into config/assistant_config.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    detected: Optional[str] = None
    discovered_versions: List[str] = []

    # 1. Search candidate directories for client_libs/google-ads-python/google/ads/googleads
    candidate_paths = [
        # Relative to current working directory
        os.path.abspath("client_libs/google-ads-python/google/ads/googleads"),
        os.path.abspath(
            "plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
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
        # Global plugin installation directory
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
    ]

    for candidate in candidate_paths:
        version_dirs = _extract_version_dirs(candidate)
        if version_dirs:
            discovered_versions.append(version_dirs[-1])
            break

    # 2. Inspect installed python package if available (checking both attributes and package __path__)
    try:
        import importlib

        gads_mod = importlib.import_module("google.ads.googleads")

        installed_versions: List[str] = [
            attr
            for attr in dir(gads_mod)
            if re.match(r"^v\d+$", attr)
        ]
        pkg_paths: List[str] = []
        raw_path = getattr(gads_mod, "__path__", None)
        if raw_path:
            pkg_paths.extend(list(raw_path))
        pkg_file = getattr(gads_mod, "__file__", None)
        if pkg_file:
            pkg_paths.append(os.path.dirname(pkg_file))
        for pkg_dir in pkg_paths:
            installed_versions.extend(_extract_version_dirs(pkg_dir))
        if installed_versions:
            installed_versions.sort(key=lambda x: int(x[1:]))
            discovered_versions.append(installed_versions[-1])
    except Exception:
        pass

    if discovered_versions:
        discovered_versions.sort(key=lambda x: int(x[1:]))
        detected = discovered_versions[-1]

    # 3. Fallback to default version if no local library found
    final_version = detected or "v25"

    if update_config or config_dir is not None:
        update_assistant_config_api_version(final_version, config_dir=config_dir)

    return final_version


def main() -> None:
    """Detects the latest API version, updates config/assistant_config by default, and prints the version."""
    parser = argparse.ArgumentParser(
        description="Detect the latest Google Ads API version and update config/assistant_config."
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Print the detected API version without updating config/assistant_config.",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Optional target config directory containing assistant_config.",
    )
    args = parser.parse_args()
    version = detect_latest_api_version(
        update_config=not args.no_update,
        config_dir=args.config_dir,
    )
    print(version)


if __name__ == "__main__":
    main()
