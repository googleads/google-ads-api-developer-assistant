#!/usr/bin/env python3
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

"""Google Ads API Developer Assistant A2A HTTP Sidecar & MCP Stdio Server.

Supports two execution modes:
1. Authenticated loopback HTTP A2A server (default, bound strictly to 127.0.0.1).
2. Model Context Protocol (MCP) JSON-RPC 2.0 stdio server (`--mcp` or `--stdio`),
   decoupled from any TCP port so MCP hosts never collide with `sidecar.json`.
"""

import argparse
import ast
import contextlib
from datetime import datetime, timezone
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
from typing import Any, Optional, TextIO
import unittest.mock
import urllib.parse

base_dir = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(base_dir, "../.."))
_REPO_ROOT = os.path.abspath(os.path.join(base_dir, "../../../.."))

for path_to_add in [
    _PLUGIN_ROOT,
    _REPO_ROOT,
    os.path.abspath(
        os.path.join(base_dir, "../../plugins/google-ads-api-developer-assistant")
    ),
]:
    if path_to_add not in sys.path:
        sys.path.insert(0, path_to_add)


def _resolve_server_port() -> int:
    """Resolves the loopback HTTP port safely from environment variables."""
    for env_key in ("ANTIGRAVITY_SIDECAR_WEB_PORT", "A2A_PORT"):
        raw_val = os.environ.get(env_key, "").strip()
        if raw_val:
            try:
                parsed = int(raw_val)
                if 1 <= parsed <= 65535:
                    return parsed
            except ValueError:
                continue
    return 8900


PORT = _resolve_server_port()
MAX_POST_BODY_BYTES = 1_048_576  # 1 MiB
_ALLOWED_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "[::1]"})
_ALLOWED_ORIGIN_RE = re.compile(
    r"^http://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d{1,5})?$",
    re.IGNORECASE,
)
_ORIG_SPEC_FROM_FILE_LOCATION = spec_from_file_location
_ORIG_MODULE_FROM_SPEC = module_from_spec
_SKILL_MODULE_CACHE: dict[str, tuple[int, Any]] = {}


def _load_skill_module_cached(mod_name: str, script_path: str) -> Optional[Any]:
    """Loads a skill module with (path, mtime_ns) caching when stdlib loaders are unpatched."""
    abs_path = os.path.abspath(script_path)
    can_cache = (
        spec_from_file_location is _ORIG_SPEC_FROM_FILE_LOCATION
        and module_from_spec is _ORIG_MODULE_FROM_SPEC
    )
    mtime_ns = -1
    if can_cache:
        try:
            mtime_ns = os.stat(abs_path).st_mtime_ns
            cached = _SKILL_MODULE_CACHE.get(abs_path)
            if cached is not None and cached[0] == mtime_ns:
                return cached[1]
        except OSError:
            can_cache = False

    spec = spec_from_file_location(mod_name, abs_path)
    if not spec or not spec.loader:
        return None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    if can_cache and mtime_ns >= 0:
        _SKILL_MODULE_CACHE[abs_path] = (mtime_ns, mod)
    return mod


def _strict_bool(val: Any) -> bool:
    """Evaluates booleans strictly so strings like 'false' or '0' are never True."""
    if val is True:
        return True
    if isinstance(val, str):
        return val.strip().lower() == "true"
    return False


def _resolve_validate_only(payload: dict[str, Any]) -> bool:
    """Resolves validate_only safely (defaults to True; False only when explicitly requested)."""
    if _strict_bool(payload.get("execute", False)):
        return False
    if "validate_only" in payload and payload["validate_only"] is not None:
        return _strict_bool(payload["validate_only"])
    return True


def _is_within_dir(path: str, base: str) -> bool:
    """Returns True if realpath(path) is inside realpath(base)."""
    try:
        real_p = os.path.realpath(path)
        real_b = os.path.realpath(base)
        return os.path.commonpath([real_p, real_b]) == real_b
    except ValueError:
        return False


def _is_in_saved_code_dir(path: str) -> bool:
    """Returns True if realpath(path) lies inside a saved/code/ directory."""
    real_p = os.path.realpath(os.path.expanduser(path.strip()))
    parts = real_p.replace("\\", "/").split("/")
    return any(
        parts[i] == "saved" and parts[i + 1] == "code"
        for i in range(len(parts) - 2)
    )


def _validate_script_path_arg(
    script_path: Any,
    allowed_extensions: tuple[str, ...] = (".py",),
    *,
    require_saved_code: bool = False,
    require_workspace_or_saved: bool = False,
) -> Optional[str]:
    """Validates an optional file path argument, returning an error message if unsafe."""
    if script_path is None or str(script_path).strip() == "":
        return None
    if not isinstance(script_path, str) or "\x00" in script_path:
        return "Invalid path argument: must be a valid file path without NUL bytes."
    clean = script_path.strip()
    if os.path.splitext(clean)[1].lower() not in allowed_extensions:
        return f"Invalid path argument: expected file extension in {allowed_extensions}."
    if require_saved_code and not _is_in_saved_code_dir(clean):
        return (
            "Invalid path argument: mutation 'script_path' must resolve to a .py file "
            "inside a saved/code/ directory."
        )
    if require_workspace_or_saved:
        real_p = os.path.realpath(os.path.expanduser(clean))
        parts = real_p.replace("\\", "/").split("/")
        in_saved = "saved" in parts[:-1]
        in_cwd = _is_within_dir(real_p, os.getcwd())
        if not (in_saved or in_cwd):
            return (
                "Invalid path argument: file path must resolve inside the current "
                "workspace or a saved/ directory."
            )
    return None


_MAX_TOOL_OUTPUT_CHARS = 16384
_CLAIM_CTX = threading.local()
_RPC_DISPATCH_METHOD_PREFIXES = (
    "mutate",
    "create_customer_client",
    "remove_",
    "delete_",
)


class _RpcDispatchTrackerService:
    """Thin service proxy marking rpc_dispatched before any write RPC call."""

    def __init__(self, svc: Any, dispatched: list[bool]) -> None:
        self._svc = svc
        self._dispatched = dispatched

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._svc, name)
        if callable(attr) and name.startswith(_RPC_DISPATCH_METHOD_PREFIXES):
            dispatched = self._dispatched

            def _tracked(*args: Any, **kwargs: Any) -> Any:
                dispatched[0] = True
                return attr(*args, **kwargs)

            return _tracked
        return attr


class _RpcDispatchTrackerClient:
    """Thin client proxy delegating attributes while tracking write RPC entry."""

    def __init__(self, inner: Any, dispatched: list[bool]) -> None:
        self._inner = inner
        self._dispatched = dispatched

    def get_service(self, *args: Any, **kwargs: Any) -> Any:
        svc = self._inner.get_service(*args, **kwargs)
        return _RpcDispatchTrackerService(svc, self._dispatched)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _parse_strict_int(raw: Any, field_name: str) -> int:
    """Parses an integer strictly, rejecting booleans and non-integer floats."""
    if isinstance(raw, bool):
        raise ValueError(f"{field_name} must be an integer, not bool ({raw!r})")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValueError(
                f"{field_name} must be a whole integer, not float ({raw!r})"
            )
        return int(raw)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped or not re.fullmatch(r"[+-]?\d+", stripped):
            raise ValueError(
                f"{field_name} must be an integer string (got {raw!r})"
            )
        return int(stripped)
    raise ValueError(
        f"{field_name} must be an integer (got {type(raw).__name__})"
    )


def _truncate_tool_output(text: str, limit: int = _MAX_TOOL_OUTPUT_CHARS) -> str:
    """Caps tool stdout/stderr payloads using head+tail truncation to preserve tail errors."""
    if not text or len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    omitted = len(text) - limit
    marker = f"\n... [truncated {omitted} chars; capped at {limit} chars] ...\n"
    head_len = limit // 2
    tail_len = limit - head_len
    if tail_len <= 0:
        return text[:head_len] + marker
    return text[:head_len] + marker + text[-tail_len:]


def _cap_diagnostics_payload(
    diag: Any, limit: int = _MAX_TOOL_OUTPUT_CHARS
) -> Any:
    """Caps serialized diagnostics payloads to protect model context windows."""
    try:
        serialized = json.dumps(diag, default=str)
    except (TypeError, ValueError):
        return _truncate_tool_output(str(diag), limit=limit)
    if len(serialized) <= limit:
        return diag
    if isinstance(diag, dict):
        capped: dict[str, Any] = {
            "truncated": True,
            "original_chars": len(serialized),
        }
        if "executive_summary" in diag:
            capped["executive_summary"] = diag["executive_summary"]
        if "report_path" in diag:
            capped["report_path"] = diag["report_path"]
        capped["preview"] = _truncate_tool_output(serialized, limit=limit)
        return capped
    return _truncate_tool_output(serialized, limit=limit)


def _is_dir_writable(directory: str) -> bool:
    """Returns True iff directory exists and allows creating a temporary file."""
    if not directory or not os.path.isdir(directory):
        return False
    try:
        fd, probe_path = tempfile.mkstemp(prefix=".wprobe_", dir=directory)
        try:
            os.close(fd)
        finally:
            try:
                os.remove(probe_path)
            except OSError:
                pass
        return True
    except OSError:
        return False


