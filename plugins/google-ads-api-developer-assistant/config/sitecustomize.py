"""Runtime path resolution shim for Google Ads API Developer Assistant.

When loaded via PYTHONPATH from the installed plugin's config/ directory, this
shim ensures that calls such as GoogleAdsClient.load_from_storage(path="config/google-ads.yaml")
succeed in any working directory without requiring a local ./config/ folder or
the GitHub source checkout.
"""

import builtins
import importlib.util
import os
import sys
from typing import Any

_ORIG_OPEN = getattr(builtins.open, "_gads_orig", builtins.open)
_THIS_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))


def _is_raw_home_yaml(candidate: str) -> bool:
    expanded = os.path.abspath(os.path.expanduser(candidate))
    raw_home = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
    return expanded == raw_home


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
        if env_cfg and not _is_raw_home_yaml(env_cfg):
            exp_cfg = os.path.expanduser(env_cfg)
            if _ORIG_ISFILE(exp_cfg):
                return env_cfg if _ORIG_ISFILE(env_cfg) else exp_cfg
        plugin_cfg = os.path.join(_THIS_CONFIG_DIR, "google-ads.yaml")
        if _ORIG_ISFILE(plugin_cfg):
            return plugin_cfg
    elif norm == os.path.normpath("config/assistant_config"):
        plugin_acfg = os.path.join(_THIS_CONFIG_DIR, "assistant_config")
        if _ORIG_ISFILE(plugin_acfg):
            return plugin_acfg
    elif norm == os.path.normpath("config/financial_limits"):
        env_fl = os.environ.get("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", "").strip()
        if env_fl and _ORIG_ISFILE(env_fl):
            return env_fl
        plugin_fl = os.path.join(_THIS_CONFIG_DIR, "financial_limits")
        if _ORIG_ISFILE(plugin_fl):
            return plugin_fl

    return file


_ORIG_ISFILE = getattr(os.path.isfile, "_gads_orig", os.path.isfile)


def _assistant_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
    resolved = _resolve_assistant_config_file(file, mode)
    return _ORIG_OPEN(resolved, mode, *args, **kwargs)


_assistant_open._gads_orig = _ORIG_OPEN  # type: ignore[attr-defined]
builtins.open = _assistant_open

try:
    import io as _io

    _io.open = _assistant_open
except Exception:
    pass

try:
    import pathlib as _pathlib

    _ORIG_PATH_OPEN = getattr(
        _pathlib.Path.open, "_gads_orig", _pathlib.Path.open
    )

    def _assistant_path_open(
        self: Any, mode: str = "r", *args: Any, **kwargs: Any
    ) -> Any:
        resolved = _resolve_assistant_config_file(self, mode)
        if resolved is not self and isinstance(resolved, str):
            return _ORIG_OPEN(resolved, mode, *args, **kwargs)
        return _ORIG_PATH_OPEN(self, mode, *args, **kwargs)

    _assistant_path_open._gads_orig = _ORIG_PATH_OPEN  # type: ignore[attr-defined]
    _pathlib.Path.open = _assistant_path_open  # type: ignore[method-assign]
except Exception:
    pass


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
        if (
            env_cfg
            and not _is_raw_home_yaml(env_cfg)
            and _ORIG_ISFILE(os.path.expanduser(env_cfg))
        ):
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


_assistant_isfile._gads_orig = _ORIG_ISFILE  # type: ignore[attr-defined]
os.path.isfile = _assistant_isfile


def _chain_downstream_sitecustomize() -> None:
    """Executes the next sitecustomize.py on sys.path without recursion."""
    this_real = os.path.normcase(os.path.realpath(__file__))
    seen = getattr(sys, "_gads_chained_sitecustomizes", None)
    if seen is None:
        seen = set()
        setattr(sys, "_gads_chained_sitecustomizes", seen)
    seen.add(this_real)
    for entry in list(sys.path):
        if not entry:
            continue
        cand = os.path.join(entry, "sitecustomize.py")
        if _ORIG_ISFILE(cand):
            real_cand = os.path.normcase(os.path.realpath(cand))
            if real_cand not in seen:
                seen.add(real_cand)
                spec = importlib.util.spec_from_file_location(
                    "_gads_downstream_sitecustomize", cand
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                break


try:
    _chain_downstream_sitecustomize()
except Exception:
    pass

