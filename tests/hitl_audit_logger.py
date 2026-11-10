#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration loader, correlated JSONL audit logger, and summary table formatter.

Supports the Google Ads API Developer Assistant Post-MCP HITL Policy functional
test suite with:
  1. Validated test-account YAML configuration (`tests/test_account_config.yaml`).
  2. 0600-permissioned JSONL audit logging where every record has:
     - `record_id`: globally unique UUIDv4 identifier,
     - `record_type`: explicit record discriminator (`SUITE_START`, `REQUEST`,
       `RESPONSE`, `ERROR`, `TEST_RESULT`, `SUITE_SUMMARY`),
     - `is_error`: boolean (`true` exclusively on `ERROR` records for one-step
       filtering via `record_type == "ERROR"` or `is_error == true`),
     - `request_record_id` on every `RESPONSE` record linking back to the exact
       `REQUEST` record that generated the response.
  3. End-of-run summary and failed-test detail tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import getpass
import json
import os
import re
import sys
import textwrap
from typing import Any
import uuid

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN_ROOT = os.path.join(
    REPO_ROOT, "plugins", "google-ads-api-developer-assistant"
)
DEFAULT_TEST_ACCOUNT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "test_account_config.yaml"
)
DEFAULT_AUDIT_LOG_DIR = os.path.join(REPO_ROOT, "saved", "mutate_test_logs")

VALID_RECORD_TYPES = frozenset({
    "SUITE_START",
    "REQUEST",
    "RESPONSE",
    "ERROR",
    "TEST_RESULT",
    "SUITE_SUMMARY",
})

PLACEHOLDER_CUSTOMER_IDS = frozenset({
    "",
    "0000000000",
    "12345678",
    "1234567890",
    "REPLACE_WITH_TEST_CUSTOMER_ID",
    "TEST_CLIENT_CUSTOMER_ID",
})

_SENSITIVE_KEY_NAMES = frozenset({
    "client_secret",
    "oauth2_client_secret",
    "refresh_token",
    "access_token",
    "developer_token",
    "private_key",
    "json_key",
    "authorization",
    "a2a_auth_token",
    "password",
})

_CUSTOMER_ID_DIGITS_RE = re.compile(r"^\d{10}$")


def normalize_customer_id(raw_value: Any) -> str:
    """Strips hyphens/spaces from a customer ID while preserving non-numeric placeholders."""
    if raw_value is None:
        return ""
    cleaned = str(raw_value).strip()
    if not cleaned:
        return ""
    compact = cleaned.replace("-", "").replace(" ", "")
    if compact.isdigit():
        return compact
    return cleaned


def is_valid_customer_id(customer_id: str) -> bool:
    """Returns True when `customer_id` is a non-placeholder 10-digit Google Ads ID."""
    norm = normalize_customer_id(customer_id)
    if norm in PLACEHOLDER_CUSTOMER_IDS:
        return False
    return bool(_CUSTOMER_ID_DIGITS_RE.fullmatch(norm))


def redact_sensitive_data(obj: Any, _depth: int = 0) -> Any:
    """Recursively masks OAuth secrets, private keys, bearer tokens, and client IDs."""
    if _depth > 16:
        return "[MAX_DEPTH]"
    if isinstance(obj, dict):
        sanitized: dict[str, Any] = {}
        for k, v in obj.items():
            key_str = str(k)
            key_lower = key_str.strip().lower()
            if key_lower in _SENSITIVE_KEY_NAMES:
                sanitized[key_str] = "[REDACTED]"
            elif key_lower in ("client_id", "oauth2_client_id") and isinstance(v, str):
                sanitized[key_str] = f"{v[:8]}...[REDACTED]" if len(v) > 8 else "[REDACTED]"
            else:
                sanitized[key_str] = redact_sensitive_data(v, _depth + 1)
        return sanitized
    if isinstance(obj, (list, tuple)):
        return [redact_sensitive_data(item, _depth + 1) for item in obj]
    if isinstance(obj, str):
        if "Bearer " in obj:
            return re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", obj)
        return obj
    return obj


def _validate_safe_path(raw_path: str, label: str) -> str:
    """Rejects NUL bytes and normalizes a filesystem path."""
    if not isinstance(raw_path, str) or "\x00" in raw_path:
        raise ValueError(f"Invalid {label}: path must be a non-empty string without NUL bytes.")
    expanded = os.path.expanduser(raw_path.strip())
    if not expanded:
        raise ValueError(f"Invalid {label}: path cannot be empty.")
    return expanded