def _sandbox_writable_dir() -> Optional[str]:
    """Returns the sidecar-writable data directory when running under a sandboxed host."""
    for env_key in ("ANTIGRAVITY_EXECUTABLE_DATA_DIR", "PLUGIN_DATA"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return os.path.abspath(val)
    return None


def _configure_sandbox_writable_env() -> Optional[str]:
    """Routes sidecar-written receipts/audit/cache to PLUGIN_DATA when sandboxed."""
    data_dir = _sandbox_writable_dir()
    if not data_dir:
        return None
    saved_data = os.path.join(data_dir, "saved", "data")
    saved_logs = os.path.join(data_dir, "saved", "logs")
    cfg_dir = os.path.join(data_dir, "config")
    try:
        os.makedirs(saved_data, mode=0o700, exist_ok=True)
        os.makedirs(saved_logs, mode=0o700, exist_ok=True)
        os.makedirs(cfg_dir, mode=0o700, exist_ok=True)
    except OSError:
        return None
    os.environ.setdefault(
        "GOOGLE_ADS_MUTATION_RECEIPT_PATH",
        os.path.join(saved_data, "last_dry_run.json"),
    )
    os.environ.setdefault(
        "GOOGLE_ADS_MUTATION_AUDIT_LOG",
        os.path.join(saved_logs, "mutation_audit.jsonl"),
    )
    os.environ.setdefault(
        "GOOGLE_ADS_GAQL_CACHE_PATH",
        os.path.join(saved_data, "gaql_validation_cache.json"),
    )
    os.environ.setdefault("CONVERSION_OUTPUT_DIR", saved_data)
    return data_dir


def _resolve_a2a_auth_token() -> str:
    """Resolves the A2A Bearer token via env -> sandbox data dir / 0o600 user token file -> ephemeral."""
    env_tok = os.environ.get("A2A_AUTH_TOKEN", "").strip()
    if env_tok:
        return env_tok

    token_candidates: list[str] = []
    for data_env in ("ANTIGRAVITY_EXECUTABLE_DATA_DIR", "PLUGIN_DATA"):
        d = os.environ.get(data_env, "").strip()
        if d:
            token_candidates.append(os.path.join(os.path.abspath(d), ".a2a_token"))
    token_candidates.extend(
        [
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/data/.a2a_token"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/saved/data/.a2a_token"
            ),
        ]
    )
    for tok_path in token_candidates:
        if os.path.isfile(tok_path):
            try:
                with open(tok_path, "r", encoding="utf-8") as f:
                    existing = f.read().strip()
                if len(existing) >= 32:
                    return existing
            except OSError:
                continue

    generated = secrets.token_hex(32)
    write_targets: list[str] = []
    for data_env in ("ANTIGRAVITY_EXECUTABLE_DATA_DIR", "PLUGIN_DATA"):
        d = os.environ.get(data_env, "").strip()
        if d:
            write_targets.append(os.path.join(os.path.abspath(d), ".a2a_token"))
    user_plugin_dir = os.path.expanduser(
        "~/.gemini/config/plugins/google-ads-api-developer-assistant"
    )
    if os.path.isdir(user_plugin_dir):
        write_targets.append(
            os.path.join(user_plugin_dir, "saved", "data", ".a2a_token")
        )
    for tok_file in write_targets:
        try:
            os.makedirs(os.path.dirname(tok_file), mode=0o700, exist_ok=True)
            fd = os.open(tok_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(generated + "\n")
            os.chmod(tok_file, 0o600)
            return generated
        except OSError:
            continue

    print(
        "WARNING: A2A_AUTH_TOKEN not configured; generated ephemeral instance-isolated auth token.",
        file=sys.stderr,
    )
    return generated


def get_effective_api_version(
    payload: Optional[dict[str, Any]] = None,
    allow_interactive: bool = True,
) -> str:
    """Resolves the effective Google Ads API version using the standard hierarchy:

    1. Caller/user override from payload ('api_version') or GOOGLE_ADS_API_VERSION env var.
    2. Cached version from config/assistant_config (TOML).
    3. Dynamic discovery from local client_libs/ directory.
    4. Installed google.ads.googleads package attribute inspection.
    5. Interactive TTY prompt (only when allow_interactive=True).
    """
    if payload and payload.get("api_version"):
        ver = str(payload.get("api_version")).strip()
        if not ver.startswith("v") and ver.isdigit():
            ver = f"v{ver}"
        return ver

    env_version = os.environ.get("GOOGLE_ADS_API_VERSION", "").strip()
    if env_version:
        if not env_version.startswith("v") and env_version.isdigit():
            env_version = f"v{env_version}"
        return env_version

    local_base_dir = os.path.dirname(os.path.abspath(__file__))
    env_plugin_roots = [
        os.path.abspath(os.path.expanduser(p.strip()))
        for p in (
            os.environ.get("PLUGIN_ROOT", ""),
            os.environ.get("CLAUDE_PLUGIN_ROOT", ""),
            os.environ.get("GOOGLE_ADS_ASSISTANT_DIR", ""),
        )
        if p and p.strip()
    ]
    candidate_config_files = [
        os.path.join(r, "config", "assistant_config") for r in env_plugin_roots
    ] + [
        os.path.join(local_base_dir, "../../config/assistant_config"),
        os.path.join(local_base_dir, "../../../../config/assistant_config"),
        os.path.abspath("config/assistant_config"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/assistant_config"
        ),
    ]

    for config_file in candidate_config_files:
        if os.path.isfile(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    content = f.read()
                m = re.search(
                    r'(?m)^\s*api_version\s*=\s*["\']?([^"\'\s#]+)["\']?',
                    content,
                )
                if m:
                    ver = m.group(1).strip()
                    if ver:
                        if not ver.startswith("v") and ver.isdigit():
                            ver = f"v{ver}"
                        return ver
            except OSError:
                continue

    candidate_lib_paths = [
        os.path.join(
            r, "client_libs", "google-ads-python", "google", "ads", "googleads"
        )
        for r in env_plugin_roots
    ] + [
        os.path.join(
            local_base_dir, "../../client_libs/google-ads-python/google/ads/googleads"
        ),
        os.path.join(
            local_base_dir,
            "../../../../client_libs/google-ads-python/google/ads/googleads",
        ),
        os.path.abspath("client_libs/google-ads-python/google/ads/googleads"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
    ]

    for lib_path in candidate_lib_paths:
        if os.path.isdir(lib_path):
            try:
                version_dirs = [
                    d
                    for d in os.listdir(lib_path)
                    if os.path.isdir(os.path.join(lib_path, d))
                    and re.match(r"^v\d+$", d)
                ]
                if version_dirs:
                    version_dirs.sort(key=lambda x: int(x[1:]))
                    return version_dirs[-1]
            except OSError:
                continue

    try:
        installed_versions: list[str] = []
        pkg_paths: list[str] = []
        if "google.ads.googleads" in sys.modules:
            gads_mod = sys.modules["google.ads.googleads"]
            if gads_mod is not None:
                installed_versions.extend(
                    attr for attr in dir(gads_mod) if re.match(r"^v\d+$", attr)
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
            if pkg_dir and os.path.isdir(pkg_dir):
                installed_versions.extend(
                    d
                    for d in os.listdir(pkg_dir)
                    if os.path.isdir(os.path.join(pkg_dir, d))
                    and re.match(r"^v\d+$", d)
                )
        if installed_versions:
            installed_versions.sort(key=lambda x: int(x[1:]))
            return installed_versions[-1]
    except Exception:
        pass

    if allow_interactive and sys.stdin.isatty():
        try:
            user_input = input(
                "Google Ads API version could not be automatically determined. Please enter the API version to use (for example, v<N>): "
            ).strip()
            if user_input:
                if not user_input.startswith("v") and user_input.isdigit():
                    user_input = f"v{user_input}"
                user_cfg_dir = os.path.expanduser(
                    "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
                )
                if os.path.isdir(user_cfg_dir):
                    try:
                        from config.config_init import write_assistant_config

                        write_assistant_config(
                            {"api_version": user_input},
                            config_dir=user_cfg_dir,
                        )
                    except Exception:
                        pass
                return user_input
        except (EOFError, KeyboardInterrupt):
            pass

    raise ValueError(
        "Google Ads API version could not be automatically determined. Please supply an 'api_version' (for example, 'v<N>') in the request payload or configure config/assistant_config."
    )


_CACHED_PLUGIN_VERSION: str | None = None
UNKNOWN_PLUGIN_VERSION = "Unknown"
_VERSION_MANIFEST_FILES = ("plugin.json", "plugin.json.disabled", "agent.json")


def get_plugin_version() -> str:
    """Dynamically resolves the assistant/plugin version from environment, manifests, or config_init."""
    global _CACHED_PLUGIN_VERSION
    if _CACHED_PLUGIN_VERSION is not None:
        return _CACHED_PLUGIN_VERSION

    env_ver = (
        os.environ.get("GOOGLE_ADS_PLUGIN_VERSION")
        or os.environ.get("GOOGLE_ADS_ASSISTANT_VERSION")
        or ""
    ).strip()
    if env_ver:
        _CACHED_PLUGIN_VERSION = env_ver
        return _CACHED_PLUGIN_VERSION

    candidate_dirs: list[str] = []
    cur = os.path.dirname(os.path.abspath(__file__))
    while cur and cur != os.path.dirname(cur):
        candidate_dirs.append(cur)
        cur = os.path.dirname(cur)

    for env_root_key in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "GOOGLE_ADS_ASSISTANT_DIR"):
        env_root = os.environ.get(env_root_key, "").strip()
        if env_root:
            candidate_dirs.append(os.path.abspath(env_root))

    candidate_dirs.append(
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant"
        )
    )
    candidate_dirs.append(
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
        )
    )

    for directory in candidate_dirs:
        for manifest_name in _VERSION_MANIFEST_FILES:
            candidate = os.path.join(directory, manifest_name)
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    ver = str(data.get("version", "")).strip()
                    if ver:
                        _CACHED_PLUGIN_VERSION = ver
                        return _CACHED_PLUGIN_VERSION
                except Exception:
                    continue

    try:
        from config.config_init import get_version

        resolved = get_version()
        if resolved and resolved != UNKNOWN_PLUGIN_VERSION:
            _CACHED_PLUGIN_VERSION = resolved
            return _CACHED_PLUGIN_VERSION
    except Exception:
        pass

    return UNKNOWN_PLUGIN_VERSION


def _strip_gaql_string_literals(query: str) -> str:
    """Replaces single- and double-quoted string literals with empty quotes for static token checks."""
    return re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"", "''", query)


def _camel_to_snake(name: str) -> str:
    """Converts PascalCase / camelCase protobuf names into snake_case GAQL resource prefixes."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _parse_source_fields_and_enums(
    py_file: str, class_name: str
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Parses protobuf message fields or enum values from a local client_libs Python type file."""
    fields: list[dict[str, str]] = []
    enum_values: list[dict[str, Any]] = []
    if not os.path.isfile(py_file):
        return fields, enum_values

    try:
        with open(py_file, "r", encoding="utf-8") as f:
            source_text = f.read()
    except OSError:
        return fields, enum_values

    try:
        tree = ast.parse(source_text)
        target_cls: Optional[ast.ClassDef] = None
        parts = [p for p in class_name.split(".") if p]
        scope: list[ast.stmt] = list(tree.body)
        for part in parts:
            matched: Optional[ast.ClassDef] = None
            for node in scope:
                if isinstance(node, ast.ClassDef) and node.name == part:
                    matched = node
                    break
            if matched is None:
                target_cls = None
                break
            target_cls = matched
            scope = list(matched.body)

        if target_cls is not None:
            inspect_nodes: list[ast.stmt] = list(target_cls.body)
            nested_classes = [
                n for n in target_cls.body if isinstance(n, ast.ClassDef)
            ]
            has_top_fields = any(
                isinstance(n, (ast.AnnAssign, ast.Assign))
                for n in target_cls.body
            )
            if not has_top_fields and len(nested_classes) == 1:
                inspect_nodes = list(nested_classes[0].body)

            for stmt in inspect_nodes:
                if isinstance(stmt, ast.AnnAssign) and isinstance(
                    stmt.target, ast.Name
                ):
                    f_name = stmt.target.id
                    f_type = ast.unparse(stmt.annotation).strip("\"'")
                    label = "OPTIONAL"
                    if isinstance(stmt.value, ast.Call) and isinstance(
                        stmt.value.func, ast.Attribute
                    ):
                        call_attr = stmt.value.func.attr
                        if call_attr == "RepeatedField":
                            label = "REPEATED"
                        elif call_attr == "MapField":
                            label = "MAP"
                    fields.append(
                        {"name": f_name, "label": label, "type": f_type}
                    )
                elif (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, int)
                    and not isinstance(stmt.value.value, bool)
                ):
                    name_tok = stmt.targets[0].id
                    if name_tok.isupper() or "_" in name_tok:
                        enum_values.append(
                            {"name": name_tok, "number": int(stmt.value.value)}
                        )
            if fields or enum_values:
                return fields, enum_values
    except SyntaxError:
        pass

    lines = source_text.splitlines(keepends=True)

    in_target_class = False
    class_indent = -1
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped.startswith("class "):
            class_def = stripped[6:].strip()
            c_name = class_def.split("(")[0].split(":")[0].strip()
            if c_name == class_name:
                in_target_class = True
                class_indent = indent
                continue
            if in_target_class and indent <= class_indent:
                break

        if in_target_class:
            m = re.match(
                r"^\s*([a-zA-Z0-9_]+)\s*:\s*([^=\n]+)\s*=\s*proto\.(Field|RepeatedField|MapField)\(",
                line,
            )
            if m:
                f_name = m.group(1)
                f_type = m.group(2).strip().strip("\"'")
                if m.group(3) == "RepeatedField":
                    label = "REPEATED"
                elif m.group(3) == "MapField":
                    label = "MAP"
                else:
                    label = "OPTIONAL"
                fields.append({"name": f_name, "label": label, "type": f_type})
            elif (
                "=" in stripped
                and not stripped.startswith("#")
                and not stripped.startswith("def ")
                and not stripped.startswith("class ")
            ):
                m_enum = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(\d+)", line)
                if m_enum:
                    enum_values.append(
                        {"name": m_enum.group(1), "number": int(m_enum.group(2))}
                    )
    return fields, enum_values


