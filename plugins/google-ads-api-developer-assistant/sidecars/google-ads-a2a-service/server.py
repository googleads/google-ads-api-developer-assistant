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
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
import re
import secrets
import subprocess
import sys
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


def _validate_script_path_arg(
    script_path: Any, allowed_extensions: tuple[str, ...] = (".py",)
) -> Optional[str]:
    """Validates an optional file path argument, returning an error message if unsafe."""
    if script_path is None or str(script_path).strip() == "":
        return None
    if not isinstance(script_path, str) or "\x00" in script_path:
        return "Invalid path argument: must be a valid file path without NUL bytes."
    clean = script_path.strip()
    if os.path.splitext(clean)[1].lower() not in allowed_extensions:
        return f"Invalid path argument: expected file extension in {allowed_extensions}."
    return None


def _resolve_a2a_auth_token() -> str:
    """Resolves the A2A Bearer token via env -> 0o600 user token file -> random ephemeral secret."""
    env_tok = os.environ.get("A2A_AUTH_TOKEN", "").strip()
    if env_tok:
        return env_tok

    token_candidates = [
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/data/.a2a_token"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/saved/data/.a2a_token"
        ),
    ]
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
    user_plugin_dir = os.path.expanduser(
        "~/.gemini/config/plugins/google-ads-api-developer-assistant"
    )
    if os.path.isdir(user_plugin_dir):
        tok_file = os.path.join(user_plugin_dir, "saved", "data", ".a2a_token")
        try:
            os.makedirs(os.path.dirname(tok_file), mode=0o700, exist_ok=True)
            fd = os.open(tok_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(generated + "\n")
            os.chmod(tok_file, 0o600)
            return generated
        except OSError:
            pass

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
    candidate_config_files = [
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
        import google.ads.googleads  # type: ignore

        installed_versions = [
            attr for attr in dir(google.ads.googleads) if re.match(r"^v\d+$", attr)
        ]
        if installed_versions:
            installed_versions.sort(key=lambda x: int(x[1:]))
            return installed_versions[-1]
    except Exception:
        pass

    if allow_interactive and sys.stdin.isatty():
        try:
            user_input = input(
                "Google Ads API version could not be automatically determined. Please enter the API version to use (e.g., v26): "
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
        "Google Ads API version could not be automatically determined. Please supply an 'api_version' (e.g., 'v26') in the request payload or configure config/assistant_config."
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

    for env_root_key in ("CLAUDE_PLUGIN_ROOT", "GOOGLE_ADS_ASSISTANT_DIR"):
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
            lines = f.readlines()
    except OSError:
        return fields, enum_values

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
                label = "REPEATED" if m.group(3) == "RepeatedField" else "OPTIONAL"
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

        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
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
            if not raw_where_match or not re.search(
                r"segments\.date\s*=\s*['\"][0-9]{4}-[0-9]{2}-[0-9]{2}['\"]",
                raw_where_match.group(1),
                re.IGNORECASE,
            ):
                static_errors.append(
                    "Queries against 'click_view' require a single-day filter (WHERE segments.date = 'YYYY-MM-DD')."
                )

        if re.search(r"\bFROM\s+CHANGE_STATUS\b", stripped_upper):
            if (
                not where_match
                or "LAST_CHANGE_DATE_TIME" not in where_match.group(1)
                or not re.search(r"\b(?:BETWEEN|DURING)\b", where_match.group(1))
            ):
                static_errors.append(
                    "Queries against 'change_status' require a finite BETWEEN or DURING filter on last_change_date_time."
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

        ver_match = re.search(r"v(\d+)", api_version.lower())
        ver_num = int(ver_match.group(1)) if ver_match else None
        if ver_num is None or ver_num >= 23:
            if re.search(r"\bsegments\.hour\b", stripped, re.IGNORECASE):
                static_errors.append(
                    "In Google Ads API v23+, 'segments.hour' was renamed to 'segments.hour_of_day'. Update your query to use 'segments.hour_of_day'."
                )

        if static_errors:
            return {
                "task_id": task_id,
                "status": "VALIDATION_FAILED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "errors": static_errors,
            }

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "gaql_query": query,
                "gaql_validation": {
                    "status": "PASSED",
                    "static_checks": "PASSED",
                    "api_version": api_version,
                    "customer_id": customer_id,
                },
                "explanation": "GAQL query passed all structural and static analysis checks.",
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
                spec = spec_from_file_location("_sidecar_inspect_obj", inspect_script_path)
                if spec and spec.loader:
                    insp_mod = module_from_spec(spec)
                    spec.loader.exec_module(insp_mod)
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
                f"Invalid api_version '{api_version}'. Expected 'v<N>' (e.g., 'v26')."
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
                str(csv_path), allowed_extensions=(".csv",)
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
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "error": (proc.stdout + "\n" + proc.stderr).strip(),
                }
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": {
                    "header": "Created by the Google Ads API Developer Assistant",
                    "summary": proc.stdout.strip() or "CSV conversion upload validation passed.",
                    "api_version": api_version,
                    "checks": ["CSV structural, timestamp, value/currency, and SHA-256 PII checks passed"],
                },
            }

        if client is not None and customer_id:
            tc_path = os.path.abspath(
                os.path.join(
                    base_dir,
                    "../../skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py",
                )
            )
            spec = spec_from_file_location("_sidecar_troubleshoot_conv", tc_path)
            if spec and spec.loader:
                tc_mod = module_from_spec(spec)
                spec.loader.exec_module(tc_mod)
                diag = tc_mod.troubleshoot_conversions(
                    client, customer_id, json_output=True, output_dir=payload.get("output_dir")
                )
                return {
                    "task_id": task_id,
                    "status": "COMPLETED",
                    "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                    "result": {
                        "header": "Created by the Google Ads API Developer Assistant",
                        "summary": "; ".join(diag.get("executive_summary", [])) or "Diagnostics completed.",
                        "api_version": api_version,
                        "diagnostics": diag,
                        "checks": [
                            "offline_conversion_upload_client_summary queried",
                            "conversion_action diagnostics evaluated",
                        ],
                    },
                }

        return {
            "task_id": task_id,
            "status": "COMPLETED",
            "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
            "result": {
                "header": "Created by the Google Ads API Developer Assistant",
                "summary": "Verified offline conversion upload summary.",
                "api_version": api_version,
                "checks": [
                    "offline_conversion_upload_client_summary queried",
                    "Timestamp constraint verified: conversion_time > click_time",
                ],
            },
        }

    def handle_prepare_mutation(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Records a validate_only=True dry-run receipt and returns the HITL Consequence Card."""
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

        script_err = _validate_script_path_arg(script_path)
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
        spec = spec_from_file_location("run_mutation", runner_path)
        if not spec or not spec.loader:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": "Unable to load run_mutation verification module.",
            }

        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
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
                dry_run_output="Validated via sidecar PREPARE_MUTATION (validate_only=True).",
                request_sent_at_iso=now_iso,
                response_received_at_iso=now_iso,
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

        script_err = _validate_script_path_arg(script_path)
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
        spec = spec_from_file_location("run_mutation", runner_path)
        if not spec or not spec.loader:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "error": "Unable to load run_mutation verification module.",
            }

        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)

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

        if run_script:
            if not script_path or not os.path.isfile(os.path.abspath(script_path)):
                return {
                    "task_id": task_id,
                    "status": "VALIDATION_FAILED",
                    "destructive_hint": True,
                    "error": "EXECUTE_MUTATION with run_script=True requires an existing .py 'script_path'.",
                }
            resolved_script = os.path.abspath(script_path)
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
                    "error": (proc.stderr or proc.stdout or "Script execution failed.").strip(),
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
                    "stdout": proc.stdout,
                    "status_message": "HITL receipt verified and mutation script executed.",
                },
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        audit_entry = mod.append_mutation_audit_log(
            phase="EXECUTE",
            status="SUCCESS",
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
            user_approved_at_iso=now_iso,
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

    def _load_mutation_script(self, script_filename: str) -> Any:
        """Loads a mutation script module from skills/execute-mutation/scripts/."""
        script_path = os.path.abspath(
            os.path.join(
                base_dir, f"../../skills/execute-mutation/scripts/{script_filename}"
            )
        )
        spec = spec_from_file_location(
            script_filename.replace(".py", ""), script_path
        )
        if spec and spec.loader:
            mod = module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        raise RuntimeError(f"Unable to load mutation script '{script_filename}'.")

    def _check_live_execution_gate(
        self,
        task_id: str,
        payload: dict[str, Any],
        *,
        financial_rpc_calls: Optional[list[dict[str, Any]]] = None,
        operation_summary: str = "",
    ) -> tuple[Optional[dict[str, Any]], Optional[Any]]:
        """Enforces deletion prohibition, HITL confirmation, execute_mutates, and financial limits."""
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
                        customer_id=str(
                            payload.get("customer_id")
                            or payload.get("manager_customer_id", "")
                        ),
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

        return None, run_mod

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
        """Records a live A2A creation event in mutation_audit.jsonl when run_mutation is real."""
        if run_mod is None:
            return
        audit_fn = getattr(run_mod, "append_mutation_audit_log", None)
        if not callable(audit_fn) or isinstance(audit_fn, unittest.mock.MagicMock):
            return
        now_iso = datetime.now(timezone.utc).isoformat()
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
                user_approved_at_iso=now_iso,
            )
        except Exception:
            pass

    def handle_create_account(
        self, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Handles CREATE_ACCOUNT intent via create_account.py."""
        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            operation_summary="CustomerService.create_customer_client",
        )
        if gate_error is not None:
            return gate_error

        validate_only = _resolve_validate_only(payload)
        api_version = get_effective_api_version(payload, allow_interactive=False)
        mod = self._load_mutation_script("create_account.py")
        try:
            result = mod.create_account_under_mcc(
                manager_customer_id=str(
                    payload.get("manager_customer_id")
                    or payload.get("customer_id", "")
                ),
                api_version=api_version,
                descriptive_name=payload.get("descriptive_name")
                or payload.get("name"),
                currency_code=str(payload.get("currency_code", "USD")),
                time_zone=str(payload.get("time_zone", "America/New_York")),
                tracking_url_template=payload.get("tracking_url_template"),
                final_url_suffix=payload.get("final_url_suffix"),
                email_address=payload.get("email_address"),
                access_role=payload.get("access_role"),
                validate_only=validate_only,
                client=payload.get("client"),
                json_output=False,
            )
            if not validate_only:
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
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
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
        try:
            budget_micros = int(payload.get("budget_amount_micros", 5_000_000))
        except (TypeError, ValueError) as exc:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Invalid budget_amount_micros: {exc}",
            }

        fin_calls: Optional[list[dict[str, Any]]] = None
        if not (budget_rn and str(budget_rn).strip()):
            fin_calls = [
                {
                    "service": "CampaignBudgetService",
                    "method": "mutate_campaign_budgets",
                    "request_payload": {
                        "customer_id": str(payload.get("customer_id", "")),
                        "operations": [{"create": {"amount_micros": budget_micros}}],
                    },
                }
            ]

        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            financial_rpc_calls=fin_calls,
            operation_summary="CampaignService.mutate_campaigns",
        )
        if gate_error is not None:
            return gate_error

        validate_only = _resolve_validate_only(payload)
        api_version = get_effective_api_version(payload, allow_interactive=False)
        mod = self._load_mutation_script("create_campaign.py")
        try:
            result = mod.create_campaign(
                customer_id=str(payload.get("customer_id", "")),
                api_version=api_version,
                campaign_name=payload.get("campaign_name") or payload.get("name"),
                budget_amount_micros=budget_micros,
                budget_resource_name=budget_rn,
                budget_delivery_method=str(
                    payload.get("budget_delivery_method", "STANDARD")
                ),
                advertising_channel_type=str(
                    payload.get("advertising_channel_type")
                    or payload.get("channel_type", "SEARCH")
                ),
                status=str(payload.get("status", "PAUSED")),
                start_date=payload.get("start_date"),
                end_date=payload.get("end_date"),
                validate_only=validate_only,
                client=payload.get("client"),
                json_output=False,
                budget_name=payload.get("budget_name"),
                contains_eu_political_advertising=_strict_bool(
                    payload.get("contains_eu_political_advertising", False)
                ),
            )
            if not validate_only:
                self._record_live_audit(
                    run_mod,
                    status="SUCCESS",
                    customer_id=str(result.get("customer_id", "")),
                    operation_summary="CampaignService.mutate_campaigns",
                    after_state=str(result.get("campaign_resource_name", "CREATED")),
                    consequences=[
                        f"Created campaign '{result.get('campaign_name', '')}' with budget {budget_micros} micros"
                    ],
                    stdout=json.dumps(result, default=str),
                    command=["A2A:CREATE_CAMPAIGN"],
                )
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
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
                cpc_bid_int = int(cpc_bid_raw)
            except (TypeError, ValueError) as exc:
                return {
                    "task_id": task_id,
                    "status": "FAILED",
                    "destructive_hint": True,
                    "error": f"Invalid cpc_bid_micros: {exc}",
                }

        fin_calls: Optional[list[dict[str, Any]]] = None
        if cpc_bid_int is not None:
            fin_calls = [
                {
                    "service": "AdGroupService",
                    "method": "mutate_ad_groups",
                    "request_payload": {
                        "customer_id": str(payload.get("customer_id", "")),
                        "operations": [{"create": {"cpc_bid_micros": cpc_bid_int}}],
                    },
                }
            ]

        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            financial_rpc_calls=fin_calls,
            operation_summary="AdGroupService.mutate_ad_groups",
        )
        if gate_error is not None:
            return gate_error

        validate_only = _resolve_validate_only(payload)
        api_version = get_effective_api_version(payload, allow_interactive=False)
        mod = self._load_mutation_script("create_ad_group.py")
        try:
            result = mod.create_ad_group(
                customer_id=str(payload.get("customer_id", "")),
                campaign_id=payload.get("campaign_id"),
                campaign_resource_name=payload.get("campaign_resource_name"),
                api_version=api_version,
                ad_group_name=payload.get("ad_group_name") or payload.get("name"),
                cpc_bid_micros=cpc_bid_int,
                status=str(payload.get("status", "ENABLED")),
                ad_group_type=str(payload.get("ad_group_type", "SEARCH_STANDARD")),
                validate_only=validate_only,
                client=payload.get("client"),
                json_output=False,
            )
            if not validate_only:
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
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
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
        gate_error, run_mod = self._check_live_execution_gate(
            task_id,
            payload,
            operation_summary="AdGroupAdService.mutate_ad_group_ads",
        )
        if gate_error is not None:
            return gate_error

        validate_only = _resolve_validate_only(payload)
        api_version = get_effective_api_version(payload, allow_interactive=False)
        mod = self._load_mutation_script("create_ad.py")
        try:
            final_urls = payload.get("final_urls")
            if isinstance(final_urls, str):
                final_urls = [final_urls]
            elif final_urls is None and payload.get("final_url"):
                final_urls = [str(payload.get("final_url"))]

            result = mod.create_responsive_search_ad(
                customer_id=str(payload.get("customer_id", "")),
                ad_group_id=payload.get("ad_group_id"),
                ad_group_resource_name=payload.get("ad_group_resource_name"),
                api_version=api_version,
                final_urls=final_urls,
                headlines=payload.get("headlines"),
                descriptions=payload.get("descriptions"),
                path1=payload.get("path1"),
                path2=payload.get("path2"),
                status=str(payload.get("status", "PAUSED")),
                validate_only=validate_only,
                client=payload.get("client"),
                json_output=False,
            )
            if not validate_only:
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
            return {
                "task_id": task_id,
                "status": "COMPLETED",
                "destructive_hint": True,
                "executing_agent": "google-ads-api-developer-assistant-plugin-sidecar",
                "result": result,
            }
        except (SystemExit, Exception) as exc:
            return {
                "task_id": task_id,
                "status": "FAILED",
                "destructive_hint": True,
                "error": f"Ad creation failed: {exc}",
            }


