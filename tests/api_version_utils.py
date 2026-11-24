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

"""Dynamic Google Ads API version helpers for tests.

Always resolves the active/latest Google Ads API version from the installed
`google-ads` SDK, local `client_libs/`, or `GOOGLE_ADS_API_VERSION` — never a
hardcoded static version literal.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys

_TESTS_DIR = Path(__file__).resolve().parent
_PLUGIN_ROOT = (
    _TESTS_DIR.parent / "plugins" / "google-ads-api-developer-assistant"
)
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from config import config_init as _config_init  # noqa: E402
from hitl_audit_logger import detect_importable_api_version  # noqa: E402

_VER_RE = re.compile(r"^[vV](\d+)$")


def get_current_api_version() -> str:
    """Dynamically resolves the current Google Ads API version (never static)."""
    env_ver = os.environ.get("GOOGLE_ADS_API_VERSION", "").strip()
    if env_ver:
        return _config_init.validate_api_version(env_ver)

    importable = detect_importable_api_version()
    if importable:
        return _config_init.validate_api_version(importable)

    detected = _config_init.detect_latest_api_version()
    if detected:
        return _config_init.validate_api_version(detected)

    return _config_init.resolve_active_api_version()


def offset_api_version(delta: int, base: str | None = None) -> str:
    """Returns a Google Ads API version string offset from `base` by `delta`."""
    ver = base or get_current_api_version()
    match = _VER_RE.fullmatch(ver.strip())
    if not match:
        raise ValueError(f"Unexpected Google Ads API version format: {ver!r}")
    return f"v{max(1, int(match.group(1)) + delta)}"


CURRENT_API_VERSION: str = get_current_api_version()
CURRENT_API_NUMBER: int = int(CURRENT_API_VERSION[1:])
PREVIOUS_API_VERSION: str = offset_api_version(-1, CURRENT_API_VERSION)
PREVIOUS_API_NUMBER: int = int(PREVIOUS_API_VERSION[1:])
OLDER_API_VERSION: str = offset_api_version(-2, CURRENT_API_VERSION)
NEXT_API_VERSION: str = offset_api_version(1, CURRENT_API_VERSION)
FUTURE_API_VERSION: str = offset_api_version(2, CURRENT_API_VERSION)