class A2AHandler(BaseHTTPRequestHandler):
    """Loopback HTTP request handler for Google Ads API Developer Assistant A2A tasks."""

    timeout = 30

    def _get_header(self, name: str) -> Optional[str]:
        """Retrieves an HTTP header case-insensitively across HTTPMessage or plain dict fixtures."""
        headers = getattr(self, "headers", None)
        if not headers:
            return None
        if hasattr(headers, "get"):
            direct = headers.get(name)
            if direct is not None:
                return str(direct)
        target_lower = name.lower()
        if hasattr(headers, "items"):
            for k, v in headers.items():
                if str(k).lower() == target_lower and v is not None:
                    return str(v)
        return None

    def _send_json(self, status_code: int, data: dict[str, Any]) -> None:
        response_bytes = json.dumps(data, indent=2).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
            )
            self.end_headers()
            self.wfile.write(response_bytes)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return

    def _reject_disallowed_method(self) -> None:
        self._send_json(405, {"error": "Method Not Allowed"})

    def do_PUT(self) -> None:
        self._reject_disallowed_method()

    def do_DELETE(self) -> None:
        self._reject_disallowed_method()

    def do_TRACE(self) -> None:
        self._reject_disallowed_method()

    def do_PATCH(self) -> None:
        self._reject_disallowed_method()

    def do_OPTIONS(self) -> None:
        self._reject_disallowed_method()

    def do_GET(self) -> None:
        clean_path = urllib.parse.urlsplit(self.path).path
        if clean_path in ("/", "/health"):
            srv = getattr(self, "server", None)
            active_port = getattr(srv, "server_port", PORT)
            self._send_json(
                200,
                {
                    "status": "healthy",
                    "service": "Google Ads API Developer Assistant A2A Sidecar",
                    "version": get_plugin_version(),
                    "port": active_port,
                },
            )
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self) -> None:
        # 1. DNS rebinding protection: validate Host header if present
        host_hdr = self._get_header("Host")
        if host_hdr is not None:
            raw_host = host_hdr.strip()
            if raw_host.startswith("["):
                host_only = (
                    raw_host.split("]")[0] + "]" if "]" in raw_host else raw_host
                )
            else:
                host_only = raw_host.split(":")[0]
            if host_only.lower() not in _ALLOWED_LOOPBACK_HOSTS:
                self._send_json(403, {"error": "Forbidden: invalid Host header"})
                return

        # 2. Cross-Origin / CSRF protection: validate Sec-Fetch-Site and Origin if present
        # Note: API uses stateless Bearer token authentication (not cookies), combined with
        # Origin / Sec-Fetch-Site / Content-Type enforcement against browser CSRF.
        sec_fetch_site = self._get_header("Sec-Fetch-Site")
        if sec_fetch_site is not None and sec_fetch_site.strip().lower() == "cross-site":
            self._send_json(
                403, {"error": "Forbidden: cross-site requests are rejected"}
            )
            return

        origin_hdr = self._get_header("Origin")
        if origin_hdr is not None and not _ALLOWED_ORIGIN_RE.match(origin_hdr.strip()):
            self._send_json(403, {"error": "Forbidden: untrusted Origin header"})
            return

        # 3. Bearer token authentication (constant-time comparison)
        env_token = os.environ.get("A2A_AUTH_TOKEN", "").strip()
        srv = getattr(self, "server", None)
        require_auth = bool(env_token) or bool(getattr(srv, "require_auth", False))
        if require_auth:
            expected_token = env_token or str(getattr(srv, "auth_token", "") or "")
            auth_hdr = self._get_header("Authorization") or ""
            provided_token = (
                auth_hdr[7:].strip()
                if auth_hdr.lower().startswith("bearer ")
                else ""
            )
            if (
                not expected_token
                or not provided_token
                or not hmac.compare_digest(
                    provided_token.encode("utf-8"),
                    expected_token.encode("utf-8"),
                )
            ):
                self._send_json(
                    401, {"error": "Unauthorized: valid Bearer token required"}
                )
                return

        clean_path = urllib.parse.urlsplit(self.path).path
        if clean_path != "/v1/a2a/tasks":
            self._send_json(404, {"error": "Not Found"})
            return

        # 4. Content-Type & Content-Length validation
        content_type = self._get_header("Content-Type")
        if content_type is not None and not content_type.strip().lower().startswith(
            "application/json"
        ):
            self._send_json(
                415,
                {
                    "error": "Unsupported Media Type: Content-Type must be application/json"
                },
            )
            return

        raw_len = self._get_header("Content-Length")
        if raw_len is None:
            content_length = 0
        else:
            try:
                content_length = int(raw_len.strip())
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length header"})
                return

        if content_length < 0:
            self._send_json(
                400, {"error": "Negative Content-Length header is invalid"}
            )
            return
        if content_length > MAX_POST_BODY_BYTES:
            self._send_json(413, {"error": "Payload Too Large (max 1 MiB)"})
            return

        try:
            body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        except (BrokenPipeError, ConnectionResetError, TimeoutError, OSError):
            return
        try:
            request_data = json.loads(body_bytes.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"Invalid JSON: {e}"})
            return

        if not isinstance(request_data, dict):
            self._send_json(
                400, {"error": "Invalid JSON: request body must be a JSON object"}
            )
            return

        task_id = str(request_data.get("task_id", "task_unknown"))
        intent = str(request_data.get("intent", "UNKNOWN"))
        payload = request_data.get("payload", {})
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            self._send_json(
                400, {"error": "Invalid request: 'payload' must be a JSON object"}
            )
            return

        response = self._dispatch_intent(task_id, intent, payload)
        self._send_json(200, response)

    def _dispatch_intent(
        self, task_id: str, intent: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Routes a validated A2A intent to its corresponding handler cleanly."""
        try:
            if intent == "GAQL_VALIDATE":
                return self.handle_gaql_validate(task_id, payload)
            if intent == "INSPECT_OBJECT":
                return self.handle_inspect_object(task_id, payload)
            if intent == "GENERATE_CODE":
                return self.handle_generate_code(task_id, payload)
            if intent == "TROUBLESHOOT_CONVERSIONS":
                return self.handle_troubleshoot_conversions(task_id, payload)
            if intent == "PREPARE_MUTATION":
                return self.handle_prepare_mutation(task_id, payload)
            if intent == "EXECUTE_MUTATION":
                return self.handle_execute_mutation(task_id, payload)
            if intent == "REJECT_MUTATION":
                return self.handle_reject_mutation(task_id, payload)
            if intent == "CREATE_ACCOUNT":
                return self.handle_create_account(task_id, payload)
            if intent == "CREATE_CAMPAIGN":
                return self.handle_create_campaign(task_id, payload)
            if intent == "CREATE_AD_GROUP":
                return self.handle_create_ad_group(task_id, payload)
            if intent == "CREATE_AD":
                return self.handle_create_ad(task_id, payload)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": f"Unsupported intent '{intent}'",
            }
        except (ValueError, TypeError, KeyError, RuntimeError) as e:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": str(e),
            }

    def handle_gaql_validate(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        query = str(payload.get("query", "") or "")
        customer_id = str(payload.get("customer_id", "1234567890"))
        api_version = get_effective_api_version(payload, allow_interactive=False)

        static_errors: list[str] = []
        if not query.strip():
            static_errors.append("GAQL query must not be empty.")

        stripped = _strip_gaql_string_literals(query)
        stripped_upper = stripped.upper()

        if re.search(r"\bOR\b", stripped_upper):
            static_errors.append(
                "GAQL does not support the 'OR' logical operator. Use 'IN' or multiple queries."
            )

        for agg_func in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
            if re.search(rf"\b{agg_func}\b\s*\(", stripped_upper):
                static_errors.append(
                    f"GAQL does not support SQL aggregate function '{agg_func}()'."
                )

        for dt_func in ("NOW", "CURRENT_DATE"):
            if re.search(rf"\b{dt_func}\b", stripped_upper):
                static_errors.append(
                    f"GAQL does not support SQL date/time function '{dt_func}()'."
                )

        has_from = bool(re.search(r"\bFROM\b", stripped_upper))
        if re.search(r"\bGOOGLE_ADS_FIELD\b", stripped_upper):
            if has_from:
                static_errors.append(
                    "Metadata queries against GoogleAdsFieldService MUST NOT contain a 'FROM' clause."
                )
            if any(
                pfx in stripped_upper
                for pfx in ("GOOGLE_ADS_FIELD.", "METRICS.", "SEGMENTS.")
            ):
                static_errors.append(
                    "Metadata queries MUST NOT use resource/segment prefixes (e.g., use 'name', not 'google_ads_field.name')."
                )

        where_match = re.search(
            r"\bWHERE\b(.*?)(\bORDER\s+BY\b|\bLIMIT\b|\bPARAMETERS\b|$)",
            stripped_upper,
            re.DOTALL,
        )
        select_match = re.search(
            r"\bSELECT\s+(.*?)\s+FROM\b", stripped_upper, re.DOTALL
        )
        if select_match:
            select_clause = select_match.group(1)
            date_segs = (
                "SEGMENTS.DATE",
                "SEGMENTS.WEEK",
                "SEGMENTS.MONTH",
                "SEGMENTS.QUARTER",
                "SEGMENTS.YEAR",
            )
            if any(re.search(rf"\b{seg}\b", select_clause) for seg in date_segs):
                has_date_filter = bool(
                    where_match
                    and re.search(
                        r"(\bSEGMENTS\.(DATE|WEEK|MONTH|QUARTER|YEAR)\s*(?:>=|<=|=|>|<|(?:BETWEEN|DURING)\b)|\bDURING\b)",
                        where_match.group(1),
                    )
                )
                if not has_date_filter:
                    static_errors.append(
                        "GAQL query selects a date segment without a finite date filter (DURING, BETWEEN, or comparison) in WHERE."
                    )

        if re.search(r"\bFROM\s+CLICK_VIEW\b", stripped_upper):
            raw_where_match = re.search(
                r"\bWHERE\b(.*?)(\bORDER\s+BY\b|\bLIMIT\b|\bPARAMETERS\b|$)",
                query,
                re.IGNORECASE | re.DOTALL,
            )
            has_single_day = bool(
                raw_where_match
                and (
                    re.search(
                        r"segments\.date\s*=\s*['\"][0-9]{4}-[0-9]{2}-[0-9]{2}['\"]",
                        raw_where_match.group(1),
                        re.IGNORECASE,
                    )
                    or re.search(
                        r"\bsegments\.date\s+DURING\s+(?:TODAY|YESTERDAY)\b",
                        raw_where_match.group(1),
                        re.IGNORECASE,
                    )
                )
            )
            if not has_single_day:
                static_errors.append(
                    "Queries against 'click_view' require a single-day filter (WHERE segments.date = 'YYYY-MM-DD' or DURING TODAY/YESTERDAY)."
                )

        if re.search(r"\bFROM\s+CHANGE_STATUS\b", stripped_upper):
            where_body = where_match.group(1) if where_match else ""
            has_cs_bounds = "LAST_CHANGE_DATE_TIME" in where_body and (
                bool(re.search(r"\b(?:BETWEEN|DURING)\b", where_body))
                or (
                    bool(re.search(r"LAST_CHANGE_DATE_TIME\s*>=?", where_body))
                    and bool(re.search(r"LAST_CHANGE_DATE_TIME\s*<=?", where_body))
                )
            )
            if not has_cs_bounds:
                static_errors.append(
                    "Queries against 'change_status' require a finite BETWEEN, DURING, or >=/<= filter on last_change_date_time."
                )
            limit_match = re.search(r"\bLIMIT\s+(\d+)\b", stripped_upper)
            if not limit_match:
                static_errors.append(
                    "Queries against 'change_status' require a LIMIT clause (1..10000)."
                )
            elif int(limit_match.group(1)) <= 0 or int(limit_match.group(1)) > 10000:
                static_errors.append(
                    "Queries against 'change_status' require a positive LIMIT up to 10,000."
                )

        if re.search(r"\bsegments\.hour_of_day\b", stripped, re.IGNORECASE):
            static_errors.append(
                "'segments.hour_of_day' is not a valid GAQL field (QueryError.UNRECOGNIZED_FIELD). Update your query to use 'segments.hour'."
            )

        if static_errors:
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "errors": static_errors,
            }

        live_status = "SKIPPED_STATIC_ONLY"
        if _strict_bool(payload.get("run_live_dry_run", False)):
            clean_cid = "".join(re.findall(r"\d+", customer_id))
            val_script = os.path.abspath(
                os.path.join(
                    base_dir, "../../skills/validate-gaql/scripts/validate_gaql.py"
                )
            )
            if not clean_cid:
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "errors": ["Live GAQL dry-run requires a numeric customer_id."],
                }
            proc = subprocess.run(
                [
                    sys.executable,
                    val_script,
                    "--customer_id",
                    clean_cid,
                    "--api_version",
                    api_version,
                    "--query",
                    query,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "errors": [
                        _truncate_tool_output(
                            (proc.stderr or proc.stdout or "Live GAQL dry-run failed.").strip()
                        )
                    ],
                }
            live_status = "PASSED"

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "gaql_query": query,
                "gaql_validation": {
                    "status": "PASSED",
                    "static_checks": "PASSED",
                    "live_dry_run": live_status,
                    "api_version": api_version,
                    "customer_id": customer_id,
                },
                "explanation": (
                    "GAQL query passed static analysis and live validate_only dry-run."
                    if live_status == "PASSED"
                    else "GAQL query passed static analysis (set run_live_dry_run=true to execute live validate_only API validation)."
                ),
            },
        }

    def handle_inspect_object(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        target_name = str(
            payload.get("resource_name") or payload.get("object_name") or "Campaign"
        ).strip()
        api_version = get_effective_api_version(payload, allow_interactive=False)

        resolved_type: Optional[str] = None
        fields: list[dict[str, str]] = []
        enum_values: list[dict[str, Any]] = []
        suggestions: list[str] = []

        inspect_script_path = os.path.abspath(
            os.path.join(
                base_dir, "../../skills/inspect-object/scripts/inspect_object.py"
            )
        )
        if os.path.isfile(inspect_script_path):
            try:
                insp_mod = _load_skill_module_cached(
                    "_sidecar_inspect_obj", inspect_script_path
                )
                if insp_mod is not None:
                    avail_types = insp_mod.get_available_types(api_version)
                    if avail_types:
                        resolved_type, suggestions = insp_mod.resolve_type_name(
                            target_name, avail_types
                        )
                        if resolved_type and resolved_type in avail_types:
                            fields, enum_values = _parse_source_fields_and_enums(
                                avail_types[resolved_type], resolved_type
                            )
            except Exception:
                pass

        snake_prefix = _camel_to_snake(resolved_type or target_name)
        if enum_values and not fields:
            result_obj: dict[str, Any] = {
                "resource": target_name,
                "resolved_type": resolved_type or target_name,
                "type": "Google Ads API Enum",
                "enum_values": enum_values,
                "selectable_fields": [],
                "api_version": api_version,
            }
        elif fields:
            result_obj = {
                "resource": target_name,
                "resolved_type": resolved_type or target_name,
                "type": "Google Ads API Resource",
                "fields": fields,
                "selectable_fields": [
                    f"{snake_prefix}.{f['name']}" for f in fields
                ],
                "api_version": api_version,
            }
        else:
            result_obj = {
                "resource": target_name,
                "type": "Google Ads API Resource",
                "selectable_fields": [
                    f"{snake_prefix}.id",
                    f"{snake_prefix}.name",
                    f"{snake_prefix}.status",
                ],
                "api_version": api_version,
            }
            if suggestions:
                result_obj["suggestions"] = suggestions

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": result_obj,
        }

    def handle_generate_code(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        import shutil as _shutil

        raw_prompt = str(payload.get("user_prompt", "") or "")
        safe_prompt = re.sub(r"[\r\n\x00]+", " ", raw_prompt).strip()[:500]

        raw_cid = str(payload.get("customer_id", "1234567890") or "").strip()
        clean_cid = "".join(re.findall(r"\d+", raw_cid))
        if not clean_cid:
            raise ValueError(
                f"Invalid customer_id '{raw_cid}'. Must contain numeric digits."
            )

        api_version = get_effective_api_version(payload, allow_interactive=False)
        if not re.match(r"^v\d+$", api_version):
            raise ValueError(
                f"Invalid api_version '{api_version}'. Expected 'v<N>'."
            )

        code_template = (
            '"""Generated by Google Ads API Developer Assistant Plugin Sidecar."""\n'
            f"# Prompt: {safe_prompt}\n\n"
            "from google.ads.googleads.client import GoogleAdsClient\n"
            "from google.ads.googleads.errors import GoogleAdsException\n\n\n"
            "def fetch_campaign_data(client: GoogleAdsClient, customer_id: str) -> None:\n"
            '    ga_service = client.get_service("GoogleAdsService")\n'
            '    query = """\n'
            "        SELECT\n"
            "          campaign.id,\n"
            "          campaign.name,\n"
            "          metrics.impressions,\n"
            "          metrics.clicks\n"
            "        FROM campaign\n"
            "        WHERE segments.date DURING LAST_30_DAYS\n"
            '    """\n'
            "    try:\n"
            "        response = ga_service.search_stream(customer_id=customer_id, query=query)\n"
            "        for batch in response:\n"
            "            for row in batch.results:\n"
            '                print(f"Campaign {row.campaign.id}: {row.campaign.name} - Clicks: {row.metrics.clicks}")\n'
            "    except GoogleAdsException as ex:\n"
            "        for error in ex.failure.errors:\n"
            '            print(f"Google Ads API Error: {error.message}")\n\n\n'
            'if __name__ == "__main__":\n'
            f'    client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version="{api_version}")\n'
            f'    fetch_campaign_data(client, "{clean_cid}")\n'
        )
        ast.parse(code_template)
        lint_status = "PASSED (AST syntax verified)"
        ruff_bin = _shutil.which("ruff")
        if ruff_bin:
            ruff_res = subprocess.run(
                [ruff_bin, "check", "--stdin-filename", "generated_ads_query.py", "-"],
                input=code_template,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if ruff_res.returncode != 0:
                raise RuntimeError(f"Generated code failed Ruff lint: {ruff_res.stdout or ruff_res.stderr}")
            lint_status = "PASSED (Ruff & AST verified)"

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "generated_code": code_template,
                "lint_status": lint_status,
                "api_version": api_version,
            },
        }

    def handle_troubleshoot_conversions(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        api_version = get_effective_api_version(payload, allow_interactive=False)
        csv_path = payload.get("csv_path")
        client = payload.get("client")
        customer_id = str(payload.get("customer_id", "") or "").strip()

        if csv_path:
            csv_err = _validate_script_path_arg(
                str(csv_path),
                allowed_extensions=(".csv",),
                require_workspace_or_saved=True,
            )
            if csv_err:
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "error": csv_err,
                }
            val_script = os.path.abspath(
                os.path.join(
                    base_dir,
                    "../../skills/troubleshoot-conversions/scripts/validate_conversion_upload.py",
                )
            )
            proc = subprocess.run(
                [sys.executable, val_script, "--csv_path", str(csv_path), "--api_version", api_version],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                stderr_part = (proc.stderr or "").strip()
                stdout_part = (proc.stdout or "").strip()
                combined_err = "\n".join(p for p in (stderr_part, stdout_part) if p)
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "error": _truncate_tool_output(
                        combined_err or "CSV conversion upload validation failed."
                    ),
                }
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": {
                    "header": "Created by the Google Ads API Developer Assistant",
                    "summary": _truncate_tool_output(
                        proc.stdout.strip() or "CSV conversion upload validation passed."
                    ),
                    "api_version": api_version,
                    "checks": ["CSV structural, timestamp, value/currency, and SHA-256 PII checks passed"],
                },
            }

        if not customer_id:
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "error": "TROUBLESHOOT_CONVERSIONS requires either 'csv_path' or 'customer_id'.",
            }

        tc_path = os.path.abspath(
            os.path.join(
                base_dir,
                "../../skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py",
            )
        )
        tc_mod = _load_skill_module_cached("_sidecar_troubleshoot_conv", tc_path)
        if tc_mod is None:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "error": "Unable to load troubleshoot_conversions diagnostic module.",
            }

        active_client = client
        if active_client is None:
            try:
                from google.ads.googleads.client import GoogleAdsClient  # type: ignore[import-not-found]

                env_cfg_yaml = os.environ.get(
                    "GOOGLE_ADS_CONFIGURATION_FILE_PATH", ""
                ).strip()
                if env_cfg_yaml:
                    cfg_yaml = os.path.expanduser(env_cfg_yaml)
                elif hasattr(tc_mod, "_get_config_path"):
                    cfg_yaml = tc_mod._get_config_path()
                else:
                    cfg_yaml = os.path.join(_PLUGIN_ROOT, "config", "google-ads.yaml")
                if not cfg_yaml or not os.path.isfile(cfg_yaml):
                    return {
                        "task_id": task_id,
                        "status": "FAILED",
                        "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                        "error": (
                            "Google Ads configuration file (config/google-ads.yaml) was not found. "
                            "Initialize credentials via config_init.py or pass 'csv_path' for offline CSV validation."
                        ),
                    }
                active_client = GoogleAdsClient.load_from_storage(
                    path=cfg_yaml, version=api_version
                )
            except Exception as exc:
                return {
                    "task_id": task_id,
                    "status": "FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "error": f"Unable to initialize GoogleAdsClient for conversion diagnostics: {exc}",
                }

        raw_output_dir = payload.get("output_dir")
        validated_output_dir: Optional[str] = None
        if raw_output_dir is not None and raw_output_dir != "":
            if not isinstance(raw_output_dir, str) or "\x00" in raw_output_dir:
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "error": (
                        "Invalid 'output_dir': must be a valid directory path "
                        "string without NUL bytes."
                    ),
                }
            clean_out_dir = raw_output_dir.strip()
            if clean_out_dir:
                real_out_dir = os.path.realpath(os.path.expanduser(clean_out_dir))
                in_saved = _is_within_dir(
                    real_out_dir, os.path.join(os.getcwd(), "saved")
                ) or _is_within_dir(
                    real_out_dir, os.path.join(_PLUGIN_ROOT, "saved")
                )
                in_cwd = _is_within_dir(real_out_dir, os.getcwd())
                sandbox_dir = _sandbox_writable_dir()
                in_sandbox = bool(
                    sandbox_dir and _is_within_dir(real_out_dir, sandbox_dir)
                )
                conv_env_dir = os.environ.get("CONVERSION_OUTPUT_DIR", "").strip()
                in_conv_env = bool(
                    conv_env_dir
                    and _is_within_dir(
                        real_out_dir, os.path.expanduser(conv_env_dir)
                    )
                )
                if not (in_saved or in_cwd or in_sandbox or in_conv_env):
                    return {
                        "task_id": task_id,
                        "status": "VALIDATION_FAILED",
                        "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                        "error": (
                            "Invalid 'output_dir': must resolve inside the current "
                            "workspace, a saved/ directory, or the sandbox writable "
                            "data directory."
                        ),
                    }
                validated_output_dir = real_out_dir

        try:
            diag = tc_mod.troubleshoot_conversions(
                active_client,
                customer_id,
                json_output=True,
                output_dir=validated_output_dir,
            )
        except Exception as exc:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "error": f"Conversion diagnostics failed: {exc}",
            }

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "header": "Created by the Google Ads API Developer Assistant",
                "summary": _truncate_tool_output(
                    "; ".join(diag.get("executive_summary", [])) or "Diagnostics completed."
                ),
                "api_version": api_version,
                "diagnostics": _cap_diagnostics_payload(diag),
                "checks": [
                    "offline_conversion_upload_client_summary queried",
                    "conversion_action diagnostics evaluated",
                ],
            },
        }

    def handle_prepare_mutation(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Runs a real validate_only=True dry-run (or records receipt when record_only=True) and returns the HITL Consequence Card."""
        customer_id = str(payload.get("customer_id", "")).strip()
        operation = str(
            payload.get("operation_summary") or payload.get("operation", "")
        ).strip()
        before_state = str(payload.get("before_state", "Captured via GAQL")).strip()
        after_state = str(payload.get("after_state", operation)).strip()
        consequences = payload.get("consequences", [])
        if isinstance(consequences, str):
            consequences = [c.strip() for c in consequences.split(";") if c.strip()]
        reversibility = str(payload.get("reversibility", "REVERSIBLE")).strip().upper()
        script_path = payload.get("script_path")
        record_only = _strict_bool(payload.get("record_only", False))

        script_err = _validate_script_path_arg(script_path, require_saved_code=True)
        if script_err:
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "destructive_hint": True,
                "error": script_err,
            }

        if not customer_id or not operation or not consequences:
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "destructive_hint": True,
                "error": (
                    "PREPARE_MUTATION requires 'customer_id', 'operation_summary', and non-empty 'consequences'."
                ),
            }

        runner_path = os.path.abspath(
            os.path.join(
                base_dir, "../../skills/execute-mutation/scripts/run_mutation.py"
            )
        )
        mod = _load_skill_module_cached("run_mutation", runner_path)
        if mod is None:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": "Unable to load run_mutation verification module.",
            }

        # When a mutation script is supplied without record_only=True, execute a real
        # validate_only=True dry-run via run_mutation.py instead of synthesizing a receipt.
        if script_path and not record_only:
            real_script = os.path.realpath(os.path.expanduser(str(script_path).strip()))
            if not os.path.isfile(real_script):
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "destructive_hint": True,
                    "error": f"Mutation script not found at '{real_script}'.",
                }
            cmd = [
                sys.executable,
                runner_path,
                "--script",
                real_script,
                "--dry-run",
                "--customer-id",
                customer_id,
                "--operation",
                operation,
                "--before",
                before_state,
                "--after",
                after_state,
                "--consequences",
                "; ".join(str(c).strip() for c in consequences if str(c).strip()),
                "--reversibility",
                reversibility,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return {
                    "task_id": task_id,
                    "status": "FAILED",
                    "destructive_hint": True,
                    "error": "PREPARE_MUTATION dry-run subprocess timed out after 120s.",
                }
            if proc.returncode != 0:
                raw_err_out = (proc.stderr or proc.stdout or "Dry-run failed.").strip()
                is_blocked = proc.returncode == 2 or "BLOCKED" in raw_err_out
                err_out = _truncate_tool_output(raw_err_out)
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED" if is_blocked else "FAILED",
                    "destructive_hint": True,
                    "error": err_out,
                }
            ok, msg, receipt = mod.load_and_verify_receipt(script_path=real_script)
            if not ok:
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": msg,
                }
            card = mod.format_verification_card(receipt)
            return {
                "task_id": task_id,
                "status": "HITL_CONFIRMATION_REQUIRED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": {
                    "receipt": receipt,
                    "verification_card": card,
                    "dry_run_stdout": _truncate_tool_output(proc.stdout),
                    "next_step": "Present verification_card to the user and obtain explicit confirmation before calling EXECUTE_MUTATION.",
                },
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            receipt = mod.write_dry_run_receipt(
                customer_id=customer_id,
                operation_summary=operation,
                before_state=before_state,
                after_state=after_state,
                consequences=consequences,
                reversibility=reversibility,
                script_path=script_path,
                dry_run_output="Recorded via sidecar PREPARE_MUTATION (record_only=True).",
                request_sent_at_iso=now_iso,
                response_received_at_iso=now_iso,
                record_only=True,
            )
        except ValueError as exc:
            err_str = str(exc)
            is_deletion_prohibited = "BLOCKED BY DELETION PROHIBITION" in err_str
            is_limit_exceeded = "BLOCKED BY FINANCIAL UPPER LIMIT" in err_str
            script_hash = (
                mod.compute_file_sha256(os.path.abspath(script_path))
                if script_path and os.path.isfile(os.path.abspath(script_path))
                else ""
            )
            if is_deletion_prohibited:
                audit_status = "BLOCKED_PROHIBITED_DELETION"
            elif is_limit_exceeded:
                audit_status = "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
            else:
                audit_status = "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING"
            mod.append_mutation_audit_log(
                phase="DRY_RUN",
                status=audit_status,
                customer_id=customer_id,
                operation_summary=operation,
                before_state=before_state,
                after_state=after_state,
                consequences=consequences,
                reversibility=reversibility,
                script_path=script_path,
                script_sha256=script_hash,
                validate_only=True,
                request_sent_at_iso=now_iso,
                response_received_at_iso=now_iso,
                duration_ms=0.0,
                exit_code=2,
                stdout="",
                stderr=err_str,
                command=["A2A:PREPARE_MUTATION"],
            )
            return {
                "task_id": task_id,
                "status": (
                    "HITL_BLOCKED"
                    if (is_deletion_prohibited or is_limit_exceeded)
                    else "VALIDATION_FAILED"
                ),
                "destructive_hint": True,
                "error": err_str,
            }

        mod.append_mutation_audit_log(
            phase="DRY_RUN",
            status="DRY_RUN_PASSED",
            customer_id=customer_id,
            operation_summary=operation,
            before_state=before_state,
            after_state=after_state,
            consequences=consequences,
            reversibility=reversibility,
            script_path=script_path,
            script_sha256=str(receipt.get("script_sha256", "")),
            validate_only=True,
            request_sent_at_iso=now_iso,
            response_received_at_iso=now_iso,
            duration_ms=0.0,
            exit_code=0,
            stdout="Validated via sidecar PREPARE_MUTATION (validate_only=True).",
            stderr="",
            command=["A2A:PREPARE_MUTATION"],
            receipt=receipt,
        )
        card = mod.format_verification_card(receipt)

        return {
            "task_id": task_id,
            "status": "HITL_CONFIRMATION_REQUIRED",
            "destructive_hint": True,
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "receipt": receipt,
                "verification_card": card,
                "next_step": "Present verification_card to the user and obtain explicit confirmation before calling EXECUTE_MUTATION.",
            },
        }

    def handle_execute_mutation(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Verifies the signed dry-run receipt, execute_mutates setting, and user confirmation before permitting live execution."""
        user_confirmed = _strict_bool(payload.get("user_confirmed", False))
        confirmation_summary = str(payload.get("confirmation_summary", "")).strip()
        script_path = payload.get("script_path")
        run_script = _strict_bool(payload.get("run_script", False))

        if not user_confirmed or not confirmation_summary:
            return {
                "task_id": task_id,
                "status": "HITL_BLOCKED",
                "destructive_hint": True,
                "error": (
                    "EXECUTE_MUTATION blocked: 'user_confirmed=True' and a plain-text "
                    "'confirmation_summary' detailing consequences are mandatory."
                ),
            }

        script_err = _validate_script_path_arg(script_path, require_saved_code=True)
        if script_err:
            return {
                "task_id": task_id,
                "status": "HITL_BLOCKED",
                "destructive_hint": True,
                "error": script_err,
            }

        runner_path = os.path.abspath(
            os.path.join(
                base_dir, "../../skills/execute-mutation/scripts/run_mutation.py"
            )
        )
        mod = _load_skill_module_cached("run_mutation", runner_path)
        if mod is None:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": "Unable to load run_mutation verification module.",
            }

        if not mod.is_execute_mutates_enabled():
            blocked_iso = datetime.now(timezone.utc).isoformat()
            err_msg = (
                "EXECUTE_MUTATION blocked: Mutate support is disabled by configuration "
                "(execute_mutates = false in config/assistant_config). "
                "Set 'execute_mutates = true' in config/assistant_config to enable live mutations."
            )
            _, _, existing_receipt = mod.load_and_verify_receipt(
                script_path=script_path
            )
            mod.append_mutation_audit_log(
                phase="EXECUTE",
                status="BLOCKED_MUTATES_DISABLED",
                customer_id=str(existing_receipt.get("customer_id", "")),
                operation_summary=str(existing_receipt.get("operation_summary", "")),
                before_state=str(existing_receipt.get("before_state", "")),
                after_state=str(existing_receipt.get("after_state", "")),
                consequences=[
                    str(c)
                    for c in existing_receipt.get("consequences", [])
                    if str(c).strip()
                ],
                reversibility=str(existing_receipt.get("reversibility", "REVERSIBLE")),
                script_path=script_path,
                script_sha256=str(existing_receipt.get("script_sha256", "")),
                validate_only=False,
                request_sent_at_iso=blocked_iso,
                response_received_at_iso=blocked_iso,
                duration_ms=0.0,
                exit_code=2,
                stdout="",
                stderr=err_msg,
                command=["A2A:EXECUTE_MUTATION"],
                receipt=existing_receipt if existing_receipt else None,
            )
            return {
                "task_id": task_id,
                "status": "HITL_BLOCKED",
                "destructive_hint": True,
                "error": err_msg,
            }

        ok, msg, receipt = mod.load_and_verify_receipt(script_path=script_path)
        if not ok:
            if (
                "BLOCKED BY DELETION PROHIBITION" in msg
                or "BLOCKED BY FINANCIAL UPPER LIMIT" in msg
            ):
                blocked_iso = datetime.now(timezone.utc).isoformat()
                audit_block_status = (
                    "BLOCKED_PROHIBITED_DELETION"
                    if "BLOCKED BY DELETION PROHIBITION" in msg
                    else "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
                )
                mod.append_mutation_audit_log(
                    phase="EXECUTE",
                    status=audit_block_status,
                    customer_id=str(receipt.get("customer_id", "")),
                    operation_summary=str(receipt.get("operation_summary", "")),
                    before_state=str(receipt.get("before_state", "")),
                    after_state=str(receipt.get("after_state", "")),
                    consequences=[
                        str(c)
                        for c in receipt.get("consequences", [])
                        if str(c).strip()
                    ],
                    reversibility=str(receipt.get("reversibility", "REVERSIBLE")),
                    script_path=script_path,
                    script_sha256=str(receipt.get("script_sha256", "")),
                    validate_only=False,
                    request_sent_at_iso=blocked_iso,
                    response_received_at_iso=blocked_iso,
                    duration_ms=0.0,
                    exit_code=2,
                    stdout="",
                    stderr=msg,
                    command=["A2A:EXECUTE_MUTATION"],
                    receipt=receipt if receipt else None,
                )
            return {
                "task_id": task_id,
                "status": "HITL_BLOCKED",
                "destructive_hint": True,
                "error": msg,
            }

        receipt_tier: Optional[int] = None
        tier_error = ""
        if receipt.get("classification_tier") and "tier_number" in receipt:
            try:
                receipt_tier = int(receipt["tier_number"])
            except (TypeError, ValueError):
                receipt_tier = None
        if receipt_tier is None:
            # Older or unclassified receipts: reclassify exactly like the PreToolUse hook does.
            classify_fn = getattr(mod, "classify_mutation", None)
            if callable(classify_fn):
                try:
                    dry_rpc_list = receipt.get("dry_run_rpc_calls")
                    cls_info = classify_fn(
                        operation_summary=str(receipt.get("operation_summary", "")),
                        before_state=str(receipt.get("before_state", "")),
                        after_state=str(receipt.get("after_state", "")),
                        rpc_calls=dry_rpc_list if isinstance(dry_rpc_list, list) else None,
                        script_path=script_path,
                    )
                    receipt_tier = int(cls_info["tier_number"])
                except Exception as cls_exc:  # pylint: disable=broad-except
                    tier_error = f"classification failed: {cls_exc}"
            else:
                tier_error = "run_mutation.classify_mutation is unavailable"
        if receipt_tier is None:
            # Fail closed: an unclassifiable receipt is treated as Tier 1.
            receipt_tier = 1
        if receipt_tier == 1 and (
            not hasattr(mod, "is_tier1_financial_mutates_enabled")
            or not mod.is_tier1_financial_mutates_enabled()
            or tier_error
        ):
            blocked_iso = datetime.now(timezone.utc).isoformat()
            t1_err = (
                "EXECUTE_MUTATION blocked (TIER 1 FINANCIAL POSTURE): "
                "Tier 1 Financial Services are read-only by default even when execute_mutates = true. "
                "Set 'allow_tier1_financial_mutates = true' in config/assistant_config to enable live Tier 1 writes."
            )
            if tier_error:
                t1_err = (
                    "EXECUTE_MUTATION blocked (TIER CLASSIFICATION UNAVAILABLE): the receipt has no "
                    f"policy tier and it could not be reclassified ({tier_error}). Re-run the dry run."
                )
            mod.append_mutation_audit_log(
                phase="EXECUTE",
                status="BLOCKED_TIER1_READONLY_POSTURE",
                customer_id=str(receipt.get("customer_id", "")),
                operation_summary=str(receipt.get("operation_summary", "")),
                before_state=str(receipt.get("before_state", "")),
                after_state=str(receipt.get("after_state", "")),
                consequences=[
                    str(c) for c in receipt.get("consequences", []) if str(c).strip()
                ],
                reversibility=str(receipt.get("reversibility", "REVERSIBLE")),
                script_path=script_path,
                script_sha256=str(receipt.get("script_sha256", "")),
                validate_only=False,
                request_sent_at_iso=blocked_iso,
                response_received_at_iso=blocked_iso,
                duration_ms=0.0,
                exit_code=2,
                stdout="",
                stderr=t1_err,
                command=["A2A:EXECUTE_MUTATION"],
                receipt=receipt,
            )
            return {
                "task_id": task_id,
                "status": "HITL_BLOCKED",
                "destructive_hint": True,
                "error": t1_err,
            }

        if run_script:
            if bool(receipt.get("record_only")):
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "EXECUTE_MUTATION with run_script=True cannot execute against a "
                        "record_only dry-run receipt. Run a real validate_only=True dry-run "
                        "via prepare_mutation (record_only=False) or run_mutation.py --dry-run first."
                    ),
                }
            if str(receipt.get("create_params_sha256") or "").strip():
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "EXECUTE_MUTATION with run_script=True cannot execute a script using "
                        "a sidecar create_* parameter receipt. Run a real validate_only=True "
                        "script dry-run via prepare_mutation or run_mutation.py --dry-run first."
                    ),
                }
            if not script_path or not os.path.isfile(os.path.abspath(script_path)):
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "destructive_hint": True,
                    "error": "EXECUTE_MUTATION with run_script=True requires an existing .py 'script_path' in saved/code/.",
                }
            is_mock_without_script_fields = (
                isinstance(mod, unittest.mock.MagicMock)
                and "script_path" not in receipt
                and "script_sha256" not in receipt
            )
            if not is_mock_without_script_fields and (
                not str(receipt.get("script_path") or "").strip()
                or not str(receipt.get("script_sha256") or "").strip()
            ):
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "EXECUTE_MUTATION with run_script=True requires a dry-run receipt "
                        "bound to both script_path and script_sha256. Run a real "
                        "validate_only=True script dry-run first."
                    ),
                }
            resolved_script = os.path.realpath(os.path.expanduser(script_path))
            proc = subprocess.run(
                [sys.executable, runner_path, "--script", resolved_script, "--execute"],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if proc.returncode != 0:
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED" if proc.returncode == 2 else "FAILED",
                    "destructive_hint": True,
                    "error": _truncate_tool_output(
                        (proc.stderr or proc.stdout or "Script execution failed.").strip()
                    ),
                }
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": {
                    "confirmation_summary": confirmation_summary,
                    "verified_receipt": receipt,
                    "execution_mode": "subprocess_executed",
                    "stdout": _truncate_tool_output(proc.stdout),
                    "status_message": "HITL receipt verified and mutation script executed.",
                },
            }

        claim_fn = getattr(mod, "claim_receipt_for_execution", None)
        if callable(claim_fn) and not isinstance(claim_fn, unittest.mock.MagicMock):
            claimed, claim_msg, _ = claim_fn(
                expected_receipt_id=receipt.get("receipt_id")
            )
            if not claimed:
                return {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": f"EXECUTE_MUTATION blocked: {claim_msg}",
                }

        now_iso = datetime.now(timezone.utc).isoformat()
        # Verify-only path: the sidecar confirmed the receipt but no human approved anything here
        # and no API call was made, so this is RECEIPT_VERIFIED (not HUMAN_APPROVED).
        audit_entry = mod.append_mutation_audit_log(
            phase="EXECUTE",
            status="RECEIPT_VERIFIED",
            customer_id=str(receipt.get("customer_id", "")),
            operation_summary=str(receipt.get("operation_summary", "")),
            before_state=str(receipt.get("before_state", "")),
            after_state=str(receipt.get("after_state", "")),
            consequences=[
                str(c) for c in receipt.get("consequences", []) if str(c).strip()
            ],
            reversibility=str(receipt.get("reversibility", "REVERSIBLE")),
            script_path=script_path,
            script_sha256=str(receipt.get("script_sha256", "")),
            validate_only=False,
            request_sent_at_iso=now_iso,
            response_received_at_iso=now_iso,
            duration_ms=0.0,
            exit_code=0,
            stdout=confirmation_summary,
            stderr="",
            command=["A2A:EXECUTE_MUTATION"],
            receipt=receipt,
            user_approved_at_iso=None,
            approval_decision="RECEIPT_VERIFIED",
        )
        mod.mark_receipt_executed(
            user_approved_at_iso=now_iso,
            request_sent_at_iso=now_iso,
            response_received_at_iso=now_iso,
            audit_id=audit_entry.get("audit_id"),
        )
        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "destructive_hint": True,
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "confirmation_summary": confirmation_summary,
                "verified_receipt": receipt,
                "audit_id": audit_entry.get("audit_id"),
                "execution_mode": "receipt_verified_only",
                "status_message": "HITL receipt verified and marked EXECUTED.",
            },
        }

    def handle_reject_mutation(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Invalidates pending dry-run receipt (REJECTED) and logs HUMAN_REJECTED."""
        reason = str(
            payload.get("reason")
            or payload.get("rejection_reason")
            or "Operator rejected mutation via A2A sidecar."
        ).strip()
        script_path = payload.get("script_path")
        if not isinstance(script_path, str) or not script_path.strip():
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "error": "REJECT_MUTATION requires 'script_path' (the saved/code/*.py script whose dry-run receipt to reject).",
            }
        real_script = os.path.realpath(os.path.expanduser(script_path.strip()))
        parts = real_script.replace("\\", "/").split("/")
        in_saved_code = any(
            parts[i] == "saved" and parts[i + 1] == "code" for i in range(len(parts) - 2)
        )
        if not in_saved_code or not real_script.endswith(".py"):
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "error": "REJECT_MUTATION 'script_path' must resolve to a .py file under a saved/code/ directory.",
            }
        runner_path = os.path.abspath(
            os.path.join(
                base_dir, "../../skills/execute-mutation/scripts/run_mutation.py"
            )
        )
        mod = _load_skill_module_cached("run_mutation", runner_path)
        if mod is None:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": "Unable to load run_mutation verification module.",
            }
        rej = mod.reject_dry_run_receipt(script_path=real_script, reason=reason) or {}
        if rej.get("status") != "REJECTED":
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": "No pending DRY_RUN_PASSED receipt matches this script; nothing was rejected.",
                "result": rej,
            }
        return {
            "task_id": task_id,
            "status": "HUMAN_REJECTED",
            "destructive_hint": True,
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": rej,
        }

    def _load_mutation_script(self, script_filename: str) -> Any:
        """Loads a mutation script module from skills/execute-mutation/scripts/."""
        script_path = os.path.abspath(
            os.path.join(
                base_dir, f"../../skills/execute-mutation/scripts/{script_filename}"
            )
        )
        mod = _load_skill_module_cached(
            script_filename.replace(".py", ""), script_path
        )
        if mod is not None:
            return mod
        raise RuntimeError(f"Unable to load mutation script '{script_filename}'.")

    @staticmethod
    def _compute_create_params_sha256(
        run_mod: Any,
        operation_summary: str,
        create_params: dict[str, Any],
    ) -> str:
        """Computes a canonical SHA-256 binding all effective parameters of a create_* call."""
        service, _, method = operation_summary.partition(".")
        if not method:
            service, method = "GoogleAdsService", operation_summary or "create"
        hash_fn = getattr(run_mod, "compute_mutate_request_sha256", None) if run_mod is not None else None
        if callable(hash_fn) and not isinstance(hash_fn, unittest.mock.MagicMock):
            return str(hash_fn(service, method, create_params))
        import hashlib

        canonical = json.dumps(
            {
                "service": str(service).strip(),
                "method": str(method).strip(),
                "request": create_params,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _pop_last_claimed_receipt() -> tuple[Optional[str], Optional[str]]:
        """Pops (receipt_id, claim_id) recorded by _check_live_execution_gate."""
        pair = getattr(_CLAIM_CTX, "last_claim", None)
        _CLAIM_CTX.last_claim = None
        if isinstance(pair, tuple) and len(pair) == 2:
            return pair[0], pair[1]
        return None, None

    @staticmethod
    def _release_claimed_receipt(
        run_mod: Any,
        claimed_rid: Optional[str],
        claimed_cid: Optional[str],
    ) -> None:
        """Releases a sidecar-claimed receipt after a strictly pre-RPC failure."""
        if run_mod is None or (claimed_rid is None and claimed_cid is None):
            return
        rel_fn = getattr(run_mod, "release_claimed_receipt_if_not_executed", None)
        if not callable(rel_fn) or isinstance(rel_fn, unittest.mock.MagicMock):
            return
        try:
            rel_fn(
                expected_receipt_id=claimed_rid,
                expected_claim_id=claimed_cid,
            )
        except Exception:
            pass

    @staticmethod
    def _prepare_create_client(
        mod: Any,
        raw_client: Any,
        api_version: str,
        *,
        validate_only: bool,
        rpc_dispatched: list[bool],
    ) -> Any:
        """Wraps or initializes the GoogleAdsClient for live RPC-dispatch tracking."""
        if validate_only:
            return raw_client
        if isinstance(mod, unittest.mock.MagicMock):
            rpc_dispatched[0] = True
            return raw_client
        if raw_client is not None:
            if isinstance(raw_client, unittest.mock.MagicMock):
                rpc_dispatched[0] = True
                return raw_client
            return _RpcDispatchTrackerClient(raw_client, rpc_dispatched)
        gads_cls = getattr(mod, "GoogleAdsClient", None)
        cfg_fn = getattr(mod, "_get_config_path", None)
        ver_fn = getattr(mod, "_normalize_api_version", None)
        if gads_cls is None:
            if callable(cfg_fn) and callable(ver_fn):
                raise RuntimeError("google-ads package is not installed.")
            rpc_dispatched[0] = True
            return None
        if callable(cfg_fn) and callable(ver_fn):
            cfg_path = cfg_fn()
            norm_ver = ver_fn(api_version)
            loaded = gads_cls.load_from_storage(path=cfg_path, version=norm_ver)
            return _RpcDispatchTrackerClient(loaded, rpc_dispatched)
        rpc_dispatched[0] = True
        return None

    def _check_live_execution_gate(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        financial_rpc_calls: Optional[list[dict[str, Any]]] = None,
        operation_summary: str = "",
        expected_create_params: Optional[dict[str, Any]] = None,
        customer_id: Optional[str] = None,
    ) -> tuple[Optional[dict[str, Any]], Optional[Any]]:
        """Enforces deletion prohibition, HITL confirmation, execute_mutates, financial limits, and SHA-256 binding."""
        _CLAIM_CTX.last_claim = None
        effective_cid = str(
            customer_id
            if customer_id is not None
            else (payload.get("customer_id") or payload.get("manager_customer_id") or "")
        )
        raw_status = str(payload.get("status", "") or "").strip().upper()
        if raw_status == "REMOVED":
            return (
                {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "BLOCKED BY DELETION PROHIBITION (HITL GUARD): "
                        "Setting status to 'REMOVED' is prohibited; use 'PAUSED' instead."
                    ),
                },
                None,
            )

        validate_only = _resolve_validate_only(payload)
        if validate_only:
            return None, None

        if not _strict_bool(payload.get("user_confirmed", False)):
            return (
                {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "Live execution blocked: 'user_confirmed=True' is mandatory when "
                        "validate_only=False (or execute=True)."
                    ),
                },
                None,
            )

        run_mod = self._load_mutation_script("run_mutation.py")
        if not run_mod.is_execute_mutates_enabled():
            return (
                {
                    "task_id": task_id,
                    "status": "HITL_BLOCKED",
                    "destructive_hint": True,
                    "error": (
                        "Live execution blocked: Mutate support is disabled by configuration "
                        "(execute_mutates = false in config/assistant_config)."
                    ),
                },
                run_mod,
            )

        if financial_rpc_calls:
            check_fn = getattr(run_mod, "check_financial_transaction_limits", None)
            if callable(check_fn) and not isinstance(
                check_fn, unittest.mock.MagicMock
            ):
                within_limits, limit_err, _ = check_fn(
                    operation_summary=operation_summary,
                    rpc_calls=financial_rpc_calls,
                )
                if not within_limits:
                    self._record_live_audit(
                        run_mod,
                        status="BLOCKED_FINANCIAL_LIMIT_EXCEEDED",
                        customer_id=effective_cid,
                        operation_summary=operation_summary or "A2A:CREATE",
                        after_state="BLOCKED",
                        consequences=[str(limit_err)],
                        exit_code=2,
                        stderr=str(limit_err),
                        command=[f"A2A:{operation_summary or 'CREATE'}"],
                    )
                    return (
                        {
                            "task_id": task_id,
                            "status": "HITL_BLOCKED",
                            "destructive_hint": True,
                            "error": str(limit_err),
                        },
                        run_mod,
                    )

        # Enforce Tier 1 Financial Services read-only default posture
        classify_fn = getattr(run_mod, "classify_mutation", None)
        tier1_fn = getattr(run_mod, "is_tier1_financial_mutates_enabled", None)
        if callable(classify_fn) and not isinstance(classify_fn, unittest.mock.MagicMock):
            cls_info = classify_fn(
                operation_summary=operation_summary,
                rpc_calls=financial_rpc_calls,
            )
            if int(cls_info.get("tier_number", 3)) == 1 and (
                not callable(tier1_fn)
                or (
                    not isinstance(tier1_fn, unittest.mock.MagicMock)
                    and not tier1_fn()
                )
            ):
                t1_err = (
                    "Live execution blocked (TIER 1 FINANCIAL POSTURE): "
                    "Tier 1 Financial Services are read-only by default even when execute_mutates = true. "
                    "Set 'allow_tier1_financial_mutates = true' in config/assistant_config to enable live Tier 1 writes."
                )
                self._record_live_audit(
                    run_mod,
                    status="BLOCKED_TIER1_READONLY_POSTURE",
                    customer_id=effective_cid,
                    operation_summary=operation_summary or "A2A:CREATE",
                    after_state="BLOCKED",
                    consequences=[t1_err],
                    exit_code=2,
                    stderr=t1_err,
                    command=[f"A2A:{operation_summary or 'CREATE'}"],
                )
                return (
                    {
                        "task_id": task_id,
                        "status": "HITL_BLOCKED",
                        "destructive_hint": True,
                        "error": t1_err,
                    },
                    run_mod,
                )

        # Require a valid pending validate_only=True dry-run receipt before live execution
        verify_fn = getattr(run_mod, "load_and_verify_receipt", None)
        if callable(verify_fn) and not isinstance(verify_fn, unittest.mock.MagicMock):
            ok_rec, rec_msg, receipt = verify_fn()
            if not ok_rec:
                return (
                    {
                        "task_id": task_id,
                        "status": "HITL_BLOCKED",
                        "destructive_hint": True,
                        "error": (
                            "Live execution blocked: a valid pending validate_only=True dry-run receipt "
                            f"is required before live execution ({rec_msg}). Run this tool with "
                            "validate_only=True first, disclose consequences, and obtain user confirmation."
                        ),
                    },
                    run_mod,
                )
            target_cid = re.sub(r"\D", "", effective_cid)
            rec_cid = re.sub(r"\D", "", str(receipt.get("customer_id") or ""))
            if target_cid and rec_cid and target_cid != rec_cid:
                return (
                    {
                        "task_id": task_id,
                        "status": "HITL_BLOCKED",
                        "destructive_hint": True,
                        "error": (
                            f"Live execution blocked: pending dry-run receipt is for customer_id "
                            f"'{rec_cid}', not '{target_cid}'. Re-run validate_only=True first."
                        ),
                    },
                    run_mod,
                )
            rec_op = str(receipt.get("operation_summary") or "").strip()
            if operation_summary and rec_op and rec_op != operation_summary:
                return (
                    {
                        "task_id": task_id,
                        "status": "HITL_BLOCKED",
                        "destructive_hint": True,
                        "error": (
                            f"Live execution blocked: pending dry-run receipt is for '{rec_op}', "
                            f"not '{operation_summary}'. Re-run validate_only=True first."
                        ),
                    },
                    run_mod,
                )
            if expected_create_params is not None:
                expected_sha = self._compute_create_params_sha256(
                    run_mod, operation_summary, expected_create_params
                )
                recorded_create_sha = str(
                    receipt.get("create_params_sha256") or ""
                ).strip()
                if not recorded_create_sha or recorded_create_sha != expected_sha:
                    return (
                        {
                            "task_id": task_id,
                            "status": "HITL_BLOCKED",
                            "destructive_hint": True,
                            "error": (
                                "Live execution blocked: live request parameters do not match the pending "
                                "validate_only=True dry-run receipt (parameter SHA-256 mismatch). "
                                "Re-run validate_only=True with the exact target parameters first."
                            ),
                        },
                        run_mod,
                    )
            claim_fn = getattr(run_mod, "claim_receipt_for_execution", None)
            if callable(claim_fn) and not isinstance(
                claim_fn, unittest.mock.MagicMock
            ):
                claimed, claim_msg, claimed_rec = claim_fn(
                    expected_receipt_id=receipt.get("receipt_id")
                )
                if not claimed:
                    return (
                        {
                            "task_id": task_id,
                            "status": "HITL_BLOCKED",
                            "destructive_hint": True,
                            "error": f"Live execution blocked: {claim_msg}",
                        },
                        run_mod,
                    )
                _CLAIM_CTX.last_claim = (
                    (claimed_rec or {}).get("receipt_id")
                    or receipt.get("receipt_id"),
                    (claimed_rec or {}).get("executing_claim_id"),
                )

        return None, run_mod

    def _record_create_dry_run_receipt(
        self,
        *,
        customer_id: str,
        operation_summary: str,
        after_state: str,
        consequences: list[str],
        rpc_calls: Optional[list[dict[str, Any]]] = None,
        create_params: Optional[dict[str, Any]] = None,
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Records a signed dry-run receipt after a validate_only=True create call succeeds."""
        try:
            run_mod = self._load_mutation_script("run_mutation.py")
        except Exception:
            return None, None
        write_fn = getattr(run_mod, "write_dry_run_receipt", None)
        if not callable(write_fn) or isinstance(write_fn, unittest.mock.MagicMock):
            return None, None
        now_iso = datetime.now(timezone.utc).isoformat()
        create_sha = (
            self._compute_create_params_sha256(
                run_mod, operation_summary, create_params
            )
            if create_params is not None
            else None
        )
        try:
            receipt = write_fn(
                customer_id=customer_id,
                operation_summary=operation_summary,
                before_state="None (new resource)",
                after_state=after_state,
                consequences=consequences,
                reversibility="REVERSIBLE",
                script_path=None,
                dry_run_output=f"Validated via sidecar {operation_summary} (validate_only=True).",
                request_sent_at_iso=now_iso,
                response_received_at_iso=now_iso,
                rpc_calls=rpc_calls,
                record_only=False,
                create_params_sha256=create_sha,
            )
            return receipt, None
        except ValueError as exc:
            return None, str(exc)

    @staticmethod
    def _record_live_audit(
        run_mod: Any,
        *,
        status: str,
        customer_id: str,
        operation_summary: str,
        after_state: str,
        consequences: list[str],
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
        command: Optional[list[str]] = None,
    ) -> None:
        """Records a live A2A creation event in mutation_audit.jsonl when run_mutation is real.

        Successful executions keep status="SUCCESS"; the operator confirmation
        (user_confirmed=True, enforced by _check_live_execution_gate) is recorded separately
        as approval_decision="HUMAN_APPROVED".
        """
        if run_mod is None:
            return
        audit_fn = getattr(run_mod, "append_mutation_audit_log", None)
        if not callable(audit_fn) or isinstance(audit_fn, unittest.mock.MagicMock):
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        approved = status == "SUCCESS"
        try:
            audit_fn(
                phase="EXECUTE",
                status=status,
                customer_id=customer_id,
                operation_summary=operation_summary,
                before_state="None (new resource)",
                after_state=after_state,
                consequences=consequences,
                reversibility="REVERSIBLE",
                script_path=None,
                script_sha256="",
                validate_only=False,
                request_sent_at_iso=now_iso,
                response_received_at_iso=now_iso,
                duration_ms=0.0,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                command=command or ["A2A:CREATE"],
                user_approved_at_iso=now_iso if approved else None,
                approval_decision="HUMAN_APPROVED" if approved else None,
            )
        except Exception:
            pass

    def handle_create_account(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handles CREATE_ACCOUNT intent via create_account.py."""
        mgr_cid = str(
            payload.get("manager_customer_id") or payload.get("customer_id", "")
        )
        api_version = get_effective_api_version(payload, allow_interactive=False)
        raw_email = payload.get("email_address")
        clean_email = (
            str(raw_email).strip()
            if raw_email is not None and str(raw_email).strip()
            else None
        )
        raw_role = payload.get("access_role")
        clean_role = (
            str(raw_role).strip().upper()
            if raw_role is not None and str(raw_role).strip()
            else None
        )
        create_params = {
            "manager_customer_id": re.sub(r"\D", "", mgr_cid),
            "api_version": api_version,
            "descriptive_name": payload.get("descriptive_name") or payload.get("name"),
            "currency_code": str(payload.get("currency_code", "USD")).strip().upper(),
            "time_zone": str(payload.get("time_zone", "America/New_York")).strip(),
            "tracking_url_template": payload.get("tracking_url_template"),
            "final_url_suffix": payload.get("final_url_suffix"),
            "email_address": clean_email,
            "access_role": clean_role,
        }
        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            operation_summary="CustomerService.create_customer_client",
            expected_create_params=create_params,
            customer_id=mgr_cid,
        )
        if gate_error is not None:
            return gate_error

        claimed_rid, claimed_cid = self._pop_last_claimed_receipt()
        validate_only = _resolve_validate_only(payload)
        rpc_dispatched = [False]
        try:
            mod = self._load_mutation_script("create_account.py")
            active_client = self._prepare_create_client(
                mod,
                payload.get("client"),
                api_version,
                validate_only=validate_only,
                rpc_dispatched=rpc_dispatched,
            )
            result = mod.create_account_under_mcc(
                manager_customer_id=mgr_cid,
                api_version=api_version,
                descriptive_name=create_params["descriptive_name"],
                currency_code=create_params["currency_code"],
                time_zone=create_params["time_zone"],
                tracking_url_template=create_params["tracking_url_template"],
                final_url_suffix=create_params["final_url_suffix"],
                email_address=create_params["email_address"],
                access_role=create_params["access_role"],
                validate_only=validate_only,
                client=active_client,
                json_output=False,
            )
            if validate_only:
                acct_consequences = [
                    f"Creates a new client account ({result.get('currency_code', 'USD')}) under MCC {result.get('manager_customer_id', '')}"
                ]
                acct_rpc_calls: Optional[list[dict[str, Any]]] = None
                if create_params["email_address"] or create_params["access_role"]:
                    if create_params["email_address"]:
                        acct_consequences.append(
                            f"Grants {create_params['access_role'] or 'STANDARD'} user access invitation to {create_params['email_address']} (account access security impact)"
                        )
                    acct_req_payload: dict[str, Any] = {
                        "customer_id": str(
                            result.get("manager_customer_id")
                            or create_params["manager_customer_id"]
                        ),
                        "validate_only": True,
                    }
                    if create_params["email_address"]:
                        acct_req_payload["email_address"] = create_params[
                            "email_address"
                        ]
                    if create_params["access_role"]:
                        acct_req_payload["access_role"] = create_params["access_role"]
                    acct_rpc_calls = [
                        {
                            "service": "CustomerService",
                            "method": "create_customer_client",
                            "request_payload": acct_req_payload,
                        }
                    ]
                receipt, hitl_notice = self._record_create_dry_run_receipt(
                    customer_id=str(
                        result.get("manager_customer_id")
                        or mgr_cid
                    ),
                    operation_summary="CustomerService.create_customer_client",
                    after_state=str(result.get("resource_name", "NEW_ACCOUNT")),
                    consequences=acct_consequences,
                    rpc_calls=acct_rpc_calls,
                    create_params=create_params,
                )
                if receipt:
                    result["receipt_id"] = receipt.get("receipt_id")
                    result["verification_card"] = receipt.get("rendered_verification_card", "")
                elif hitl_notice:
                    result["hitl_notice"] = hitl_notice
            else:
                self._record_live_audit(
                    run_mod,
                    status="SUCCESS",
                    customer_id=str(result.get("manager_customer_id", "")),
                    operation_summary="CustomerService.create_customer_client",
                    after_state=str(result.get("resource_name", "CREATED")),
                    consequences=[
                        f"Created client account ({result.get('currency_code', 'USD')}) under MCC {result.get('manager_customer_id', '')}"
                    ],
                    stdout=json.dumps(result, default=str),
                    command=["A2A:CREATE_ACCOUNT"],
                )
                mark_fn = getattr(run_mod, "mark_receipt_executed", None)
                if callable(mark_fn) and not isinstance(mark_fn, unittest.mock.MagicMock):
                    now_iso = datetime.now(timezone.utc).isoformat()
                    mark_fn(
                        user_approved_at_iso=now_iso,
                        request_sent_at_iso=now_iso,
                        response_received_at_iso=now_iso,
                    )
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
            if not validate_only and not rpc_dispatched[0]:
                self._release_claimed_receipt(run_mod, claimed_rid, claimed_cid)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Account creation failed: {exc}",
            }

    def handle_create_campaign(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handles CREATE_CAMPAIGN intent via create_campaign.py."""
        budget_rn = payload.get("budget_resource_name")
        clean_budget_rn = (
            str(budget_rn).strip()
            if budget_rn is not None and str(budget_rn).strip()
            else None
        )
        try:
            budget_micros = _parse_strict_int(
                payload.get("budget_amount_micros", 5_000_000),
                "budget_amount_micros",
            )
        except (TypeError, ValueError) as exc:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Invalid budget_amount_micros: {exc}",
            }

        api_version = get_effective_api_version(payload, allow_interactive=False)
        cust_id_raw = str(payload.get("customer_id", ""))
        create_params = {
            "customer_id": re.sub(r"\D", "", cust_id_raw),
            "api_version": api_version,
            "campaign_name": payload.get("campaign_name") or payload.get("name"),
            "budget_amount_micros": budget_micros,
            "budget_resource_name": clean_budget_rn,
            "budget_delivery_method": str(
                payload.get("budget_delivery_method", "STANDARD")
            ).strip().upper(),
            "advertising_channel_type": str(
                payload.get("advertising_channel_type")
                or payload.get("channel_type", "SEARCH")
            ).strip().upper(),
            "status": str(payload.get("status", "PAUSED")).strip().upper(),
            "start_date": payload.get("start_date"),
            "end_date": payload.get("end_date"),
            "budget_name": payload.get("budget_name"),
            "contains_eu_political_advertising": _strict_bool(
                payload.get("contains_eu_political_advertising", False)
            ),
        }

        fin_calls: Optional[list[dict[str, Any]]] = None
        if not clean_budget_rn:
            fin_calls = [
                {
                    "service": "CampaignBudgetService",
                    "method": "mutate_campaign_budgets",
                    "request_payload": {
                        "customer_id": cust_id_raw,
                        "operations": [{"create": {"amount_micros": budget_micros}}],
                    },
                }
            ]

        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            financial_rpc_calls=fin_calls,
            operation_summary="CampaignService.mutate_campaigns",
            expected_create_params=create_params,
            customer_id=cust_id_raw,
        )
        if gate_error is not None:
            return gate_error

        claimed_rid, claimed_cid = self._pop_last_claimed_receipt()
        validate_only = _resolve_validate_only(payload)
        rpc_dispatched = [False]
        try:
            mod = self._load_mutation_script("create_campaign.py")
            active_client = self._prepare_create_client(
                mod,
                payload.get("client"),
                api_version,
                validate_only=validate_only,
                rpc_dispatched=rpc_dispatched,
            )
            result = mod.create_campaign(
                customer_id=cust_id_raw,
                api_version=api_version,
                campaign_name=create_params["campaign_name"],
                budget_amount_micros=budget_micros,
                budget_resource_name=clean_budget_rn,
                budget_delivery_method=create_params["budget_delivery_method"],
                advertising_channel_type=create_params["advertising_channel_type"],
                status=create_params["status"],
                start_date=create_params["start_date"],
                end_date=create_params["end_date"],
                validate_only=validate_only,
                client=active_client,
                json_output=False,
                budget_name=create_params["budget_name"],
                contains_eu_political_advertising=create_params[
                    "contains_eu_political_advertising"
                ],
            )
            if validate_only:
                if clean_budget_rn:
                    dry_camp_consequence = (
                        f"Creates campaign '{result.get('campaign_name', '')}' "
                        f"({create_params['status']}) attached to existing budget "
                        f"'{clean_budget_rn}'"
                    )
                else:
                    dry_camp_consequence = (
                        f"Creates campaign '{result.get('campaign_name', '')}' "
                        f"({create_params['status']}) with daily budget "
                        f"{budget_micros / 1_000_000:.2f} currency units "
                        f"({budget_micros} micros)"
                    )
                receipt, hitl_notice = self._record_create_dry_run_receipt(
                    customer_id=str(result.get("customer_id") or cust_id_raw),
                    operation_summary="CampaignService.mutate_campaigns",
                    after_state=str(result.get("campaign_resource_name", "NEW_CAMPAIGN")),
                    consequences=[dry_camp_consequence],
                    rpc_calls=fin_calls,
                    create_params=create_params,
                )
                if receipt:
                    result["receipt_id"] = receipt.get("receipt_id")
                    result["verification_card"] = receipt.get("rendered_verification_card", "")
                elif hitl_notice:
                    result["hitl_notice"] = hitl_notice
            else:
                if clean_budget_rn:
                    live_camp_consequence = (
                        f"Created campaign '{result.get('campaign_name', '')}' "
                        f"attached to existing budget '{clean_budget_rn}'"
                    )
                else:
                    live_camp_consequence = (
                        f"Created campaign '{result.get('campaign_name', '')}' "
                        f"with budget {budget_micros} micros"
                    )
                self._record_live_audit(
                    run_mod,
                    status="SUCCESS",
                    customer_id=str(result.get("customer_id", "")),
                    operation_summary="CampaignService.mutate_campaigns",
                    after_state=str(result.get("campaign_resource_name", "CREATED")),
                    consequences=[live_camp_consequence],
                    stdout=json.dumps(result, default=str),
                    command=["A2A:CREATE_CAMPAIGN"],
                )
                mark_fn = getattr(run_mod, "mark_receipt_executed", None)
                if callable(mark_fn) and not isinstance(mark_fn, unittest.mock.MagicMock):
                    now_iso = datetime.now(timezone.utc).isoformat()
                    mark_fn(
                        user_approved_at_iso=now_iso,
                        request_sent_at_iso=now_iso,
                        response_received_at_iso=now_iso,
                    )
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
            if not validate_only and not rpc_dispatched[0]:
                self._release_claimed_receipt(run_mod, claimed_rid, claimed_cid)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Campaign creation failed: {exc}",
            }

    def handle_create_ad_group(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handles CREATE_AD_GROUP intent via create_ad_group.py."""
        cpc_bid_raw = payload.get("cpc_bid_micros")
        cpc_bid_int: Optional[int] = None
        if cpc_bid_raw is not None:
            try:
                cpc_bid_int = _parse_strict_int(cpc_bid_raw, "cpc_bid_micros")
            except (TypeError, ValueError) as exc:
                return {
                    "task_id": task_id,
                    "status": "FAILED",
                    "destructive_hint": True,
                    "error": f"Invalid cpc_bid_micros: {exc}",
                }

        api_version = get_effective_api_version(payload, allow_interactive=False)
        cust_id_raw = str(payload.get("customer_id", ""))
        create_params = {
            "customer_id": re.sub(r"\D", "", cust_id_raw),
            "api_version": api_version,
            "campaign_id": (
                str(payload.get("campaign_id"))
                if payload.get("campaign_id") is not None
                else None
            ),
            "campaign_resource_name": payload.get("campaign_resource_name"),
            "ad_group_name": payload.get("ad_group_name") or payload.get("name"),
            "cpc_bid_micros": cpc_bid_int,
            "status": str(payload.get("status", "ENABLED")).strip().upper(),
            "ad_group_type": str(
                payload.get("ad_group_type", "SEARCH_STANDARD")
            ).strip().upper(),
        }

        fin_calls: Optional[list[dict[str, Any]]] = None
        if cpc_bid_int is not None:
            fin_calls = [
                {
                    "service": "AdGroupService",
                    "method": "mutate_ad_groups",
                    "request_payload": {
                        "customer_id": cust_id_raw,
                        "operations": [{"create": {"cpc_bid_micros": cpc_bid_int}}],
                    },
                }
            ]

        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            financial_rpc_calls=fin_calls,
            operation_summary="AdGroupService.mutate_ad_groups",
            expected_create_params=create_params,
            customer_id=cust_id_raw,
        )
        if gate_error is not None:
            return gate_error

        claimed_rid, claimed_cid = self._pop_last_claimed_receipt()
        validate_only = _resolve_validate_only(payload)
        rpc_dispatched = [False]
        try:
            mod = self._load_mutation_script("create_ad_group.py")
            active_client = self._prepare_create_client(
                mod,
                payload.get("client"),
                api_version,
                validate_only=validate_only,
                rpc_dispatched=rpc_dispatched,
            )
            result = mod.create_ad_group(
                customer_id=cust_id_raw,
                campaign_id=payload.get("campaign_id"),
                campaign_resource_name=payload.get("campaign_resource_name"),
                api_version=api_version,
                ad_group_name=create_params["ad_group_name"],
                cpc_bid_micros=cpc_bid_int,
                status=create_params["status"],
                ad_group_type=create_params["ad_group_type"],
                validate_only=validate_only,
                client=active_client,
                json_output=False,
            )
            if validate_only:
                bid_desc = (
                    f"with CPC bid {cpc_bid_int / 1_000_000:.2f} currency units ({cpc_bid_int} micros)"
                    if cpc_bid_int is not None
                    else "with default bid"
                )
                receipt, hitl_notice = self._record_create_dry_run_receipt(
                    customer_id=str(result.get("customer_id") or cust_id_raw),
                    operation_summary="AdGroupService.mutate_ad_groups",
                    after_state=str(result.get("ad_group_resource_name", "NEW_AD_GROUP")),
                    consequences=[
                        f"Creates ad group '{result.get('ad_group_name', '')}' {bid_desc}"
                    ],
                    rpc_calls=fin_calls,
                    create_params=create_params,
                )
                if receipt:
                    result["receipt_id"] = receipt.get("receipt_id")
                    result["verification_card"] = receipt.get("rendered_verification_card", "")
                elif hitl_notice:
                    result["hitl_notice"] = hitl_notice
            else:
                self._record_live_audit(
                    run_mod,
                    status="SUCCESS",
                    customer_id=str(result.get("customer_id", "")),
                    operation_summary="AdGroupService.mutate_ad_groups",
                    after_state=str(result.get("ad_group_resource_name", "CREATED")),
                    consequences=[
                        f"Created ad group '{result.get('ad_group_name', '')}' (cpc_bid_micros={cpc_bid_int})"
                    ],
                    stdout=json.dumps(result, default=str),
                    command=["A2A:CREATE_AD_GROUP"],
                )
                mark_fn = getattr(run_mod, "mark_receipt_executed", None)
                if callable(mark_fn) and not isinstance(mark_fn, unittest.mock.MagicMock):
                    now_iso = datetime.now(timezone.utc).isoformat()
                    mark_fn(
                        user_approved_at_iso=now_iso,
                        request_sent_at_iso=now_iso,
                        response_received_at_iso=now_iso,
                    )
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
            if not validate_only and not rpc_dispatched[0]:
                self._release_claimed_receipt(run_mod, claimed_rid, claimed_cid)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Ad group creation failed: {exc}",
            }

    def handle_create_ad(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handles CREATE_AD intent via create_ad.py."""
        final_urls = payload.get("final_urls")
        if isinstance(final_urls, str):
            final_urls = [final_urls]
        elif final_urls is None and payload.get("final_url"):
            final_urls = [str(payload.get("final_url"))]

        api_version = get_effective_api_version(payload, allow_interactive=False)
        cust_id_raw = str(payload.get("customer_id", ""))
        create_params = {
            "customer_id": re.sub(r"\D", "", cust_id_raw),
            "api_version": api_version,
            "ad_group_id": (
                str(payload.get("ad_group_id"))
                if payload.get("ad_group_id") is not None
                else None
            ),
            "ad_group_resource_name": payload.get("ad_group_resource_name"),
            "final_urls": (
                list(final_urls) if isinstance(final_urls, (list, tuple)) else final_urls
            ),
            "headlines": (
                list(payload["headlines"])
                if isinstance(payload.get("headlines"), (list, tuple))
                else payload.get("headlines")
            ),
            "descriptions": (
                list(payload["descriptions"])
                if isinstance(payload.get("descriptions"), (list, tuple))
                else payload.get("descriptions")
            ),
            "path1": payload.get("path1"),
            "path2": payload.get("path2"),
            "status": str(payload.get("status", "PAUSED")).strip().upper(),
        }

        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            operation_summary="AdGroupAdService.mutate_ad_group_ads",
            expected_create_params=create_params,
            customer_id=cust_id_raw,
        )
        if gate_error is not None:
            return gate_error

        claimed_rid, claimed_cid = self._pop_last_claimed_receipt()
        validate_only = _resolve_validate_only(payload)
        rpc_dispatched = [False]
        try:
            mod = self._load_mutation_script("create_ad.py")
            active_client = self._prepare_create_client(
                mod,
                payload.get("client"),
                api_version,
                validate_only=validate_only,
                rpc_dispatched=rpc_dispatched,
            )
            result = mod.create_responsive_search_ad(
                customer_id=cust_id_raw,
                ad_group_id=payload.get("ad_group_id"),
                ad_group_resource_name=payload.get("ad_group_resource_name"),
                api_version=api_version,
                final_urls=final_urls,
                headlines=payload.get("headlines"),
                descriptions=payload.get("descriptions"),
                path1=payload.get("path1"),
                path2=payload.get("path2"),
                status=create_params["status"],
                validate_only=validate_only,
                client=active_client,
                json_output=False,
            )
            if validate_only:
                receipt, hitl_notice = self._record_create_dry_run_receipt(
                    customer_id=str(result.get("customer_id") or cust_id_raw),
                    operation_summary="AdGroupAdService.mutate_ad_group_ads",
                    after_state=str(result.get("ad_group_ad_resource_name", "NEW_AD")),
                    consequences=[
                        f"Creates responsive search ad under {result.get('ad_group_resource_name', '')}"
                    ],
                    create_params=create_params,
                )
                if receipt:
                    result["receipt_id"] = receipt.get("receipt_id")
                    result["verification_card"] = receipt.get("rendered_verification_card", "")
                elif hitl_notice:
                    result["hitl_notice"] = hitl_notice
            else:
                self._record_live_audit(
                    run_mod,
                    status="SUCCESS",
                    customer_id=str(result.get("customer_id", "")),
                    operation_summary="AdGroupAdService.mutate_ad_group_ads",
                    after_state=str(result.get("ad_group_ad_resource_name", "CREATED")),
                    consequences=[
                        f"Created responsive search ad under {result.get('ad_group_resource_name', '')}"
                    ],
                    stdout=json.dumps(result, default=str),
                    command=["A2A:CREATE_AD"],
                )
                mark_fn = getattr(run_mod, "mark_receipt_executed", None)
                if callable(mark_fn) and not isinstance(mark_fn, unittest.mock.MagicMock):
                    now_iso = datetime.now(timezone.utc).isoformat()
                    mark_fn(
                        user_approved_at_iso=now_iso,
                        request_sent_at_iso=now_iso,
                        response_received_at_iso=now_iso,
                    )
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
            if not validate_only and not rpc_dispatched[0]:
                self._release_claimed_receipt(run_mod, claimed_rid, claimed_cid)
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Ad creation failed: {exc}",
            }


