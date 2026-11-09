"""Runtime path resolution shim for Google Ads API Developer Assistant.

When loaded via PYTHONPATH from the installed plugin's config/ directory, this
shim ensures that calls such as GoogleAdsClient.load_from_storage(path="config/google-ads.yaml")
succeed in any working directory without requiring a local ./config/ folder or
the GitHub source checkout.
"""

import builtins
import os
from typing import Any

_ORIG_OPEN = builtins.open
_THIS_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_assistant_config_file(file: Any, mode: str = "r") -> Any:
    if not isinstance(file, (str, bytes, os.PathLike)):
        return file
    try:
        path_str = os.fspath(file)
    except TypeError:
        return file
    if isinstance(path_str, bytes):
        return file

    # Preserve strict local isolation during unit test runs unless explicitly testing the shim
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "_GOOGLE_ADS_TEST_SITECUSTOMIZE"
    ):
        return file

    if os.path.isabs(path_str) or os.path.exists(path_str):
        return file

    mode_str = str(mode) if mode is not None else "r"
    is_read_mode = "r" in mode_str and not any(
        m in mode_str for m in ("w", "a", "+", "x")
    )
    if not is_read_mode:
        return file

    norm = os.path.normpath(path_str)
    if norm == os.path.normpath("config/google-ads.yaml"):
        env_cfg = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
        if env_cfg and os.path.isfile(env_cfg):
            return env_cfg
        plugin_cfg = os.path.join(_THIS_CONFIG_DIR, "google-ads.yaml")
        if os.path.isfile(plugin_cfg):
            return plugin_cfg
    elif norm == os.path.normpath("config/assistant_config"):
        plugin_acfg = os.path.join(_THIS_CONFIG_DIR, "assistant_config")
        if os.path.isfile(plugin_acfg):
            return plugin_acfg
    elif norm == os.path.normpath("config/financial_limits"):
        env_fl = os.environ.get("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", "").strip()
        if env_fl and os.path.isfile(env_fl):
            return env_fl
        plugin_fl = os.path.join(_THIS_CONFIG_DIR, "financial_limits")
        if os.path.isfile(plugin_fl):
            return plugin_fl

    return file


def _assistant_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    resolved = _resolve_assistant_config_file(file, mode)
    return _ORIG_OPEN(resolved, mode, *args, **kwargs)


builtins.open = _assistant_open

try:
    import io as _io

    _io.open = _assistant_open
except Exception:
    pass

try:
    import pathlib as _pathlib

    _ORIG_PATH_OPEN = _pathlib.Path.open

    def _assistant_path_open(
        self: Any, mode: str = "r", *args: Any, **kwargs: Any
    ) -> Any:
        resolved = _resolve_assistant_config_file(self, mode)
        if resolved is not self and isinstance(resolved, str):
            return _ORIG_OPEN(resolved, mode, *args, **kwargs)
        return _ORIG_PATH_OPEN(self, mode, *args, **kwargs)

    _pathlib.Path.open = _assistant_path_open  # type: ignore[method-assign]
except Exception:
    pass

_ORIG_ISFILE = os.path.isfile


def _assistant_isfile(path: Any) -> bool:
    if _ORIG_ISFILE(path):
        return True
    if not isinstance(path, (str, os.PathLike)):
        return False
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "_GOOGLE_ADS_TEST_SITECUSTOMIZE"
    ):
        return False
    try:
        path_str = os.fspath(path)
    except TypeError:
        return False
    if not isinstance(path_str, str) or os.path.isabs(path_str):
        return False
    norm = os.path.normpath(path_str)
    if norm == os.path.normpath("config/google-ads.yaml"):
        env_cfg = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
        if env_cfg and _ORIG_ISFILE(env_cfg):
            return True
        return _ORIG_ISFILE(os.path.join(_THIS_CONFIG_DIR, "google-ads.yaml"))
    if norm == os.path.normpath("config/assistant_config"):
        return _ORIG_ISFILE(os.path.join(_THIS_CONFIG_DIR, "assistant_config"))
    if norm == os.path.normpath("config/financial_limits"):
        env_fl = os.environ.get("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", "").strip()
        if env_fl and _ORIG_ISFILE(env_fl):
            return True
        return _ORIG_ISFILE(os.path.join(_THIS_CONFIG_DIR, "financial_limits"))
    return False


os.path.isfile = _assistant_isfile

