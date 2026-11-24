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

"""Detects the latest Google Ads API version and updates assistant_config."""

import argparse
import importlib
import importlib.util
import json
import os
import re
import sys
import tomllib
from typing import Any, Optional


def _format_toml_value(val: Any) -> str:
    """Formats a scalar TOML value."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    return json.dumps(str(val))


def _render_updated_assistant_config(
    existing_text: str,
    ver_clean: str,
    cid_override: Optional[str] = None,
) -> str:
    """Formats assistant_config TOML preserving extra user keys."""
    parsed_extra: dict[str, Any] = {}
    cid = "12345678"
    exec_mutates = False
    enabled_val: Optional[bool] = None
    if existing_text.strip():
        try:
            loaded = tomllib.loads(existing_text)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if k == "customer_id" and str(v).strip():
                        cid = str(v).strip()
                    elif k == "execute_mutates" and isinstance(v, bool):
                        exec_mutates = v
                    elif k == "enabled" and isinstance(v, bool):
                        enabled_val = v
                    elif k not in (
                        "api_version",
                        "customer_id",
                        "execute_mutates",
                        "enabled",
                    ):
                        parsed_extra[k] = v
        except tomllib.TOMLDecodeError:
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
                exec_mutates = m_em.group(1).lower() == "true"
            m_en = re.search(
                r'(?m)^\s*enabled\s*=\s*["\']?(true|false)["\']?',
                existing_text,
                re.IGNORECASE,
            )
            if m_en:
                enabled_val = m_en.group(1).lower() == "true"

    if cid_override:
        cid = cid_override
    lines = [
        f'api_version = "{ver_clean}"',
        f'customer_id = "{cid}"',
        f"execute_mutates = {'true' if exec_mutates else 'false'}",
    ]
    if enabled_val is not None:
        lines.append(f"enabled = {'true' if enabled_val else 'false'}")
    for k, v in parsed_extra.items():
        if re.fullmatch(r"[A-Za-z0-9_-]+", str(k)):
            lines.append(f"{k} = {_format_toml_value(v)}")
    return "\n".join(lines) + "\n"


def _is_git_tracked_plugin_config_dir(cfg_dir: str) -> bool:
    """Returns True if cfg_dir is the git-tracked plugin config directory."""
    abs_cfg = os.path.abspath(cfg_dir)
    plugin_dir = os.path.dirname(abs_cfg)
    plugins_parent = os.path.dirname(plugin_dir)
    repo_root = os.path.dirname(plugins_parent)
    return (
        os.path.basename(abs_cfg) == "config"
        and os.path.basename(plugin_dir) == "google-ads-api-developer-assistant"
        and os.path.basename(plugins_parent) == "plugins"
        and os.path.isdir(os.path.join(repo_root, ".git"))
    )


def update_assistant_config_api_version(
    latest_version: str,
    config_dir: Optional[str] = None,
) -> list[str]:
    """Updates api_version in config/assistant_config (TOML).

    Preserves existing customer_id, execute_mutates, and enabled settings.

    Args:
        latest_version: Detected API version string (format 'v<N>').
        config_dir: Optional explicit config directory path.

    Returns:
        List of assistant_config file paths that were updated.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ver_clean = latest_version.strip().strip("'\"")
    if ver_clean and not ver_clean.startswith("v") and ver_clean.isdigit():
        ver_clean = f"v{ver_clean}"

    global_cfg_dirs = (
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/"
            "google-ads-api-developer-assistant/config"
        ),
    )
    has_global_cfg = any(os.path.isdir(d) for d in global_cfg_dirs)

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
                os.path.join(
                    script_dir, "../../../../../config/assistant_config"
                )
            ),
            os.path.expanduser(
                "~/.gemini/config/plugins/"
                "google-ads-api-developer-assistant/config/assistant_config"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/"
                "google-ads-api-developer-assistant/config/assistant_config"
            ),
        ]

    updated_paths: list[str] = []
    seen: set[str] = set()
    for cfg_path in candidate_configs:
        norm_path = os.path.normpath(cfg_path)
        if norm_path in seen:
            continue
        seen.add(norm_path)

        cfg_parent = os.path.dirname(norm_path)
        if not config_dir and not os.path.isdir(cfg_parent):
            continue
        if (
            config_dir is None
            and has_global_cfg
            and _is_git_tracked_plugin_config_dir(cfg_parent)
        ):
            continue
        os.makedirs(cfg_parent, exist_ok=True)

        existing_text = ""
        if os.path.isfile(norm_path):
            try:
                with open(norm_path, "r", encoding="utf-8") as f:
                    existing_text = f.read()
            except OSError:
                existing_text = ""

        legacy_cid_override: Optional[str] = None
        if 'customer_id = "12345678"' in _render_updated_assistant_config(
            existing_text, ver_clean
        ):
            for legacy_name in ("customer_id", "customer_id.txt"):
                legacy_file = os.path.join(cfg_parent, legacy_name)
                if os.path.isfile(legacy_file):
                    try:
                        with open(legacy_file, "r", encoding="utf-8") as lf:
                            legacy_cid = lf.read().strip().strip("'\"")
                        if legacy_cid and legacy_cid != "12345678":
                            legacy_cid_override = legacy_cid
                            break
                    except OSError:
                        pass

        try:
            content_out = _render_updated_assistant_config(
                existing_text, ver_clean, cid_override=legacy_cid_override
            )
            if content_out != existing_text or not os.path.isfile(norm_path):
                fd = os.open(
                    norm_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content_out)
            if sys.platform != "win32" and os.path.isfile(norm_path):
                try:
                    os.chmod(norm_path, 0o600)
                except OSError:
                    pass
            updated_paths.append(norm_path)
        except OSError:
            continue

    return updated_paths