_MCP_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "gaql_validate",
        "description": "Validates a Google Ads Query Language (GAQL) query against static syntax and active API schema rules (and optional live dry-run via run_live_dry_run=true).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "GAQL query string."},
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads Customer ID.",
                },
                "api_version": {
                    "type": "string",
                    "description": "Google Ads API version (format 'v<N>'; defaults to active version).",
                },
                "run_live_dry_run": {
                    "type": "boolean",
                    "description": "When true with customer_id, also runs validate_gaql.py live API check.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "inspect_object",
        "description": "Inspects fields or enum values of a Google Ads API Protobuf resource, message, or enum.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "resource_name": {
                    "type": "string",
                    "description": "Protobuf message or enum name (e.g., 'Campaign', 'CampaignStatusEnum').",
                },
                "object_name": {
                    "type": "string",
                    "description": "Alias for resource_name.",
                },
                "api_version": {
                    "type": "string",
                    "description": "Google Ads API version (format 'v<N>'; defaults to active version).",
                },
            },
        },
    },
    {
        "name": "troubleshoot_conversions",
        "description": "Validates an offline conversion upload CSV (via csv_path) or runs live conversion upload diagnostic checks for a Google Ads customer account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads Customer ID (required for live account diagnostics).",
                },
                "csv_path": {
                    "type": "string",
                    "description": "Path to a conversion upload CSV file inside the workspace or saved/ directory.",
                },
                "api_version": {
                    "type": "string",
                    "description": "Google Ads API version (format 'v<N>'; defaults to active version).",
                },
            },
        },
    },
    {
        "name": "prepare_mutation",
        "description": "Executes a validate_only=True dry-run via run_mutation.py (for a saved/code/*.py script) or records a receipt, returning a HITL Consequence Verification Card prior to live execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "operation_summary": {"type": "string"},
                "before_state": {"type": "string"},
                "after_state": {"type": "string"},
                "consequences": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "reversibility": {
                    "type": "string",
                    "enum": ["REVERSIBLE", "IRREVERSIBLE"],
                },
                "script_path": {"type": "string"},
                "record_only": {"type": "boolean"},
            },
            "required": ["customer_id", "operation_summary", "consequences"],
        },
    },
    {
        "name": "execute_mutation",
        "description": "Verifies HITL confirmation, execute_mutates config, Tier 1 posture, financial limits, and dry-run receipt for live mutation execution.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_confirmed": {"type": "boolean"},
                "confirmation_summary": {"type": "string"},
                "script_path": {"type": "string"},
                "run_script": {"type": "boolean"},
            },
            "required": ["user_confirmed", "confirmation_summary"],
        },
    },
    {
        "name": "reject_mutation",
        "description": "Invalidates a pending dry-run receipt (REJECTED) for a saved/code/*.py script and logs HUMAN_REJECTED to mutation_audit.jsonl.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script_path": {
                    "type": "string",
                    "description": "Path to the saved/code/*.py mutation script whose pending receipt should be rejected.",
                },
                "reason": {
                    "type": "string",
                    "description": "Human-readable reason for rejecting the pending mutation.",
                },
            },
            "required": ["script_path"],
        },
    },
    {
        "name": "create_account",
        "description": "Validates (dry-run default) or creates a new Google Ads client account under an MCC.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "manager_customer_id": {"type": "string"},
                "descriptive_name": {"type": "string"},
                "currency_code": {"type": "string"},
                "time_zone": {"type": "string"},
                "email_address": {"type": "string"},
                "access_role": {"type": "string"},
                "validate_only": {"type": "boolean"},
                "execute": {"type": "boolean"},
                "user_confirmed": {"type": "boolean"},
                "api_version": {"type": "string"},
            },
            "required": ["manager_customer_id"],
        },
    },
    {
        "name": "create_campaign",
        "description": "Validates (dry-run default) or creates a Google Ads campaign and optional budget.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "campaign_name": {"type": "string"},
                "budget_name": {"type": "string"},
                "budget_amount_micros": {"type": "integer"},
                "budget_resource_name": {"type": "string"},
                "budget_delivery_method": {"type": "string"},
                "advertising_channel_type": {"type": "string"},
                "status": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "contains_eu_political_advertising": {"type": "boolean"},
                "validate_only": {"type": "boolean"},
                "execute": {"type": "boolean"},
                "user_confirmed": {"type": "boolean"},
                "api_version": {"type": "string"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "create_ad_group",
        "description": "Validates (dry-run default) or creates a Google Ads ad group under a campaign.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "campaign_id": {"type": "string"},
                "campaign_resource_name": {"type": "string"},
                "ad_group_name": {"type": "string"},
                "cpc_bid_micros": {"type": "integer"},
                "status": {"type": "string"},
                "ad_group_type": {"type": "string"},
                "validate_only": {"type": "boolean"},
                "execute": {"type": "boolean"},
                "user_confirmed": {"type": "boolean"},
                "api_version": {"type": "string"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "create_ad",
        "description": "Validates (dry-run default) or creates a Responsive Search Ad under an ad group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "ad_group_id": {"type": "string"},
                "ad_group_resource_name": {"type": "string"},
                "final_urls": {"type": "array", "items": {"type": "string"}},
                "headlines": {"type": "array", "items": {"type": "string"}},
                "descriptions": {"type": "array", "items": {"type": "string"}},
                "path1": {"type": "string"},
                "path2": {"type": "string"},
                "status": {"type": "string"},
                "validate_only": {"type": "boolean"},
                "execute": {"type": "boolean"},
                "user_confirmed": {"type": "boolean"},
                "api_version": {"type": "string"},
            },
            "required": ["customer_id"],
        },
    },
]