def resolve_credentials_yaml_path(configured_path: str) -> str:
    """Resolves `google-ads.yaml` across explicit, env, plugin, and user config locations."""
    clean = _validate_safe_path(configured_path or "config/google-ads.yaml", "credentials_yaml_path")
    if os.path.isabs(clean) and os.path.isfile(clean):
        return os.path.realpath(clean)

    env_cfg = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
    candidates: list[str] = []
    if env_cfg:
        candidates.append(os.path.expanduser(env_cfg))
    candidates.extend([
        os.path.abspath(clean),
        os.path.join(REPO_ROOT, clean),
        os.path.join(PLUGIN_ROOT, clean),
        os.path.join(PLUGIN_ROOT, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser("~/google-ads.yaml"),
    ])
    for cand in candidates:
        if cand and os.path.isfile(cand):
            return os.path.realpath(cand)
    return os.path.abspath(clean)


@dataclass
class TestAccountConfig:
    """Validated runtime configuration for functional tests against a Google Ads Test Account."""

    config_file_path: str
    test_customer_id: str
    login_customer_id: str = ""
    credentials_yaml_path: str = "config/google-ads.yaml"
    api_version: str = "v26"
    allow_live_execute: bool = True
    auto_provision_fixtures: bool = True
    require_test_account: bool = True
    max_daily_budget_micros: int = 10_000_000
    max_cpc_bid_micros: int = 2_000_000
    audit_log_dir: str = DEFAULT_AUDIT_LOG_DIR
    audit_filename_prefix: str = "hitl_policy_functional_audit"
    fixtures: dict[str, str] = field(default_factory=dict)


def load_test_account_config(
    config_path: str | None = None,
    *,
    customer_id_override: str | None = None,
    login_customer_id_override: str | None = None,
    credentials_yaml_override: str | None = None,
    api_version_override: str | None = None,
    allow_live_execute_override: bool | None = None,
) -> TestAccountConfig:
    """Loads and validates the test account YAML configuration file."""
    effective_cfg_path = _validate_safe_path(
        config_path or DEFAULT_TEST_ACCOUNT_CONFIG_PATH, "config_path"
    )
    resolved_cfg_path = os.path.abspath(effective_cfg_path)
    if not os.path.isfile(resolved_cfg_path):
        raise FileNotFoundError(
            f"Test account configuration file not found at '{resolved_cfg_path}'."
        )

    with open(resolved_cfg_path, "r", encoding="utf-8") as f:
        raw_data = yaml.safe_load(f) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(
            f"Configuration file '{resolved_cfg_path}' must contain a top-level YAML mapping."
        )

    acct_sec = raw_data.get("test_account")
    if not isinstance(acct_sec, dict):
        acct_sec = raw_data

    exec_sec = raw_data.get("execution")
    if not isinstance(exec_sec, dict):
        exec_sec = {}

    safety_sec = raw_data.get("safety")
    if not isinstance(safety_sec, dict):
        safety_sec = {}

    audit_sec = raw_data.get("audit_log")
    if not isinstance(audit_sec, dict):
        audit_sec = {}

    fixtures_sec = raw_data.get("fixtures")
    if not isinstance(fixtures_sec, dict):
        fixtures_sec = {}

    raw_cid = (
        customer_id_override
        or os.environ.get("GOOGLE_ADS_TEST_CUSTOMER_ID", "").strip()
        or acct_sec.get("test_customer_id", "")
    )
    raw_login_cid = (
        login_customer_id_override
        if login_customer_id_override is not None
        else (
            os.environ.get("GOOGLE_ADS_TEST_LOGIN_CUSTOMER_ID", "").strip()
            or acct_sec.get("login_customer_id", "")
        )
    )
    raw_creds = (
        credentials_yaml_override
        or acct_sec.get("credentials_yaml_path")
        or "config/google-ads.yaml"
    )
    api_version = str(
        api_version_override or acct_sec.get("api_version") or "v26"
    ).strip()
    if not re.fullmatch(r"v\d+", api_version):
        raise ValueError(f"Invalid api_version '{api_version}' (expected format 'v26').")

    allow_live = (
        bool(allow_live_execute_override)
        if allow_live_execute_override is not None
        else bool(exec_sec.get("allow_live_execute", True))
    )
    auto_prov = bool(exec_sec.get("auto_provision_fixtures", True))
    # Fail-closed invariant: `require_test_account` is enforced True for safety.
    require_test = bool(safety_sec.get("require_test_account", True))
    if not require_test:
        raise ValueError(
            "safety.require_test_account cannot be false; functional tests must run strictly "
            "against a Google Ads Test Account (customer.test_account == true)."
        )

    max_budget = int(safety_sec.get("max_daily_budget_micros", 10_000_000))
    max_cpc = int(safety_sec.get("max_cpc_bid_micros", 2_000_000))
    if max_budget <= 0 or max_cpc <= 0:
        raise ValueError("Safety micro caps (max_daily_budget_micros, max_cpc_bid_micros) must be > 0.")

    raw_audit_dir = str(audit_sec.get("directory") or DEFAULT_AUDIT_LOG_DIR).strip()
    audit_dir = (
        raw_audit_dir
        if os.path.isabs(raw_audit_dir)
        else os.path.join(REPO_ROOT, raw_audit_dir)
    )
    raw_prefix = str(
        audit_sec.get("filename_prefix") or "hitl_policy_functional_audit"
    ).strip()
    safe_prefix = re.sub(r"[^A-Za-z0-9._-]", "_", raw_prefix) or "hitl_policy_functional_audit"

    default_fixtures = {
        "test_campaign_name": "HITL_Functional_Test_Search_Paused",
        "test_pmax_campaign_name": "HITL_Functional_Test_PMax_Paused",
        "test_ad_group_name": "HITL_Functional_Test_AdGroup",
        "test_asset_group_name": "HITL_Functional_Test_AssetGroup",
        "test_keyword_text": "hitl policy functional test keyword",
        "test_negative_keyword_text": "hitl_negative_check_term",
        "test_label_name": "HITL_Functional_Test_Label",
        "test_shared_set_name": "HITL_Functional_Test_NegKeywordList",
        "test_conversion_action_name": "HITL_Functional_Test_UploadClicks",
        "test_user_list_name": "HITL_Functional_Test_CRM_UserList",
        "ato_probe_email": "qa.ato.check@example.com",
    }
    for k, v in fixtures_sec.items():
        if v is not None and str(v).strip():
            default_fixtures[str(k)] = str(v).strip()

    return TestAccountConfig(
        config_file_path=resolved_cfg_path,
        test_customer_id=normalize_customer_id(raw_cid),
        login_customer_id=normalize_customer_id(raw_login_cid),
        credentials_yaml_path=resolve_credentials_yaml_path(str(raw_creds)),
        api_version=api_version,
        allow_live_execute=allow_live,
        auto_provision_fixtures=auto_prov,
        require_test_account=True,
        max_daily_budget_micros=max_budget,
        max_cpc_bid_micros=max_cpc,
        audit_log_dir=os.path.abspath(audit_dir),
        audit_filename_prefix=safe_prefix,
        fixtures=default_fixtures,
    )


class FunctionalAuditLogger:
    """0600-permissioned JSONL audit logger with correlated REQUEST/RESPONSE/ERROR records."""

    def __init__(
        self,
        *,
        log_path: str | None = None,
        log_dir: str = DEFAULT_AUDIT_LOG_DIR,
        filename_prefix: str = "hitl_policy_functional_audit",
        target_customer_id: str = "",
        login_customer_id: str = "",
        api_version: str = "v26",
    ) -> None:
        self.run_id = str(uuid.uuid4())
        try:
            self.operator = getpass.getuser()
        except Exception:
            self.operator = "unknown"
        self.target_customer_id = target_customer_id
        self.login_customer_id = login_customer_id
        self.api_version = api_version
        self._seen_record_ids: set[str] = set()
        self._request_record_ids: set[str] = set()
        self.error_count = 0
        self.record_count = 0

        if log_path:
            clean_log_path = _validate_safe_path(log_path, "audit_log_path")
            self.log_path = os.path.abspath(clean_log_path)
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        else:
            abs_dir = os.path.abspath(_validate_safe_path(log_dir, "audit_log_dir"))
            os.makedirs(abs_dir, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H_%M_%S")
            safe_prefix = re.sub(r"[^A-Za-z0-9._-]", "_", filename_prefix) or "audit"
            self.log_path = os.path.join(abs_dir, f"{ts}_{safe_prefix}.jsonl")

        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.close(fd)
        self._enforce_0600()

    def _enforce_0600(self) -> None:
        if sys.platform != "win32" and os.path.isfile(self.log_path):
            try:
                os.chmod(self.log_path, 0o600)
            except OSError:
                pass

    def _next_record_id(self) -> str:
        rec_id = str(uuid.uuid4())
        while rec_id in self._seen_record_ids:
            rec_id = str(uuid.uuid4())
        self._seen_record_ids.add(rec_id)
        return rec_id

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _append_record(self, record: dict[str, Any]) -> dict[str, Any]:
        rec_type = str(record.get("record_type", ""))
        if rec_type not in VALID_RECORD_TYPES:
            raise ValueError(f"Unsupported record_type '{rec_type}'.")

        sanitized = redact_sensitive_data(record)
        line_bytes = (json.dumps(sanitized, default=str) + "\n").encode("utf-8")
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._enforce_0600()
        self.record_count += 1
        if rec_type == "ERROR":
            self.error_count += 1
        return sanitized

    def log_suite_start(self, config_summary: dict[str, Any]) -> str:
        """Writes a SUITE_START record and returns its unique `record_id`."""
        rec_id = self._next_record_id()
        self._append_record({
            "record_id": rec_id,
            "record_type": "SUITE_START",
            "is_error": False,
            "level": "INFO",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "target_customer_id": self.target_customer_id,
            "login_customer_id": self.login_customer_id,
            "api_version": self.api_version,
            "config": config_summary,
        })
        return rec_id

    def log_request(
        self,
        *,
        test_id: str,
        suite: str,
        action: str,
        payload: dict[str, Any] | None = None,
        service: str | None = None,
        method: str | None = None,
    ) -> str:
        """Writes a REQUEST record and returns its unique `record_id` for response correlation."""
        rec_id = self._next_record_id()
        self._request_record_ids.add(rec_id)
        entry: dict[str, Any] = {
            "record_id": rec_id,
            "record_type": "REQUEST",
            "is_error": False,
            "level": "INFO",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "test_id": test_id,
            "suite": suite,
            "action": action,
            "target_customer_id": self.target_customer_id,
            "login_customer_id": self.login_customer_id,
            "api_version": self.api_version,
            "payload": payload or {},
        }
        if service:
            entry["service"] = service
        if method:
            entry["method"] = method
        self._append_record(entry)
        return rec_id

    def log_response(
        self,
        *,
        request_record_id: str,
        test_id: str,
        suite: str,
        status: str,
        duration_ms: float = 0.0,
        payload: dict[str, Any] | None = None,
        google_ads_request_id: str | None = None,
    ) -> str:
        """Writes a RESPONSE record referencing `request_record_id` and returns its `record_id`."""
        if not request_record_id or request_record_id not in self._request_record_ids:
            raise ValueError(
                f"RESPONSE record requires a valid prior REQUEST record_id (got {request_record_id!r})."
            )
        rec_id = self._next_record_id()
        entry: dict[str, Any] = {
            "record_id": rec_id,
            "record_type": "RESPONSE",
            "request_record_id": request_record_id,
            "is_error": False,
            "level": "INFO",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "test_id": test_id,
            "suite": suite,
            "status": status,
            "duration_ms": round(float(duration_ms), 3),
            "google_ads_request_id": google_ads_request_id,
            "payload": payload or {},
        }
        self._append_record(entry)
        return rec_id

    def log_error(
        self,
        *,
        test_id: str,
        suite: str,
        error_code: str,
        error_message: str,
        request_record_id: str | None = None,
        response_record_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> str:
        """Writes an ERROR record (`record_type: "ERROR"`, `is_error: true`) and returns `record_id`."""
        rec_id = self._next_record_id()
        entry: dict[str, Any] = {
            "record_id": rec_id,
            "record_type": "ERROR",
            "is_error": True,
            "level": "ERROR",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "test_id": test_id,
            "suite": suite,
            "error_code": error_code,
            "error_message": error_message,
            "request_record_id": request_record_id,
            "response_record_id": response_record_id,
            "details": details or {},
        }
        self._append_record(entry)
        return rec_id

    def log_test_result(
        self,
        *,
        test_id: str,
        suite: str,
        name: str,
        passed: bool,
        duration_ms: float,
        details: str,
        last_request_record_id: str | None = None,
        error_record_id: str | None = None,
    ) -> str:
        """Writes a TEST_RESULT record summarizing a single test case outcome."""
        rec_id = self._next_record_id()
        self._append_record({
            "record_id": rec_id,
            "record_type": "TEST_RESULT",
            "is_error": False,
            "level": "INFO",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "test_id": test_id,
            "suite": suite,
            "name": name,
            "passed": bool(passed),
            "outcome": "PASSED" if passed else "FAILED",
            "duration_ms": round(float(duration_ms), 3),
            "details": details,
            "last_request_record_id": last_request_record_id,
            "error_record_id": error_record_id,
        })
        return rec_id

    def log_suite_summary(
        self,
        *,
        total_tests: int,
        passed_tests: int,
        failed_tests: int,
        duration_ms: float,
        failed_details: list[dict[str, Any]],
    ) -> str:
        """Writes the final SUITE_SUMMARY record to the JSONL audit log."""
        rec_id = self._next_record_id()
        self._append_record({
            "record_id": rec_id,
            "record_type": "SUITE_SUMMARY",
            "is_error": False,
            "level": "INFO",
            "timestamp": self.utc_now_iso(),
            "run_id": self.run_id,
            "operator": self.operator,
            "target_customer_id": self.target_customer_id,
            "total_tests": int(total_tests),
            "passed_tests": int(passed_tests),
            "failed_tests": int(failed_tests),
            "error_records_logged": int(self.error_count),
            "duration_ms": round(float(duration_ms), 3),
            "failed_test_details": failed_details,
        })
        return rec_id


def filter_error_records(log_path: str) -> list[dict[str, Any]]:
    """Filters a JSONL audit log and returns strictly the error records."""
    resolved = _validate_safe_path(log_path, "log_path")
    errors: list[dict[str, Any]] = []
    with open(resolved, "r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            rec = json.loads(stripped)
            if not isinstance(rec, dict):
                raise ValueError(f"Line {line_num} in '{resolved}' is not a JSON object.")
            if rec.get("record_type") == "ERROR" or rec.get("is_error") is True:
                errors.append(rec)
    return errors


def verify_audit_log_integrity(log_path: str) -> dict[str, Any]:
    """Validates unique IDs, record_type taxonomy, REQUEST->RESPONSE correlation, and error filter."""
    resolved = _validate_safe_path(log_path, "log_path")
    seen_ids: set[str] = set()
    request_ids: set[str] = set()
    response_count = 0
    error_by_type: list[str] = []
    error_by_flag: list[str] = []
    total_records = 0

    with open(resolved, "r", encoding="utf-8") as f:
        for line_num, raw_line in enumerate(f, start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            total_records += 1
            rec = json.loads(stripped)
            if not isinstance(rec, dict):
                raise AssertionError(f"Line {line_num}: expected JSON object.")
            rec_id = rec.get("record_id")
            if not isinstance(rec_id, str) or not rec_id.strip():
                raise AssertionError(f"Line {line_num}: missing non-empty record_id.")
            if rec_id in seen_ids:
                raise AssertionError(f"Line {line_num}: duplicate record_id '{rec_id}'.")
            seen_ids.add(rec_id)

            rec_type = rec.get("record_type")
            if rec_type not in VALID_RECORD_TYPES:
                raise AssertionError(f"Line {line_num}: invalid record_type {rec_type!r}.")

            if rec_type == "REQUEST":
                request_ids.add(rec_id)
            elif rec_type == "RESPONSE":
                response_count += 1
                req_ref = rec.get("request_record_id")
                if not isinstance(req_ref, str) or req_ref not in request_ids:
                    raise AssertionError(
                        f"Line {line_num}: RESPONSE {rec_id} has invalid request_record_id {req_ref!r}."
                    )

            if rec_type == "ERROR":
                error_by_type.append(rec_id)
            if rec.get("is_error") is True:
                error_by_flag.append(rec_id)

    if error_by_type != error_by_flag:
        raise AssertionError(
            "Mismatch between record_type=='ERROR' and is_error==True sets."
        )

    return {
        "total_records": total_records,
        "unique_record_ids": len(seen_ids),
        "request_records": len(request_ids),
        "response_records": response_count,
        "error_records": len(error_by_type),
    }


@dataclass
class TestCaseResult:
    """Outcome of a single functional test case."""

    test_id: str
    suite: str
    name: str
    passed: bool
    duration_ms: float
    details: str
    request_record_id: str | None = None
    error_record_id: str | None = None


def format_results_tables(
    results: list[TestCaseResult],
    *,
    target_customer_id: str,
    audit_log_path: str,
    error_record_count: int,
    total_duration_ms: float,
) -> str:
    """Renders summary counts, per-suite breakdown, and failed-test detail tables."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    pass_rate = (passed / total * 100.0) if total > 0 else 0.0

    lines: list[str] = []
    sep = "=" * 108
    thin = "-" * 108

    lines.append("")
    lines.append(sep)
    lines.append("GOOGLE ADS API DEVELOPER ASSISTANT — FUNCTIONAL TEST EXECUTION SUMMARY")
    lines.append(sep)
    lines.append(f"| {'Metric':<34} | {'Value':<67} |")
    lines.append(f"|{'-' * 36}|{'-' * 69}|")
    lines.append(f"| {'Target Test Account ID':<34} | {target_customer_id or '(unconfigured)':<67} |")
    lines.append(f"| {'Total Tests Executed':<34} | {str(total):<67} |")
    lines.append(f"| {'Tests Passed':<34} | {str(passed):<67} |")
    lines.append(f"| {'Tests Failed':<34} | {str(failed):<67} |")
    lines.append(f"| {'Pass Rate':<34} | {f'{pass_rate:.1f}%':<67} |")
    lines.append(f"| {'Error Records in JSONL Log':<34} | {str(error_record_count):<67} |")
    lines.append(f"| {'Total Duration':<34} | {f'{total_duration_ms / 1000.0:.2f}s':<67} |")
    lines.append(sep)

    # Suite breakdown table
    suite_order: list[str] = []
    suite_counts: dict[str, list[int]] = {}
    for r in results:
        if r.suite not in suite_counts:
            suite_order.append(r.suite)
            suite_counts[r.suite] = [0, 0]
        if r.passed:
            suite_counts[r.suite][0] += 1
        else:
            suite_counts[r.suite][1] += 1

    lines.append("")
    lines.append("PER-SUITE RESULTS")
    lines.append(thin)
    lines.append(f"| {'Suite':<16} | {'Passed':>10} | {'Failed':>10} | {'Total':>10} | {'Status':<48} |")
    lines.append(f"|{'-' * 18}|{'-' * 12}|{'-' * 12}|{'-' * 12}|{'-' * 50}|")
    for s_name in suite_order:
        s_pass, s_fail = suite_counts[s_name]
        s_tot = s_pass + s_fail
        s_status = "ALL PASSED" if s_fail == 0 else f"{s_fail} FAILED"
        lines.append(
            f"| {s_name:<16} | {s_pass:>10} | {s_fail:>10} | {s_tot:>10} | {s_status:<48} |"
        )
    lines.append(
        f"| {'TOTAL':<16} | {passed:>10} | {failed:>10} | {total:>10} | "
        f"{('ALL PASSED' if failed == 0 else f'{failed} FAILED'):<48} |"
    )
    lines.append(thin)

    # Failed tests detail table
    failed_items = [r for r in results if not r.passed]
    lines.append("")
    lines.append(f"FAILED TESTS DETAILS ({len(failed_items)} failed)")
    lines.append(sep)
    if not failed_items:
        lines.append("| None — all executed functional tests passed!                                                             |")
        lines.append(sep)
    else:
        lines.append(
            f"| {'Test ID':<12} | {'Suite':<10} | {'Test Case':<30} | {'Failure Details & Error Record ID':<43} |"
        )
        lines.append(f"|{'-' * 14}|{'-' * 12}|{'-' * 32}|{'-' * 45}|")
        for item in failed_items:
            name_wrapped = textwrap.wrap(item.name, width=30) or [item.name[:30]]
            err_suffix = (
                f" [error_record_id={item.error_record_id}]"
                if item.error_record_id
                else ""
            )
            full_detail = f"{item.details}{err_suffix}"
            detail_wrapped = textwrap.wrap(full_detail, width=43) or [""]
            row_count = max(len(name_wrapped), len(detail_wrapped), 1)
            for idx in range(row_count):
                c_id = item.test_id if idx == 0 else ""
                c_suite = item.suite if idx == 0 else ""
                c_name = name_wrapped[idx] if idx < len(name_wrapped) else ""
                c_det = detail_wrapped[idx] if idx < len(detail_wrapped) else ""
                lines.append(
                    f"| {c_id:<12} | {c_suite:<10} | {c_name:<30} | {c_det:<43} |"
                )
            lines.append(f"|{'-' * 14}|{'-' * 12}|{'-' * 32}|{'-' * 45}|")

    lines.append("")
    lines.append(f"Audit Log (JSONL) : {audit_log_path}")
    lines.append(
        f"Filter Errors CLI : python3 tests/hitl_policy_functional_suite.py --filter-errors \"{audit_log_path}\""
    )
    lines.append(
        f"Filter Errors jq  : jq 'select(.record_type == \"ERROR\")' \"{audit_log_path}\""
    )
    lines.append("")
    return "\n".join(lines)