def _extract_version_dirs(base_dir: str) -> list[str]:
    """Returns sorted v<N> directory names inside base_dir."""
    if not base_dir or not os.path.isdir(base_dir):
        return []
    try:
        v_dirs = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d))
            and re.fullmatch(r"v\d+", d)
        ]
        v_dirs.sort(key=lambda x: int(x[1:]))
        return v_dirs
    except OSError:
        return []


def detect_latest_api_version(
    update_config: bool = False,
    config_dir: Optional[str] = None,
) -> str:
    """Detects the latest Google Ads API version from local or installed files.

    If update_config is True or config_dir is provided, automatically writes the
    detected api_version into config/assistant_config.

    Args:
        update_config: Whether to update config/assistant_config with the
          detected API version.
        config_dir: Optional explicit config directory containing
          assistant_config.

    Returns:
        The highest detected API version string (format 'v<N>').

    Raises:
        RuntimeError: If no Google Ads API version can be detected from local
            client_libs or the installed google-ads package.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    detected: Optional[str] = None
    discovered_versions: list[str] = []
    gads_subpath = "client_libs/google-ads-python/google/ads/googleads"

    # 1. Search candidate directories for local google-ads-python sources.
    candidate_paths = (
        # Relative to current working directory
        os.path.abspath(gads_subpath),
        os.path.abspath(
            f"plugins/google-ads-api-developer-assistant/{gads_subpath}"
        ),
        # Relative to .agents/skills/ext_version/scripts/
        os.path.abspath(
            os.path.join(script_dir, f"../../../../{gads_subpath}")
        ),
        # Relative to plugins/.../skills/ext-version/scripts/
        os.path.abspath(os.path.join(script_dir, f"../../../{gads_subpath}")),
        # Global plugin installation directories
        os.path.expanduser(
            "~/.gemini/config/plugins/"
            f"google-ads-api-developer-assistant/{gads_subpath}"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/"
            f"google-ads-api-developer-assistant/{gads_subpath}"
        ),
    )

    for candidate in candidate_paths:
        version_dirs = _extract_version_dirs(candidate)
        if version_dirs:
            discovered_versions.append(version_dirs[-1])
            break

    # 2. Inspect installed python package without heavy gRPC/Protobuf import.
    try:
        installed_versions: list[str] = []
        pkg_paths: list[str] = []
        if "google.ads.googleads" in sys.modules:
            gads_mod = sys.modules["google.ads.googleads"]
            if gads_mod is not None:
                installed_versions.extend(
                    attr
                    for attr in dir(gads_mod)
                    if re.fullmatch(r"v\d+", attr)
                )
                raw_path = getattr(gads_mod, "__path__", None)
                if raw_path:
                    pkg_paths.extend(list(raw_path))
                pkg_file = getattr(gads_mod, "__file__", None)
                if pkg_file:
                    pkg_paths.append(os.path.dirname(pkg_file))
        else:
            spec = importlib.util.find_spec("google.ads.googleads")
            if spec is not None:
                if spec.submodule_search_locations:
                    pkg_paths.extend(list(spec.submodule_search_locations))
                elif spec.origin:
                    pkg_paths.append(os.path.dirname(spec.origin))
        for pkg_dir in pkg_paths:
            installed_versions.extend(_extract_version_dirs(pkg_dir))
        if installed_versions:
            installed_versions.sort(key=lambda x: int(x[1:]))
            discovered_versions.append(installed_versions[-1])
    except (AttributeError, ImportError, OSError, TypeError, ValueError):
        pass

    if discovered_versions:
        discovered_versions.sort(key=lambda x: int(x[1:]))
        detected = discovered_versions[-1]

    if not detected:
        raise RuntimeError(
            "Unable to detect the latest Google Ads API version from local "
            "client_libs or installed google-ads package."
        )

    if update_config or config_dir is not None:
        update_assistant_config_api_version(detected, config_dir=config_dir)

    return detected


def get_active_api_version() -> str:
    """Returns the API version the skill scripts use, without writing config.

    Delegates to config_init.resolve_active_api_version: GOOGLE_ADS_API_VERSION,
    then api_version in the active assistant_config, then the highest version
    in local client_libs and the installed google-ads package.

    Raises:
        ValueError: If the version is invalid or cannot be determined.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    try:
        if plugin_root not in sys.path and os.path.isdir(plugin_root):
            sys.path.insert(0, plugin_root)
        resolver = importlib.import_module(
            "config.config_init"
        ).resolve_active_api_version
    except (AttributeError, ImportError, OSError, SyntaxError) as e:
        raise ValueError(
            "Could not determine Google Ads API version (config_init is "
            f"unavailable: {e}); pass --api_version vN"
        ) from e
    return str(resolver())


def main() -> None:
    """Prints the active or highest installed API version."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Detect the highest installed Google Ads API version and update "
            "config/assistant_config (default), print the active version "
            "(--active / --no-update), or print the highest installed version "
            "(--installed)."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--active",
        "--no-update",
        dest="active",
        action="store_true",
        help=(
            "Print the active API version that the skill scripts use "
            "(GOOGLE_ADS_API_VERSION, then assistant_config, then the highest "
            "installed version). Never writes config/assistant_config."
        ),
    )
    mode.add_argument(
        "--installed",
        action="store_true",
        help=(
            "Print the highest installed API version (local client_libs and "
            "the google-ads package) without updating config/assistant_config."
        ),
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Optional target config directory containing assistant_config.",
    )
    args = parser.parse_args()
    try:
        if args.active:
            version = get_active_api_version()
        else:
            version = detect_latest_api_version(
                update_config=not args.installed,
                config_dir=None if args.installed else args.config_dir,
            )
    except (RuntimeError, ValueError) as e:
        sys.stderr.write(f"ERROR: {e}\n")
        sys.exit(1)
    print(version)


if __name__ == "__main__":
    main()