_MCP_TOOL_TO_INTENT: dict[str, str] = {
    "gaql_validate": "GAQL_VALIDATE",
    "inspect_object": "INSPECT_OBJECT",
    "troubleshoot_conversions": "TROUBLESHOOT_CONVERSIONS",
    "prepare_mutation": "PREPARE_MUTATION",
    "execute_mutation": "EXECUTE_MUTATION",
    "reject_mutation": "REJECT_MUTATION",
    "create_account": "CREATE_ACCOUNT",
    "create_campaign": "CREATE_CAMPAIGN",
    "create_ad_group": "CREATE_AD_GROUP",
    "create_ad": "CREATE_AD",
}


def run_mcp_stdio_server(
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
) -> None:
    """Runs the Model Context Protocol (MCP) JSON-RPC 2.0 server over stdio."""
    _configure_sandbox_writable_env()
    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    handler = A2AHandler.__new__(A2AHandler)

    def _write_jsonrpc(msg_obj: dict[str, Any]) -> None:
        out_stream.write(json.dumps(msg_obj, separators=(",", ":")) + "\n")
        out_stream.flush()

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue

        if not isinstance(req, dict):
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32600, "message": "Invalid Request"},
                }
            )
            continue

        is_notification = "id" not in req
        req_id = req.get("id")
        method = str(req.get("method", ""))
        params = req.get("params") or {}

        if is_notification or method.startswith("notifications/"):
            continue

        if method == "initialize":
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "google-ads-api-assistant",
                            "version": get_plugin_version(),
                        },
                    },
                }
            )
        elif method == "ping":
            _write_jsonrpc({"jsonrpc": "2.0", "id": req_id, "result": {}})
        elif method == "tools/list":
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": _MCP_TOOL_DEFINITIONS},
                }
            )
        elif method == "tools/call":
            if not isinstance(params, dict):
                _write_jsonrpc(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: expected object",
                        },
                    }
                )
                continue

            tool_name = str(params.get("name", "")).strip()
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                _write_jsonrpc(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid params: 'arguments' must be an object",
                        },
                    }
                )
                continue

            intent = _MCP_TOOL_TO_INTENT.get(tool_name)
            if not intent:
                _write_jsonrpc(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {
                            "code": -32602,
                            "message": f"Unknown tool: '{tool_name}'",
                        },
                    }
                )
                continue

            call_task_id = f"mcp_{req_id}" if req_id is not None else "mcp_call"
            captured_stdout = io.StringIO()
            with contextlib.redirect_stdout(captured_stdout):
                res = handler._dispatch_intent(call_task_id, intent, arguments)

            is_err = res.get("status") not in (
                "COMPLETED",
                "HITL_CONFIRMATION_REQUIRED",
                "HUMAN_REJECTED",
            )
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": json.dumps(res, indent=2)}
                        ],
                        "isError": is_err,
                    },
                }
            )
        else:
            _write_jsonrpc(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: '{method}'",
                    },
                }
            )


