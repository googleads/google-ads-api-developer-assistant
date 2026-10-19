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
    if not isinstance(file, (str, bytes)):
        return file
    if isinstance(file, bytes):
        return file

    # Preserve strict local isolation during unit test runs unless explicitly testing the shim
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get(
        "_GOOGLE_ADS_TEST_SITECUSTOMIZE"
    ):
        return file

    if os.path.isabs(file) or os.path.exists(file):
        return file

    norm = os.path.normpath(file)
    if norm == os.path.normpath("config/google-ads.yaml"):
        env_cfg = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
        if env_cfg and os.path.isfile(env_cfg):
            return env_cfg
        plugin_cfg = os.path.join(_THIS_CONFIG_DIR, "google-ads.yaml")
        if os.path.isfile(plugin_cfg):
            return plugin_cfg
    elif norm == os.path.normpath("config/assistant_config") and (
        "r" in mode and "w" not in mode and "a" not in mode and "+" not in mode
    ):
        plugin_acfg = os.path.join(_THIS_CONFIG_DIR, "assistant_config")
        if os.path.isfile(plugin_acfg):
            return plugin_acfg

    return file


def _assistant_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    resolved = _resolve_assistant_config_file(file, mode)
    return _ORIG_OPEN(resolved, mode, *args, **kwargs)


builtins.open = _assistant_open