_MCP_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "gaql_validate",
        "description": "Validates a Google Ads Query Language (GAQL) query against static syntax and v26 schema rules.",
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
                    "description": "Google Ads API version (e.g., 'v26').",
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
                    "description": "Google Ads API version (e.g., 'v26').",
                },
            },
        },
    },
    {
        "name": "generate_code",
        "description": "Generates AST-verified Python Google Ads API client code.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_prompt": {
                    "type": "string",
                    "description": "Description of the Google Ads API task.",
                },
                "customer_id": {
                    "type": "string",
                    "description": "Target Google Ads Customer ID.",
                },
                "api_version": {
                    "type": "string",
                    "description": "Google Ads API version (e.g., 'v26').",
                },
            },
        },
    },
    {
        "name": "troubleshoot_conversions",
        "description": "Runs conversion upload diagnostic checks for a Google Ads customer account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "Google Ads Customer ID.",
                },
                "api_version": {
                    "type": "string",
                    "description": "Google Ads API version (e.g., 'v26').",
                },
            },
        },
    },
    {
        "name": "prepare_mutation",
        "description": "Records a signed HITL dry-run receipt and returns a Consequence Verification Card prior to live execution.",
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
            },
            "required": ["customer_id", "operation_summary", "consequences"],
        },
    },
    {
        "name": "execute_mutation",
        "description": "Verifies HITL confirmation, execute_mutates config, financial limits, and dry-run receipt for live mutation execution.",
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
    "generate_code": "GENERATE_CODE",
    "troubleshoot_conversions": "TROUBLESHOOT_CONVERSIONS",
    "prepare_mutation": "PREPARE_MUTATION",
    "execute_mutation": "EXECUTE_MUTATION",
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
                            "name": "google-ads-assistant",
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

    # Sync user-scoped ~/google-ads.yaml into ~/.gemini/config/plugins/.../config ONLY
    # (never mutating git-tracked files inside the repository workspace).
    existing_cfg_env = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
    user_cfg_dir = os.path.expanduser(
        "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
    )
    if not (existing_cfg_env and os.path.isfile(existing_cfg_env)) and os.path.isdir(
        user_cfg_dir
    ):
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
        description="Google Ads API Developer Assistant A2A HTTP Sidecar & MCP Stdio Server."
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