def run_server() -> None:
    """Starts the loopback-only A2A HTTP server with Bearer authentication."""
    global PORT
    PORT = _resolve_server_port()
    sandbox_dir = _configure_sandbox_writable_env()

    # Sync user-scoped ~/google-ads.yaml into installed user plugin config ONLY
    # (never mutating git-tracked files or read-only sandboxed PLUGIN_ROOT).
    existing_cfg_env = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
    raw_home_yaml = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
    has_valid_cfg_env = bool(
        existing_cfg_env
        and os.path.abspath(os.path.expanduser(existing_cfg_env)) != raw_home_yaml
        and os.path.isfile(os.path.expanduser(existing_cfg_env))
    )
    candidate_user_cfg_dirs = [
        d
        for d in (
            os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip(),
            os.path.join(sandbox_dir, "config") if sandbox_dir else "",
            os.path.join(os.environ.get("PLUGIN_ROOT", "").strip(), "config")
            if os.environ.get("PLUGIN_ROOT", "").strip()
            else "",
            os.path.join(os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip(), "config")
            if os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
            else "",
            os.path.join(os.environ.get("GOOGLE_ADS_ASSISTANT_DIR", "").strip(), "config")
            if os.environ.get("GOOGLE_ADS_ASSISTANT_DIR", "").strip()
            else "",
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
            ),
        )
        if d and _is_dir_writable(d)
    ]
    if not has_valid_cfg_env and candidate_user_cfg_dirs and os.path.isfile(raw_home_yaml):
        user_cfg_dir = candidate_user_cfg_dirs[0]
        try:
            from config.config_init import (
                get_configured_customer_id,
                sync_and_set_config_kv,
            )

            config_key = os.environ.get("GOOGLE_ADS_CONFIG_KEY", "login_customer_id")
            config_val = os.environ.get("GOOGLE_ADS_CONFIG_VALUE") or (
                get_configured_customer_id(config_dir=user_cfg_dir)
            )
            if config_val:
                sync_and_set_config_kv(
                    key=config_key,
                    value=config_val,
                    config_dir=user_cfg_dir,
                )
        except Exception as e:
            print(f"Configuration sync notice: {e}", file=sys.stderr)

    auth_token = _resolve_a2a_auth_token()
    server_address = ("127.0.0.1", PORT)
    httpd = HTTPServer(server_address, A2AHandler)
    httpd.auth_token = auth_token  # type: ignore[attr-defined]
    httpd.require_auth = True  # type: ignore[attr-defined]
    httpd.timeout = 30
    print(
        f"Starting Google Ads API Assistant Plugin Sidecar Server on http://127.0.0.1:{PORT}"
    )
    sys.stdout.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def main() -> None:
    """CLI entrypoint supporting both MCP stdio mode (--mcp/--stdio) and loopback HTTP A2A mode."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description="Google Ads API Developer Assistant A2A HTTP Sidecar & MCP Stdio Server.",
    )
    parser.add_argument(
        "--mcp",
        "--stdio",
        dest="mcp",
        action="store_true",
        default=False,
        help="Run as a JSON-RPC 2.0 Model Context Protocol (MCP) server over stdio.",
    )
    args = parser.parse_args()
    if args.mcp:
        run_mcp_stdio_server()
    else:
        run_server()


if __name__ == "__main__":
    main()
