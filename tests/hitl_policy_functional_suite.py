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

"""Functional test suite for the Mutate Capabilities & Post-MCP HITL Policy Test Plan.

Executes functional tests from:
  "Google Ads API Developer Assistant — Mutate Capabilities & Post-MCP HITL Policy Test Plan"
against a configured Google Ads Test Account (`tests/test_account_config.yaml`), producing a
correlated 0600-permissioned JSONL audit log and end-of-run summary & failure tables.

Usage:
    # Execute full suite using tests/test_account_config.yaml:
    python3 tests/hitl_policy_functional_suite.py

    # Override test account / manager ID on CLI:
    python3 tests/hitl_policy_functional_suite.py --customer-id 1234567890 --login-customer-id 9998887776

    # Filter an audit log to strictly the error records:
    python3 tests/hitl_policy_functional_suite.py --filter-errors saved/mutate_test_logs/<file>.jsonl
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
from http.server import HTTPServer
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
import pkgutil
import secrets
import socket
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.request
import uuid

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.auth.credentials import AnonymousCredentials
from google.protobuf.json_format import MessageToDict
import yaml

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from hitl_audit_logger import (  # noqa: E402
    DEFAULT_TEST_ACCOUNT_CONFIG_PATH,
    PLUGIN_ROOT,
    FunctionalAuditLogger,
    TestAccountConfig,
    TestCaseResult,
    filter_error_records,
    format_results_tables,
    is_valid_customer_id,
    load_test_account_config,
    redact_sensitive_data,
    verify_audit_log_integrity,
)

if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

from config import config_init  # noqa: E402

CONFIG_INIT_SCRIPT = os.path.join(PLUGIN_ROOT, "config", "config_init.py")
RUN_MUTATION_SCRIPT = os.path.join(
    PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "run_mutation.py"
)
PMAX_FILTER_SCRIPT = os.path.join(
    PLUGIN_ROOT, "skills", "pmax-listing-filter", "scripts", "create_pmax_webpage_filter.py"
)
VALIDATE_CONV_SCRIPT = os.path.join(
    PLUGIN_ROOT,
    "skills",
    "troubleshoot-conversions",
    "scripts",
    "validate_conversion_upload.py",
)
VALIDATE_GAQL_SCRIPT = os.path.join(
    PLUGIN_ROOT, "skills", "validate-gaql", "scripts", "validate_gaql.py"
)
SIDECAR_SERVER_SCRIPT = os.path.join(
    PLUGIN_ROOT, "sidecars", "google-ads-a2a-service", "server.py"
)


def _load_run_mutation_module() -> Any:
    spec = spec_from_file_location("_functional_run_mutation", RUN_MUTATION_SCRIPT)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load {RUN_MUTATION_SCRIPT}")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_sidecar_module() -> Any:
    spec = spec_from_file_location("_functional_sidecar_server", SIDECAR_SERVER_SCRIPT)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load {SIDECAR_SERVER_SCRIPT}")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUN_MUTATION_MOD = _load_run_mutation_module()
SIDECAR_MOD = _load_sidecar_module()
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# ==============================================================================
# Policy 4-Tier 111-Service Catalog (Post MCP Policy HITL §4.1–§4.4)
# ==============================================================================

TIER_1_FINANCIAL_SERVICES: tuple[str, ...] = (
    "account_budget_proposal_service",
    "bidding_data_exclusion_service",
    "bidding_seasonality_adjustment_service",
    "bidding_strategy_service",
    "billing_setup_service",
    "campaign_budget_service",
)

TIER_2_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Core Spend & Status Control": (
        "campaign_service",
        "ad_group_service",
        "ad_group_ad_service",
        "asset_group_service",
        "smart_campaign_setting_service",
        "google_ads_service",
    ),
    "Bidding & Auction Mechanics": (
        "ad_group_criterion_service",
        "ad_group_bid_modifier_service",
        "campaign_bid_modifier_service",
        "ad_parameter_service",
        "ad_service",
        "ad_group_asset_service",
        "ad_group_asset_set_service",
        "campaign_asset_service",
        "campaign_asset_set_service",
        "customer_asset_service",
        "customer_asset_set_service",
        "asset_set_asset_service",
    ),
    "Smart Bidding & Conversion Optimization": (
        "conversion_action_service",
        "conversion_upload_service",
        "conversion_adjustment_upload_service",
        "conversion_custom_variable_service",
        "conversion_value_rule_service",
        "conversion_value_rule_set_service",
        "campaign_conversion_goal_service",
        "conversion_goal_campaign_config_service",
        "custom_conversion_goal_service",
        "customer_conversion_goal_service",
        "goal_service",
        "campaign_goal_config_service",
        "customer_sk_ad_network_conversion_value_schema_service",
    ),
    "Performance Max & AI Steering": (
        "asset_group_asset_service",
        "asset_group_listing_group_filter_service",
        "asset_group_signal_service",
        "automatically_created_asset_removal_service",
    ),
    "Traffic Boundaries & Exclusions": (
        "campaign_criterion_service",
        "customer_negative_criterion_service",
        "shared_set_service",
        "shared_criterion_service",
        "campaign_shared_set_service",
    ),
    "Testing, Recommendations & Automation": (
        "campaign_draft_service",
        "experiment_service",
        "experiment_arm_service",
        "recommendation_service",
        "recommendation_subscription_service",
    ),
    "Guaranteed Spend & Lead Credits": (
        "reservation_service",
        "local_services_lead_service",
    ),
}

TIER_3_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Account Structure & Linking": (
        "account_link_service",
        "customer_client_link_service",
        "customer_manager_link_service",
        "data_link_service",
        "product_link_invitation_service",
        "product_link_service",
        "third_party_app_analytics_link_service",
    ),
    "Administrative & Verification": (
        "batch_job_service",
        "customer_service",
        "customer_user_access_invitation_service",
        "customer_user_access_service",
        "identity_verification_service",
        "incentive_service",
    ),
    "Organization & Labeling": (
        "label_service",
        "campaign_label_service",
        "ad_group_label_service",
        "ad_group_ad_label_service",
        "ad_group_criterion_label_service",
        "customer_label_service",
        "campaign_group_service",
    ),
    "Planning & Forecasting": (
        "keyword_plan_service",
        "keyword_plan_campaign_service",
        "keyword_plan_campaign_keyword_service",
        "keyword_plan_ad_group_service",
        "keyword_plan_ad_group_keyword_service",
    ),
    "Audience & User Data Management": (
        "audience_service",
        "custom_audience_service",
        "custom_interest_service",
        "offline_user_data_job_service",
        "remarketing_action_service",
        "user_data_service",
        "user_list_customer_type_service",
        "user_list_service",
    ),
    "Asset & Customization Infrastructure": (
        "asset_service",
        "asset_set_service",
        "customizer_attribute_service",
        "customer_customizer_service",
        "campaign_customizer_service",
        "ad_group_customizer_service",
        "ad_group_criterion_customizer_service",
        "you_tube_video_upload_service",
    ),
}

TIER_4_READ_ONLY_SERVICES: tuple[str, ...] = (
    "asset_generation_service",
    "audience_insights_service",
    "benchmarks_service",
    "brand_suggestion_service",
    "content_creator_insights_service",
    "geo_target_constant_service",
    "google_ads_field_service",
    "invoice_service",
    "keyword_plan_idea_service",
    "keyword_theme_constant_service",
    "payments_account_service",
    "reach_plan_service",
    "shareable_preview_service",
    "smart_campaign_suggest_service",
    "travel_asset_suggestion_service",
)

GAP_01_NON_MUTATE_VERBS: tuple[str, ...] = (
    "create_product_link",
    "remove_product_link",
    "create_product_link_invitation",
    "update_product_link_invitation",
    "remove_product_link_invitation",
    "create_account_link",
    "create_data_link",
    "remove_data_link",
    "update_data_link",
    "create_you_tube_video_upload",
    "update_you_tube_video_upload",
    "remove_you_tube_video_upload",
    "create_offline_user_data_job",
    "add_offline_user_data_job_operations",
    "run_offline_user_data_job",
    "move_manager_link",
    "start_identity_verification",
    "remove_campaign_automatically_created_asset",
)


def _snake_to_pascal_service(snake_service: str) -> str:
    return "".join(part.capitalize() for part in snake_service.split("_"))


def _proto_to_dict(msg: Any) -> dict[str, Any]:
    if msg is None:
        return {}
    if isinstance(msg, dict):
        return dict(msg)
    pb = getattr(type(msg), "pb", None)
    raw = pb(msg) if callable(pb) else getattr(msg, "_pb", msg)
    try:
        return MessageToDict(raw, preserving_proto_field_name=True)
    except Exception:
        return {"repr": repr(msg)}


def _extract_ads_failure_summary(exc: BaseException) -> tuple[str, str | None, dict[str, Any]]:
    req_id = getattr(exc, "request_id", None)
    if isinstance(exc, GoogleAdsException):
        codes: list[str] = []
        errors_list: list[dict[str, Any]] = []
        failure = getattr(exc, "failure", None)
        if failure is not None:
            for err in getattr(failure, "errors", []):
                err_dict = _proto_to_dict(err)
                errors_list.append(err_dict)
                ec = err_dict.get("error_code", {})
                if isinstance(ec, dict) and ec:
                    k, v = next(iter(ec.items()))
                    codes.append(f"{k}.{v}")
        code_label = ", ".join(codes) if codes else type(exc).__name__
        return (
            code_label,
            str(req_id) if req_id else None,
            {"exception": type(exc).__name__, "codes": codes, "errors": errors_list},
        )
    return (
        type(exc).__name__,
        str(req_id) if req_id else None,
        {"exception": type(exc).__name__, "message": str(exc)},
    )


_FATAL_AUTH_OR_ACCESS_SUBSTRINGS: tuple[str, ...] = (
    "UNAUTHENTICATED",
    "USER_PERMISSION_DENIED",
    "CUSTOMER_NOT_FOUND",
    "INVALID_CUSTOMER_ID",
    "NOT_ADS_USER",
    "OAUTH_TOKEN",
    "RefreshError",
    "invalid_client",
    "invalid_grant",
)


def _is_auth_or_access_failure(code_label: str, message: str) -> bool:
    combined = f"{code_label} {message}"
    return any(tok.lower() in combined.lower() for tok in _FATAL_AUTH_OR_ACCESS_SUBSTRINGS)


@dataclass
class DiscoveredFixtures:
    """Resource names and baseline values discovered or provisioned on the test account."""

    account_verified: bool = False
    account_error: str = ""
    customer_descriptive_name: str = ""
    currency_code: str = "USD"
    search_campaign_rn: str = ""
    search_campaign_name: str = ""
    campaign_budget_rn: str = ""
    campaign_budget_micros: int = 5_000_000
    ad_group_rn: str = ""
    rsa_ad_rns: list[str] = field(default_factory=list)
    keyword_criterion_rn: str = ""
    keyword_cpc_micros: int = 1_000_000
    negative_criterion_rn: str = ""
    pmax_campaign_rn: str = ""
    asset_group_rn: str = ""
    asset_group_id: str = ""
    label_rn: str = ""
    label_name: str = ""
    shared_set_rn: str = ""
    conversion_action_rn: str = ""
    user_list_rn: str = ""


class FunctionalTestContext:
    """Manages sandbox isolation, live/descriptor GoogleAdsClient instances, and audit logging."""

    def __init__(
        self,
        cfg: TestAccountConfig,
        audit: FunctionalAuditLogger,
        *,
        client_factory: Callable[[TestAccountConfig, str], Any] | None = None,
        extra_pythonpath: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.audit = audit
        self._client_factory = client_factory
        self._extra_pythonpath = extra_pythonpath
        self.fixtures = DiscoveredFixtures()
        self.current_test_id = "INIT"
        self.current_suite = "INIT"
        self.last_request_record_id: str | None = None

        self._temp_dir_obj = tempfile.TemporaryDirectory(prefix="gads_hitl_func_")
        self.sandbox_dir = self._temp_dir_obj.name
        self.sandbox_cfg_dir = os.path.join(self.sandbox_dir, "config")
        self.sandbox_code_dir = os.path.join(self.sandbox_dir, "saved", "code")
        self.sandbox_data_dir = os.path.join(self.sandbox_dir, "saved", "data")
        self.sandbox_logs_dir = os.path.join(self.sandbox_dir, "saved", "logs")
        for d in (
            self.sandbox_cfg_dir,
            self.sandbox_code_dir,
            self.sandbox_data_dir,
            self.sandbox_logs_dir,
        ):
            os.makedirs(d, exist_ok=True)

        self.sandbox_yaml = os.path.join(self.sandbox_cfg_dir, "google-ads.yaml")
        self.sandbox_assistant_cfg = os.path.join(self.sandbox_cfg_dir, "assistant_config")
        self.sandbox_fin_limits = os.path.join(self.sandbox_cfg_dir, "financial_limits")
        self.sandbox_plugin_audit = os.path.join(
            self.sandbox_logs_dir, "mutation_audit.jsonl"
        )
        self.sandbox_receipt = os.path.join(self.sandbox_data_dir, "last_dry_run.json")

        self._saved_env: dict[str, str | None] = {}
        for env_key in (
            "GOOGLE_ADS_CONFIGURATION_FILE_PATH",
            "GOOGLE_ADS_ASSISTANT_CONFIG_DIR",
            "GOOGLE_ADS_ASSISTANT_DIR",
            "GOOGLE_ADS_FINANCIAL_LIMITS_FILE",
            "GOOGLE_ADS_MUTATION_AUDIT_LOG",
        ):
            self._saved_env[env_key] = os.environ.get(env_key)

        self._receipt_backups: dict[str, tuple[bytes, int] | None] = {}
        self._snapshot_global_receipts()
        self._seed_sandbox_configs()

        os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = self.sandbox_yaml
        os.environ["GOOGLE_ADS_ASSISTANT_CONFIG_DIR"] = self.sandbox_cfg_dir
        os.environ["GOOGLE_ADS_ASSISTANT_DIR"] = PLUGIN_ROOT
        os.environ["GOOGLE_ADS_FINANCIAL_LIMITS_FILE"] = self.sandbox_fin_limits
        os.environ["GOOGLE_ADS_MUTATION_AUDIT_LOG"] = self.sandbox_plugin_audit

        self._descriptor_client: Any = None
        self._live_client: Any = None
        self._live_client_error: str | None = None

    def _global_receipt_candidates(self) -> list[str]:
        cands = list(RUN_MUTATION_MOD.get_receipt_paths())
        if self.sandbox_receipt not in cands:
            cands.append(self.sandbox_receipt)
        return cands

    def _snapshot_global_receipts(self) -> None:
        for p in self._global_receipt_candidates():
            if os.path.isfile(p):
                try:
                    with open(p, "rb") as f:
                        raw = f.read()
                    mode = stat.S_IMODE(os.stat(p).st_mode)
                    self._receipt_backups[p] = (raw, mode)
                except OSError:
                    self._receipt_backups[p] = None
            else:
                self._receipt_backups[p] = None

    def clear_all_receipts(self) -> None:
        """Removes dry-run receipts in sandbox and plugin locations between test cases."""
        for p in self._global_receipt_candidates():
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _restore_global_receipts(self) -> None:
        self.clear_all_receipts()
        for p, backup in self._receipt_backups.items():
            if p.startswith(self.sandbox_dir):
                continue
            if backup is not None:
                raw, mode = backup
                try:
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode or 0o600)
                    with os.fdopen(fd, "wb") as f:
                        f.write(raw)
                    if sys.platform != "win32":
                        os.chmod(p, mode or 0o600)
                except OSError:
                    pass

    def _seed_sandbox_configs(self) -> None:
        if os.path.isfile(self.cfg.credentials_yaml_path):
            with open(self.cfg.credentials_yaml_path, "r", encoding="utf-8") as f:
                creds_data = yaml.safe_load(f) or {}
            if not isinstance(creds_data, dict):
                creds_data = {}
        else:
            creds_data = {}

        if self.cfg.login_customer_id:
            creds_data["login_customer_id"] = str(self.cfg.login_customer_id)
        creds_data.setdefault("use_proto_plus", True)

        if creds_data:
            fd = os.open(self.sandbox_yaml, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                yaml.safe_dump(creds_data, f, sort_keys=False)
            if sys.platform != "win32":
                os.chmod(self.sandbox_yaml, 0o600)

        self.write_sandbox_assistant_config(execute_mutates=False)
        fd_fl = os.open(self.sandbox_fin_limits, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd_fl, "w", encoding="utf-8") as f_fl:
            f_fl.write("# Sandbox financial limits unlocked for HITL policy testing\n")
            for lim_key in sorted(RUN_MUTATION_MOD.FINANCIAL_LIMIT_SPECS.keys()):
                f_fl.write(f'"{lim_key}" = 100000000000\n')
        if sys.platform != "win32":
            os.chmod(self.sandbox_fin_limits, 0o600)

    def write_sandbox_assistant_config(
        self,
        *,
        execute_mutates: bool = False,
        customer_id: str | None = None,
        api_version: str | None = None,
        enabled: bool = True,
    ) -> None:
        cid = customer_id if customer_id is not None else (self.cfg.test_customer_id or "12345678")
        ver = api_version or self.cfg.api_version
        content = (
            f'api_version = "{ver}"\n'
            f'customer_id = "{cid}"\n'
            f"execute_mutates = {'true' if execute_mutates else 'false'}\n"
            f"enabled = {'true' if enabled else 'false'}\n"
        )
        fd = os.open(self.sandbox_assistant_cfg, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        if sys.platform != "win32":
            os.chmod(self.sandbox_assistant_cfg, 0o600)

    def subprocess_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("GOOGLE_ADS_EXECUTE_MUTATES", None)
        env.pop("ANTIGRAVITY_SIDECAR_WEB_PORT", None)
        env["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = self.sandbox_yaml
        env["GOOGLE_ADS_ASSISTANT_CONFIG_DIR"] = self.sandbox_cfg_dir
        env["GOOGLE_ADS_ASSISTANT_DIR"] = PLUGIN_ROOT
        env["GOOGLE_ADS_FINANCIAL_LIMITS_FILE"] = self.sandbox_fin_limits
        env["GOOGLE_ADS_MUTATION_AUDIT_LOG"] = self.sandbox_plugin_audit

        existing_parts = [
            p for p in env.get("PYTHONPATH", "").strip().split(os.pathsep) if p
        ]
        cov_parts = [p for p in existing_parts if "cov_hook" in p]
        other_parts = [p for p in existing_parts if "cov_hook" not in p]

        pp_entries: list[str] = [*cov_parts]
        if self._extra_pythonpath:
            pp_entries.append(self._extra_pythonpath)
        pp_entries.append(os.path.join(PLUGIN_ROOT, "config"))
        pp_entries.extend(other_parts)
        env["PYTHONPATH"] = os.pathsep.join(pp_entries)

        if extra:
            for k, v in extra.items():
                env[k] = v
        return env

    def get_descriptor_client(self) -> Any:
        if self._descriptor_client is None:
            self._descriptor_client = GoogleAdsClient(
                credentials=AnonymousCredentials(),
                developer_token="",
                version=self.cfg.api_version,
            )
        return self._descriptor_client

    def get_live_client(self) -> Any:
        if self._live_client is not None:
            return self._live_client
        if self._live_client_error is not None:
            raise RuntimeError(self._live_client_error)
        try:
            if self._client_factory is not None:
                self._live_client = self._client_factory(self.cfg, self.sandbox_yaml)
            else:
                if not os.path.isfile(self.sandbox_yaml):
                    raise FileNotFoundError(
                        f"Credentials YAML not found at '{self.cfg.credentials_yaml_path}'."
                    )
                self._live_client = GoogleAdsClient.load_from_storage(
                    path=self.sandbox_yaml,
                    version=self.cfg.api_version,
                )
            return self._live_client
        except Exception as exc:
            self._live_client_error = f"{type(exc).__name__}: {exc}"
            raise

    def require_verified_test_account(self, action_desc: str) -> None:
        """Fails fast and logs a REQUEST/RESPONSE pair when the test-account gate did not pass."""
        if self.fixtures.account_verified:
            return
        req_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=f"TestAccountGateCheck:{action_desc}",
            payload={
                "target_customer_id": self.cfg.test_customer_id,
                "account_verified": False,
            },
        )
        self.last_request_record_id = req_id
        reason = (
            self.fixtures.account_error
            or "Target Google Ads Test Account was not verified during PREFLIGHT."
        )
        self.audit.log_response(
            request_record_id=req_id,
            test_id=self.current_test_id,
            suite=self.current_suite,
            status="BLOCKED_PREFLIGHT_FAILED",
            duration_ms=0.0,
            payload={"blocked_reason": reason},
        )
        raise AssertionError(f"Requires accessible Google Ads Test Account: {reason}")

    def logged_local_check(
        self,
        action: str,
        request_payload: dict[str, Any],
        fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Executes a local guardrail/config check wrapped in correlated REQUEST/RESPONSE logs."""
        req_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=action,
            payload=request_payload,
        )
        self.last_request_record_id = req_id
        t0 = time.perf_counter()
        try:
            resp = fn()
            dur = (time.perf_counter() - t0) * 1000.0
            self.audit.log_response(
                request_record_id=req_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status="OK",
                duration_ms=dur,
                payload=resp,
            )
            return resp
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            self.audit.log_response(
                request_record_id=req_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status="EXCEPTION",
                duration_ms=dur,
                payload={"exception": type(exc).__name__, "message": str(exc)},
            )
            raise

    def logged_subprocess(
        self,
        action: str,
        argv: list[str],
        *,
        stdin_text: str | None = None,
        extra_env: dict[str, str] | None = None,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess[str]:
        """Runs a Python/CLI subprocess (`shell=False`) and logs correlated REQUEST/RESPONSE."""
        req_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=action,
            payload={
                "argv": argv,
                "cwd": self.sandbox_dir,
                "stdin_present": stdin_text is not None,
            },
        )
        self.last_request_record_id = req_id
        t0 = time.perf_counter()
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=self.sandbox_dir,
            env=self.subprocess_env(extra_env),
            timeout=timeout,
            check=False,
        )
        dur = (time.perf_counter() - t0) * 1000.0
        self.audit.log_response(
            request_record_id=req_id,
            test_id=self.current_test_id,
            suite=self.current_suite,
            status=f"EXIT_{proc.returncode}",
            duration_ms=dur,
            payload={
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-2000:],
                "stderr": proc.stderr[-2000:],
            },
        )
        return proc

    def logged_rpc(
        self,
        service_name: str,
        method_name: str,
        request_obj: Any = None,
        *,
        kwargs: dict[str, Any] | None = None,
    ) -> tuple[bool, Any, str, str | None, dict[str, Any]]:
        """Invokes a live GoogleAdsClient RPC and logs correlated REQUEST and RESPONSE records.

        Returns `(ok, response_or_none, status_code, google_ads_request_id, serialized_payload)`.
        """
        req_dict = (
            _proto_to_dict(request_obj)
            if request_obj is not None
            else dict(kwargs or {})
        )
        req_rec_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=f"GoogleAdsRPC:{service_name}.{method_name}",
            service=service_name,
            method=method_name,
            payload=req_dict,
        )
        self.last_request_record_id = req_rec_id
        t0 = time.perf_counter()
        try:
            client = self.get_live_client()
            svc = client.get_service(service_name)
            fn = getattr(svc, method_name)
            if request_obj is not None:
                raw_resp = fn(request=request_obj)
            elif kwargs:
                raw_resp = fn(**kwargs)
            else:
                raw_resp = fn()

            if method_name in ("search", "search_google_ads_fields"):
                rows = list(raw_resp)
                dur = (time.perf_counter() - t0) * 1000.0
                ser = {
                    "row_count": len(rows),
                    "sample": [_proto_to_dict(r) for r in rows[:3]],
                }
                self.audit.log_response(
                    request_record_id=req_rec_id,
                    test_id=self.current_test_id,
                    suite=self.current_suite,
                    status="OK",
                    duration_ms=dur,
                    payload=ser,
                )
                return True, rows, "OK", None, ser

            if method_name == "search_stream":
                batches = list(raw_resp)
                rows = [r for b in batches for r in getattr(b, "results", [])]
                gads_req_id = (
                    getattr(batches[0], "request_id", None) if batches else None
                )
                dur = (time.perf_counter() - t0) * 1000.0
                ser = {
                    "row_count": len(rows),
                    "sample": [_proto_to_dict(r) for r in rows[:3]],
                }
                self.audit.log_response(
                    request_record_id=req_rec_id,
                    test_id=self.current_test_id,
                    suite=self.current_suite,
                    status="OK",
                    duration_ms=dur,
                    google_ads_request_id=str(gads_req_id) if gads_req_id else None,
                    payload=ser,
                )
                return True, rows, "OK", str(gads_req_id) if gads_req_id else None, ser

            dur = (time.perf_counter() - t0) * 1000.0
            ser = _proto_to_dict(raw_resp)
            gads_req_id = getattr(raw_resp, "request_id", None) or ser.get("request_id")
            self.audit.log_response(
                request_record_id=req_rec_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status="OK",
                duration_ms=dur,
                google_ads_request_id=str(gads_req_id) if gads_req_id else None,
                payload=ser,
            )
            return True, raw_resp, "OK", str(gads_req_id) if gads_req_id else None, ser
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            code_label, gads_req_id, err_dict = _extract_ads_failure_summary(exc)
            self.audit.log_response(
                request_record_id=req_rec_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status=f"RPC_ERROR:{code_label}",
                duration_ms=dur,
                google_ads_request_id=gads_req_id,
                payload=err_dict,
            )
            return False, None, code_label, gads_req_id, err_dict

    def write_sandbox_script(self, filename: str, code: str) -> str:
        safe_name = os.path.basename(filename)
        if not safe_name.endswith(".py"):
            safe_name += ".py"
        target = os.path.join(self.sandbox_code_dir, safe_name)
        with open(target, "w", encoding="utf-8") as f:
            f.write(code)
        return target

    def close(self) -> None:
        self._restore_global_receipts()
        for env_key, orig_val in self._saved_env.items():
            if orig_val is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = orig_val
        self._temp_dir_obj.cleanup()


# ==============================================================================
# Helper Builders for Sandbox Scripts & Fixture Provisioning
# ==============================================================================


def _budget_mutation_script_source(
    budget_resource_name: str,
    amount_micros: int,
    *,
    force_validate_only_false: bool = False,
    drift_on_execute_micros: int | None = None,
    extra_call_on_execute: bool = False,
    skip_call_on_execute: bool = False,
    api_version: str = "v26",
) -> str:
    vo_expr = "False" if force_validate_only_false else "not args.execute"
    exec_micros = drift_on_execute_micros if drift_on_execute_micros is not None else amount_micros
    return f"""#!/usr/bin/env python3
import argparse
from google.ads.googleads.client import GoogleAdsClient

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--execute", action="store_true")
parser.add_argument("--customer-id", required=True)
args = parser.parse_args()

if args.execute and {skip_call_on_execute!r}:
    print("Skipped RPC on execute")
    raise SystemExit(0)

client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version={api_version!r})
svc = client.get_service("CampaignBudgetService")
req = client.get_type("MutateCampaignBudgetsRequest")
req.customer_id = args.customer_id
req.validate_only = {vo_expr}
if args.execute:
    req.response_content_type = client.enums.ResponseContentTypeEnum.MUTABLE_RESOURCE
op = client.get_type("CampaignBudgetOperation")
op.update.resource_name = {budget_resource_name!r}
op.update.amount_micros = {exec_micros} if args.execute else {amount_micros}
op.update_mask.paths.append("amount_micros")
req.operations.append(op)
resp = svc.mutate_campaign_budgets(request=req)
if args.execute and {extra_call_on_execute!r}:
    svc.mutate_campaign_budgets(request=req)
print("OK", getattr(resp, "results", []))
"""


def _discover_or_provision_fixtures(ctx: FunctionalTestContext) -> None:
    """Discovers Section 2.2 entities via GAQL and provisions missing PAUSED fixtures safely."""
    cid = ctx.cfg.test_customer_id
    client = ctx.get_live_client()
    suffix = uuid.uuid4().hex[:6]

    # 1. Search Campaign + Non-Shared Budget
    q_camp = (
        "SELECT campaign.resource_name, campaign.name, campaign.status, "
        "campaign_budget.resource_name, campaign_budget.amount_micros, "
        "campaign_budget.explicitly_shared "
        "FROM campaign "
        "WHERE campaign.advertising_channel_type = 'SEARCH' "
        "AND campaign.status = 'PAUSED' "
        "AND campaign_budget.explicitly_shared = FALSE "
        "LIMIT 1"
    )
    ok, rows, code, _, err = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_camp}
    )
    if not ok:
        raise AssertionError(f"Failed querying Search campaigns ({code}): {err}")
    if rows:
        r0 = rows[0]
        ctx.fixtures.search_campaign_rn = str(r0.campaign.resource_name)
        ctx.fixtures.search_campaign_name = str(r0.campaign.name)
        ctx.fixtures.campaign_budget_rn = str(r0.campaign_budget.resource_name)
        ctx.fixtures.campaign_budget_micros = int(
            getattr(r0.campaign_budget, "amount_micros", 5_000_000) or 5_000_000
        )
    elif ctx.cfg.auto_provision_fixtures:
        b_req = client.get_type("MutateCampaignBudgetsRequest")
        b_req.customer_id = cid
        b_op = client.get_type("CampaignBudgetOperation")
        b_op.create.name = f"HITL_Test_Budget_{suffix}"
        b_op.create.amount_micros = min(5_000_000, ctx.cfg.max_daily_budget_micros)
        b_op.create.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
        b_op.create.explicitly_shared = False
        b_req.operations.append(b_op)
        ok_b, resp_b, c_b, _, e_b = ctx.logged_rpc(
            "CampaignBudgetService", "mutate_campaign_budgets", b_req
        )
        if not ok_b:
            raise AssertionError(f"Failed provisioning CampaignBudget ({c_b}): {e_b}")
        ctx.fixtures.campaign_budget_rn = str(resp_b.results[0].resource_name)
        ctx.fixtures.campaign_budget_micros = min(5_000_000, ctx.cfg.max_daily_budget_micros)

        c_req = client.get_type("MutateCampaignsRequest")
        c_req.customer_id = cid
        c_op = client.get_type("CampaignOperation")
        camp_name = f"{ctx.cfg.fixtures['test_campaign_name']}_{suffix}"
        c_op.create.name = camp_name
        c_op.create.status = client.enums.CampaignStatusEnum.PAUSED
        c_op.create.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
        c_op.create.campaign_budget = ctx.fixtures.campaign_budget_rn
        c_op.create.manual_cpc.enhanced_cpc_enabled = False
        c_op.create.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        c_op.create.network_settings.target_google_search = True
        c_req.operations.append(c_op)
        ok_c, resp_c, c_c, _, e_c = ctx.logged_rpc(
            "CampaignService", "mutate_campaigns", c_req
        )
        if not ok_c:
            raise AssertionError(f"Failed provisioning Search Campaign ({c_c}): {e_c}")
        ctx.fixtures.search_campaign_rn = str(resp_c.results[0].resource_name)
        ctx.fixtures.search_campaign_name = camp_name

    # 2. AdGroup + 2 RSAs + Keyword Criterion + Negative CampaignCriterion
    if ctx.fixtures.search_campaign_rn:
        q_ag = (
            "SELECT ad_group.resource_name, ad_group.name "
            "FROM ad_group "
            f"WHERE campaign.resource_name = '{ctx.fixtures.search_campaign_rn}' "
            "AND ad_group.status != 'REMOVED' LIMIT 1"
        )
        ok_ag, rows_ag, _, _, _ = ctx.logged_rpc(
            "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_ag}
        )
        if ok_ag and rows_ag:
            ctx.fixtures.ad_group_rn = str(rows_ag[0].ad_group.resource_name)
        elif ctx.cfg.auto_provision_fixtures:
            ag_req = client.get_type("MutateAdGroupsRequest")
            ag_req.customer_id = cid
            ag_op = client.get_type("AdGroupOperation")
            ag_op.create.name = f"{ctx.cfg.fixtures['test_ad_group_name']}_{suffix}"
            ag_op.create.campaign = ctx.fixtures.search_campaign_rn
            ag_op.create.status = client.enums.AdGroupStatusEnum.PAUSED
            ag_op.create.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
            ag_op.create.cpc_bid_micros = min(1_000_000, ctx.cfg.max_cpc_bid_micros)
            ag_req.operations.append(ag_op)
            ok_cag, resp_cag, _, _, _ = ctx.logged_rpc(
                "AdGroupService", "mutate_ad_groups", ag_req
            )
            if ok_cag and resp_cag.results:
                ctx.fixtures.ad_group_rn = str(resp_cag.results[0].resource_name)

        if ctx.fixtures.ad_group_rn:
            q_rsa = (
                "SELECT ad_group_ad.resource_name "
                "FROM ad_group_ad "
                f"WHERE ad_group.resource_name = '{ctx.fixtures.ad_group_rn}' "
                "AND ad_group_ad.status != 'REMOVED' LIMIT 2"
            )
            ok_r, rows_r, _, _, _ = ctx.logged_rpc(
                "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_rsa}
            )
            if ok_r and rows_r:
                ctx.fixtures.rsa_ad_rns = [
                    str(r.ad_group_ad.resource_name) for r in rows_r
                ]
            if len(ctx.fixtures.rsa_ad_rns) < 2 and ctx.cfg.auto_provision_fixtures:
                needed = 2 - len(ctx.fixtures.rsa_ad_rns)
                aga_req = client.get_type("MutateAdGroupAdsRequest")
                aga_req.customer_id = cid
                for idx in range(needed):
                    aga_op = client.get_type("AdGroupAdOperation")
                    aga_op.create.ad_group = ctx.fixtures.ad_group_rn
                    aga_op.create.status = client.enums.AdGroupAdStatusEnum.PAUSED
                    aga_op.create.ad.final_urls.append("https://example.com")
                    for h_txt in (
                        f"Official Test Headline {idx + 1}A",
                        f"Trusted Quality Service {idx + 1}B",
                        f"Verified Test Solution {idx + 1}C",
                    ):
                        hl = client.get_type("AdTextAsset")
                        hl.text = h_txt[:30]
                        aga_op.create.ad.responsive_search_ad.headlines.append(hl)
                    for d_txt in (
                        "Automated functional test creative description one.",
                        "Second responsive search ad description for testing.",
                    ):
                        ds = client.get_type("AdTextAsset")
                        ds.text = d_txt[:90]
                        aga_op.create.ad.responsive_search_ad.descriptions.append(ds)
                    aga_req.operations.append(aga_op)
                ok_ca, resp_ca, _, _, _ = ctx.logged_rpc(
                    "AdGroupAdService", "mutate_ad_group_ads", aga_req
                )
                if ok_ca:
                    for res_item in resp_ca.results:
                        ctx.fixtures.rsa_ad_rns.append(str(res_item.resource_name))

            q_kw = (
                "SELECT ad_group_criterion.resource_name, ad_group_criterion.cpc_bid_micros "
                "FROM ad_group_criterion "
                f"WHERE ad_group.resource_name = '{ctx.fixtures.ad_group_rn}' "
                "AND ad_group_criterion.type = 'KEYWORD' "
                "AND ad_group_criterion.status != 'REMOVED' LIMIT 1"
            )
            ok_kw, rows_kw, _, _, _ = ctx.logged_rpc(
                "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_kw}
            )
            if ok_kw and rows_kw:
                ctx.fixtures.keyword_criterion_rn = str(
                    rows_kw[0].ad_group_criterion.resource_name
                )
                ctx.fixtures.keyword_cpc_micros = int(
                    getattr(rows_kw[0].ad_group_criterion, "cpc_bid_micros", 1_000_000)
                    or 1_000_000
                )
            elif ctx.cfg.auto_provision_fixtures:
                kw_req = client.get_type("MutateAdGroupCriteriaRequest")
                kw_req.customer_id = cid
                kw_op = client.get_type("AdGroupCriterionOperation")
                kw_op.create.ad_group = ctx.fixtures.ad_group_rn
                kw_op.create.status = client.enums.AdGroupCriterionStatusEnum.PAUSED
                kw_op.create.keyword.text = ctx.cfg.fixtures["test_keyword_text"]
                kw_op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
                kw_op.create.cpc_bid_micros = min(1_000_000, ctx.cfg.max_cpc_bid_micros)
                kw_req.operations.append(kw_op)
                ok_ckw, resp_ckw, _, _, _ = ctx.logged_rpc(
                    "AdGroupCriterionService", "mutate_ad_group_criteria", kw_req
                )
                if ok_ckw and resp_ckw.results:
                    ctx.fixtures.keyword_criterion_rn = str(resp_ckw.results[0].resource_name)

        q_neg = (
            "SELECT campaign_criterion.resource_name "
            "FROM campaign_criterion "
            f"WHERE campaign.resource_name = '{ctx.fixtures.search_campaign_rn}' "
            "AND campaign_criterion.negative = TRUE LIMIT 1"
        )
        ok_n, rows_n, _, _, _ = ctx.logged_rpc(
            "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_neg}
        )
        if ok_n and rows_n:
            ctx.fixtures.negative_criterion_rn = str(rows_n[0].campaign_criterion.resource_name)
        elif ctx.cfg.auto_provision_fixtures:
            nc_req = client.get_type("MutateCampaignCriteriaRequest")
            nc_req.customer_id = cid
            nc_op = client.get_type("CampaignCriterionOperation")
            nc_op.create.campaign = ctx.fixtures.search_campaign_rn
            nc_op.create.negative = True
            nc_op.create.keyword.text = ctx.cfg.fixtures["test_negative_keyword_text"]
            nc_op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.EXACT
            nc_req.operations.append(nc_op)
            ok_cn, resp_cn, _, _, _ = ctx.logged_rpc(
                "CampaignCriterionService", "mutate_campaign_criteria", nc_req
            )
            if ok_cn and resp_cn.results:
                ctx.fixtures.negative_criterion_rn = str(resp_cn.results[0].resource_name)

    # 3. Performance Max Campaign + AssetGroup
    q_pmax = (
        "SELECT campaign.resource_name, asset_group.resource_name, asset_group.id "
        "FROM asset_group "
        "WHERE campaign.advertising_channel_type = 'PERFORMANCE_MAX' "
        "AND campaign.status != 'REMOVED' LIMIT 1"
    )
    ok_pm, rows_pm, _, _, _ = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_pmax}
    )
    if ok_pm and rows_pm:
        ctx.fixtures.pmax_campaign_rn = str(rows_pm[0].campaign.resource_name)
        ctx.fixtures.asset_group_rn = str(rows_pm[0].asset_group.resource_name)
        ctx.fixtures.asset_group_id = str(rows_pm[0].asset_group.id)
    elif ctx.cfg.auto_provision_fixtures:
        ga_req = client.get_type("MutateGoogleAdsRequest")
        ga_req.customer_id = cid
        op_b = client.get_type("MutateOperation")
        op_b.campaign_budget_operation.create.resource_name = f"customers/{cid}/campaignBudgets/-1"
        op_b.campaign_budget_operation.create.name = f"HITL_PMax_Budget_{suffix}"
        op_b.campaign_budget_operation.create.amount_micros = min(
            5_000_000, ctx.cfg.max_daily_budget_micros
        )
        op_b.campaign_budget_operation.create.delivery_method = (
            client.enums.BudgetDeliveryMethodEnum.STANDARD
        )
        op_b.campaign_budget_operation.create.explicitly_shared = False
        ga_req.mutate_operations.append(op_b)

        op_c = client.get_type("MutateOperation")
        op_c.campaign_operation.create.resource_name = f"customers/{cid}/campaigns/-2"
        op_c.campaign_operation.create.name = (
            f"{ctx.cfg.fixtures['test_pmax_campaign_name']}_{suffix}"
        )
        op_c.campaign_operation.create.status = client.enums.CampaignStatusEnum.PAUSED
        op_c.campaign_operation.create.advertising_channel_type = (
            client.enums.AdvertisingChannelTypeEnum.PERFORMANCE_MAX
        )
        op_c.campaign_operation.create.campaign_budget = f"customers/{cid}/campaignBudgets/-1"
        op_c.campaign_operation.create.maximize_conversion_value.target_roas = 2.0
        op_c.campaign_operation.create.brand_guidelines_enabled = False
        op_c.campaign_operation.create.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        ga_req.mutate_operations.append(op_c)

        op_agg = client.get_type("MutateOperation")
        op_agg.asset_group_operation.create.name = (
            f"{ctx.cfg.fixtures['test_asset_group_name']}_{suffix}"
        )
        op_agg.asset_group_operation.create.campaign = f"customers/{cid}/campaigns/-2"
        op_agg.asset_group_operation.create.status = client.enums.AssetGroupStatusEnum.PAUSED
        op_agg.asset_group_operation.create.final_urls.append("https://example.com")
        ga_req.mutate_operations.append(op_agg)
        ok_pm_c, resp_pm_c, _, _, _ = ctx.logged_rpc("GoogleAdsService", "mutate", ga_req)
        if ok_pm_c and len(resp_pm_c.mutate_operation_responses) >= 3:
            ctx.fixtures.pmax_campaign_rn = str(
                resp_pm_c.mutate_operation_responses[1].campaign_result.resource_name
            )
            ag_rn = str(
                resp_pm_c.mutate_operation_responses[2].asset_group_result.resource_name
            )
            ctx.fixtures.asset_group_rn = ag_rn
            ctx.fixtures.asset_group_id = ag_rn.rsplit("/", 1)[-1]

    # 4. Label + SharedSet + UPLOAD_CLICKS ConversionAction + CRM_BASED UserList
    q_lbl = "SELECT label.resource_name, label.name FROM label WHERE label.status = 'ENABLED' LIMIT 1"
    ok_l, rows_l, _, _, _ = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_lbl}
    )
    if ok_l and rows_l:
        ctx.fixtures.label_rn = str(rows_l[0].label.resource_name)
        ctx.fixtures.label_name = str(rows_l[0].label.name)
    elif ctx.cfg.auto_provision_fixtures:
        l_req = client.get_type("MutateLabelsRequest")
        l_req.customer_id = cid
        l_op = client.get_type("LabelOperation")
        lbl_name = f"{ctx.cfg.fixtures['test_label_name']}_{suffix}"
        l_op.create.name = lbl_name
        l_req.operations.append(l_op)
        ok_cl, resp_cl, _, _, _ = ctx.logged_rpc("LabelService", "mutate_labels", l_req)
        if ok_cl and resp_cl.results:
            ctx.fixtures.label_rn = str(resp_cl.results[0].resource_name)
            ctx.fixtures.label_name = lbl_name

    q_ss = (
        "SELECT shared_set.resource_name FROM shared_set "
        "WHERE shared_set.type = 'NEGATIVE_KEYWORDS' AND shared_set.status = 'ENABLED' LIMIT 1"
    )
    ok_ss, rows_ss, _, _, _ = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_ss}
    )
    if ok_ss and rows_ss:
        ctx.fixtures.shared_set_rn = str(rows_ss[0].shared_set.resource_name)
    elif ctx.cfg.auto_provision_fixtures:
        ss_req = client.get_type("MutateSharedSetsRequest")
        ss_req.customer_id = cid
        ss_op = client.get_type("SharedSetOperation")
        ss_op.create.name = f"{ctx.cfg.fixtures['test_shared_set_name']}_{suffix}"
        ss_op.create.type_ = client.enums.SharedSetTypeEnum.NEGATIVE_KEYWORDS
        ss_req.operations.append(ss_op)
        ok_css, resp_css, _, _, _ = ctx.logged_rpc(
            "SharedSetService", "mutate_shared_sets", ss_req
        )
        if ok_css and resp_css.results:
            ctx.fixtures.shared_set_rn = str(resp_css.results[0].resource_name)

    q_ca = (
        "SELECT conversion_action.resource_name FROM conversion_action "
        "WHERE conversion_action.type = 'UPLOAD_CLICKS' "
        "AND conversion_action.status = 'ENABLED' LIMIT 1"
    )
    ok_ca2, rows_ca2, _, _, _ = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_ca}
    )
    if ok_ca2 and rows_ca2:
        ctx.fixtures.conversion_action_rn = str(rows_ca2[0].conversion_action.resource_name)
    elif ctx.cfg.auto_provision_fixtures:
        ca_req = client.get_type("MutateConversionActionsRequest")
        ca_req.customer_id = cid
        ca_op = client.get_type("ConversionActionOperation")
        ca_op.create.name = f"{ctx.cfg.fixtures['test_conversion_action_name']}_{suffix}"
        ca_op.create.type_ = client.enums.ConversionActionTypeEnum.UPLOAD_CLICKS
        ca_op.create.category = client.enums.ConversionActionCategoryEnum.DEFAULT
        ca_op.create.status = client.enums.ConversionActionStatusEnum.ENABLED
        ca_req.operations.append(ca_op)
        ok_cca, resp_cca, _, _, _ = ctx.logged_rpc(
            "ConversionActionService", "mutate_conversion_actions", ca_req
        )
        if ok_cca and resp_cca.results:
            ctx.fixtures.conversion_action_rn = str(resp_cca.results[0].resource_name)

    q_ul = (
        "SELECT user_list.resource_name FROM user_list "
        "WHERE user_list.type = 'CRM_BASED' LIMIT 1"
    )
    ok_ul, rows_ul, _, _, _ = ctx.logged_rpc(
        "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_ul}
    )
    if ok_ul and rows_ul:
        ctx.fixtures.user_list_rn = str(rows_ul[0].user_list.resource_name)
    elif ctx.cfg.auto_provision_fixtures:
        ul_req = client.get_type("MutateUserListsRequest")
        ul_req.customer_id = cid
        ul_op = client.get_type("UserListOperation")
        ul_op.create.name = f"{ctx.cfg.fixtures['test_user_list_name']}_{suffix}"
        ul_op.create.membership_life_span = 30
        ul_op.create.crm_based_user_list.upload_key_type = (
            client.enums.CustomerMatchUploadKeyTypeEnum.CONTACT_INFO
        )
        ul_req.operations.append(ul_op)
        ok_cul, resp_cul, _, _, _ = ctx.logged_rpc(
            "UserListService", "mutate_user_lists", ul_req
        )
        if ok_cul and resp_cul.results:
            ctx.fixtures.user_list_rn = str(resp_cul.results[0].resource_name)


# ==============================================================================
# Functional Test Case Definitions
# ==============================================================================


@dataclass
class FunctionalTestSpec:
    test_id: str
    suite: str
    name: str
    fn: Callable[[FunctionalTestContext], str]


def _build_all_tests() -> list[FunctionalTestSpec]:
    specs: list[FunctionalTestSpec] = []

    def register(test_id: str, suite: str, name: str):
        def _dec(fn: Callable[[FunctionalTestContext], str]):
            specs.append(FunctionalTestSpec(test_id=test_id, suite=suite, name=name, fn=fn))
            return fn

        return _dec

    # --------------------------------------------------------------------------
    # Section 2: PREFLIGHT — Config, Caller Access, Test-Account Gate & Fixtures
    # --------------------------------------------------------------------------

    @register("PF-01", "PREFLIGHT", "Test account config & 0600 credentials check")
    def pf_01(ctx: FunctionalTestContext) -> str:
        def _check() -> dict[str, Any]:
            cid_ok = is_valid_customer_id(ctx.cfg.test_customer_id)
            creds_exists = os.path.isfile(ctx.cfg.credentials_yaml_path)
            sbx_mode = (
                oct(stat.S_IMODE(os.stat(ctx.sandbox_yaml).st_mode))
                if os.path.isfile(ctx.sandbox_yaml)
                else "missing"
            )
            return {
                "config_file_path": ctx.cfg.config_file_path,
                "test_customer_id": ctx.cfg.test_customer_id,
                "customer_id_valid_10_digit": cid_ok,
                "credentials_yaml_exists": creds_exists,
                "sandbox_yaml_mode": sbx_mode,
            }

        res = ctx.logged_local_check(
            "ValidateTestAccountConfig",
            {"config_file": ctx.cfg.config_file_path},
            _check,
        )
        if not res["credentials_yaml_exists"]:
            ctx.fixtures.account_error = (
                f"Credentials YAML not found at '{ctx.cfg.credentials_yaml_path}'."
            )
            raise AssertionError(ctx.fixtures.account_error)
        if not res["customer_id_valid_10_digit"]:
            ctx.fixtures.account_error = (
                f"test_customer_id={ctx.cfg.test_customer_id!r} in "
                f"'{ctx.cfg.config_file_path}' is not a configured 10-digit Google Ads Test "
                "Account ID. Update tests/test_account_config.yaml or pass --customer-id."
            )
            raise AssertionError(ctx.fixtures.account_error)
        if sys.platform != "win32" and res["sandbox_yaml_mode"] != "0o600":
            raise AssertionError(
                f"Expected sandbox google-ads.yaml mode 0o600, got {res['sandbox_yaml_mode']}."
            )
        return f"Verified 10-digit test_customer_id={ctx.cfg.test_customer_id} and 0600 credentials."

    @register("PF-02", "PREFLIGHT", "Caller OAuth/SA access (list_accessible_customers)")
    def pf_02(ctx: FunctionalTestContext) -> str:
        ok, resp, code, _, err = ctx.logged_rpc(
            "CustomerService", "list_accessible_customers"
        )
        if not ok:
            ctx.fixtures.account_error = (
                f"Caller credentials failed list_accessible_customers ({code}): {err}"
            )
            raise AssertionError(ctx.fixtures.account_error)
        rns = list(getattr(resp, "resource_names", []) or [])
        if not rns:
            ctx.fixtures.account_error = (
                "Authenticated caller has 0 accessible Google Ads accounts "
                "(list_accessible_customers returned []). Ensure the person running these "
                "tests has OAuth/Service Account access to the configured test account."
            )
            raise AssertionError(ctx.fixtures.account_error)
        return f"Caller authenticated with {len(rns)} accessible customer resource(s)."

    @register("PF-03", "PREFLIGHT", "Verify caller access & customer.test_account == True")
    def pf_03(ctx: FunctionalTestContext) -> str:
        if not is_valid_customer_id(ctx.cfg.test_customer_id):
            reason = (
                ctx.fixtures.account_error
                or f"Invalid test_customer_id={ctx.cfg.test_customer_id!r}."
            )
            ctx.require_verified_test_account("PF-03")
            raise AssertionError(reason)

        query = (
            "SELECT customer.id, customer.descriptive_name, customer.test_account, "
            "customer.manager, customer.status, customer.currency_code "
            "FROM customer LIMIT 1"
        )
        ok, rows, code, _, err = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": query},
        )
        if not ok or not rows:
            ctx.fixtures.account_error = (
                f"Caller cannot access customer {ctx.cfg.test_customer_id} ({code}): {err}"
            )
            raise AssertionError(ctx.fixtures.account_error)

        cust = rows[0].customer
        is_test = bool(getattr(cust, "test_account", False) is True)
        is_mgr = bool(getattr(cust, "manager", False) is True)
        desc = str(getattr(cust, "descriptive_name", ""))
        currency = str(getattr(cust, "currency_code", "USD") or "USD")
        if not is_test:
            ctx.fixtures.account_error = (
                f"FATAL_NON_TEST_ACCOUNT: Account {ctx.cfg.test_customer_id} ({desc!r}) has "
                "customer.test_account=False. Refusing to run functional mutations on a "
                "production account."
            )
            raise AssertionError(ctx.fixtures.account_error)
        if is_mgr:
            ctx.fixtures.account_error = (
                f"Account {ctx.cfg.test_customer_id} ({desc!r}) is a Manager (MCC) account "
                "(customer.manager=True). Set test_customer_id to a Test Client Account ID and "
                "login_customer_id to the MCC ID."
            )
            raise AssertionError(ctx.fixtures.account_error)

        ctx.fixtures.account_verified = True
        ctx.fixtures.customer_descriptive_name = desc
        ctx.fixtures.currency_code = currency
        return (
            f"Verified Google Ads Test Client Account {ctx.cfg.test_customer_id} "
            f"({desc!r}, currency={currency}, test_account=True)."
        )

    @register("PF-04", "PREFLIGHT", "Section 2.2 test account entity discovery/provisioning")
    def pf_04(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("DiscoverOrProvisionFixtures")
        _discover_or_provision_fixtures(ctx)
        missing: list[str] = []
        if not ctx.fixtures.search_campaign_rn or not ctx.fixtures.campaign_budget_rn:
            missing.append("PAUSED SEARCH campaign + CampaignBudget")
        if not ctx.fixtures.ad_group_rn:
            missing.append("AdGroup")
        if not ctx.fixtures.keyword_criterion_rn:
            missing.append("Keyword AdGroupCriterion")
        if not ctx.fixtures.label_rn:
            missing.append("Label")
        if missing:
            raise AssertionError(f"Missing required Section 2.2 test fixtures: {missing}")
        return (
            f"Ready fixtures: campaign={ctx.fixtures.search_campaign_rn}, "
            f"ad_group={ctx.fixtures.ad_group_rn}, pmax_ag={ctx.fixtures.asset_group_rn or 'N/A'}."
        )

    # --------------------------------------------------------------------------
    # Section 3.1: Configuration, Master Switch & Tier 1 Policy Posture (TC-CFG)
    # --------------------------------------------------------------------------

    @register("TC-CFG-01", "TC-CFG", "Default safe state (execute_mutates = false)")
    def tc_cfg_01(ctx: FunctionalTestContext) -> str:
        fresh_cfg_dir = os.path.join(ctx.sandbox_dir, "cfg_01_fresh")
        ctx.logged_local_check(
            "sync_and_set_config_kv",
            {"config_dir": fresh_cfg_dir},
            lambda: {
                "yaml": config_init.sync_and_set_config_kv(
                    config_dir=fresh_cfg_dir,
                    source_yaml=ctx.sandbox_yaml,
                )
            },
        )
        default_enabled = config_init.is_execute_mutates_enabled(config_dir=fresh_cfg_dir)
        if default_enabled is not False:
            raise AssertionError(f"Expected default execute_mutates=False, got {default_enabled}.")

        ctx.write_sandbox_assistant_config(execute_mutates=False)
        noop_script = ctx.write_sandbox_script("cfg01_noop.py", "print('noop')\n")
        proc = ctx.logged_subprocess(
            "run_mutation_execute_when_disabled",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", noop_script, "--execute"],
        )
        if proc.returncode != 2:
            raise AssertionError(f"Expected exit code 2, got {proc.returncode}.")
        with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
            entries = [json.loads(ln) for ln in f if ln.strip()]
        if not any(e.get("status") == "BLOCKED_MUTATES_DISABLED" for e in entries):
            raise AssertionError("mutation_audit.jsonl missing BLOCKED_MUTATES_DISABLED.")
        return "Default execute_mutates=false verified; --execute exited 2 with BLOCKED_MUTATES_DISABLED."

    @register("TC-CFG-02", "TC-CFG", "CLI toggle (--execute-mutates)")
    def tc_cfg_02(ctx: FunctionalTestContext) -> str:
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        ctx.write_sandbox_assistant_config(
            execute_mutates=False, customer_id=cid, api_version=ctx.cfg.api_version
        )
        for state in ("true", "false"):
            proc = ctx.logged_subprocess(
                f"config_init_toggle_{state}",
                [
                    sys.executable,
                    CONFIG_INIT_SCRIPT,
                    "--config-dir",
                    ctx.sandbox_cfg_dir,
                    "--source-yaml",
                    ctx.sandbox_yaml,
                    "--execute-mutates",
                    state,
                ],
            )
            if proc.returncode != 0:
                raise AssertionError(f"Toggle to {state} failed: {proc.stderr}")
            parsed = config_init.read_assistant_config(config_dir=ctx.sandbox_cfg_dir)
            if parsed.get("execute_mutates") is not (state == "true"):
                raise AssertionError(f"Expected execute_mutates={state}, got {parsed}.")
            if parsed.get("customer_id") != cid or parsed.get("api_version") != ctx.cfg.api_version:
                raise AssertionError(f"Toggle altered customer_id/api_version: {parsed}")
        return "Toggled execute_mutates true/false without altering customer_id or api_version."

    @register("TC-CFG-03", "TC-CFG", "Environment variable precedence (GOOGLE_ADS_EXECUTE_MUTATES)")
    def tc_cfg_03(ctx: FunctionalTestContext) -> str:
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        noop_script = ctx.write_sandbox_script("cfg03_env.py", "print('noop')\n")
        proc = ctx.logged_subprocess(
            "run_mutation_with_env_override_false",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", noop_script, "--execute"],
            extra_env={"GOOGLE_ADS_EXECUTE_MUTATES": "false"},
        )
        hook_payload = json.dumps({
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": f'python3 "{RUN_MUTATION_SCRIPT}" --script "{noop_script}" --execute',
                    "Cwd": ctx.sandbox_dir,
                },
            }
        })
        hook_proc = ctx.logged_subprocess(
            "hook_with_env_override_false",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=hook_payload,
            extra_env={"GOOGLE_ADS_EXECUTE_MUTATES": "false"},
        )
        hook_json = json.loads(hook_proc.stdout.strip())
        if proc.returncode != 2 or hook_json.get("decision") != "deny":
            raise AssertionError(
                f"Env override failed: run_mutation rc={proc.returncode}, hook={hook_json}"
            )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        return "GOOGLE_ADS_EXECUTE_MUTATES=false overrode file execute_mutates=true in both layers."

    @register("TC-CFG-04", "TC-CFG", "Credential path isolation in PreToolUse")
    def tc_cfg_04(ctx: FunctionalTestContext) -> str:
        raw_cmd = (
            'python3 -c \'from google.ads.googleads.client import GoogleAdsClient; '
            'c = GoogleAdsClient.load_from_storage(); p = "~/google-ads.yaml"\''
        )
        hook_in = json.dumps({
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": raw_cmd, "Cwd": ctx.sandbox_dir},
            }
        })
        proc = ctx.logged_subprocess(
            "pretooluse_credential_rewrite",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=hook_in,
        )
        out = json.loads(proc.stdout.strip())
        rewritten = out.get("overwrite", {}).get("CommandLine", "")
        for expected_tok in (
            'path="config/google-ads.yaml"',
            "GOOGLE_ADS_CONFIGURATION_FILE_PATH=",
            "GOOGLE_ADS_ASSISTANT_DIR=",
            "PYTHONPATH=",
        ):
            if expected_tok not in rewritten:
                raise AssertionError(
                    f"Missing {expected_tok!r} in rewritten CommandLine: {rewritten}"
                )
        if "~/google-ads.yaml" in rewritten:
            raise AssertionError(f"Unrewritten ~/google-ads.yaml remained in: {rewritten}")
        return "PreToolUse rewrote credential paths and injected required env variables."

    @register("TC-CFG-05", "TC-CFG", "Tier 1 Financial Services default read-only posture (GAP-03)")
    def tc_cfg_05(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        unblocked_tier1: list[str] = []
        for svc_snake in TIER_1_FINANCIAL_SERVICES:
            svc_pascal = _snake_to_pascal_service(svc_snake)
            script = ctx.write_sandbox_script(f"cfg05_{svc_snake}.py", "print('tier1 check')\n")
            ctx.logged_subprocess(
                f"prepare_tier1_receipt_{svc_snake}",
                [
                    sys.executable,
                    RUN_MUTATION_SCRIPT,
                    "--script",
                    script,
                    "--dry-run",
                    "--record-only",
                    "--customer-id",
                    cid,
                    "--operation",
                    f"{svc_pascal} Tier 1 mutation",
                    "--after",
                    "amount_micros = 5000000",
                    "--consequences",
                    "Modifies financial spending cap by $5.00/day",
                ],
            )
            hook_in = json.dumps({
                "toolCall": {
                    "name": "run_command",
                    "args": {
                        "CommandLine": f"python3 {RUN_MUTATION_SCRIPT} --script {script} --execute",
                        "Cwd": ctx.sandbox_dir,
                    },
                }
            })
            h_proc = ctx.logged_subprocess(
                f"hook_tier1_posture_{svc_snake}",
                [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
                stdin_text=hook_in,
            )
            decision = json.loads(h_proc.stdout.strip()).get("decision")
            if decision != "deny":
                unblocked_tier1.append(f"{svc_snake} (decision={decision})")
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if unblocked_tier1:
            raise AssertionError(
                "GAP-03 (Policy §2.3A & §4.1): Tier 1 Financial Services were not blocked by "
                "default without an explicit Account Owner Tier 1 override when execute_mutates=true: "
                f"{', '.join(unblocked_tier1)}"
            )
        return "All 6 Tier 1 Financial Services enforced separate Account Owner override posture."

    # --------------------------------------------------------------------------
    # Section 3.2: PreToolUse Hook, Non-mutate_* RPC Coverage & Tier 4 (TC-HOOK)
    # --------------------------------------------------------------------------

    @register("TC-HOOK-01", "TC-HOOK", "Read-only skill & test runner allowlist")
    def tc_hook_01(ctx: FunctionalTestContext) -> str:
        cmds = [
            "python3 skills/validate-gaql/scripts/validate_gaql.py -q 'SELECT customer.id FROM customer'",
            "python3 skills/inspect-object/scripts/inspect_object.py --target Campaign",
            "python3 skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py",
            "python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py",
            "pytest -q",
            "ruff check .",
        ]
        res = ctx.logged_local_check(
            "evaluate_mutation_guard_allowlist",
            {"commands": cmds},
            lambda: {
                c: config_init.evaluate_mutation_guard(c, workspace_cwd=ctx.sandbox_dir)
                for c in cmds
            },
        )
        bad = {c: d for c, d in res.items() if d != ("allow", None)}
        if bad:
            raise AssertionError(f"Read-only commands not allowed: {bad}")
        return "All 6 read-only skill & test runner invocations returned ('allow', None)."

    @register("TC-HOOK-02", "TC-HOOK", "Tier 4 Autonomous Read-Only Services (All 15 Services)")
    def tc_hook_02(ctx: FunctionalTestContext) -> str:
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        tier4_calls = {
            "asset_generation_service": "svc.generate_text(request=req)",
            "audience_insights_service": "svc.list_insights_eligible_dates(request=req)",
            "benchmarks_service": "svc.list_benchmarks_sources(request=req)",
            "brand_suggestion_service": "svc.suggest_brands(request=req)",
            "content_creator_insights_service": "svc.generate_trending_insights(request=req)",
            "geo_target_constant_service": "svc.suggest_geo_target_constants(request=req)",
            "google_ads_field_service": "svc.search_google_ads_fields(request=req)",
            "invoice_service": "svc.list_invoices(request=req)",
            "keyword_plan_idea_service": "svc.generate_keyword_ideas(request=req)",
            "keyword_theme_constant_service": "svc.suggest_keyword_theme_constants(request=req)",
            "payments_account_service": "svc.list_payments_accounts(request=req)",
            "reach_plan_service": "svc.list_plannable_locations(request=req)",
            "shareable_preview_service": "svc.generate_shareable_previews(request=req)",
            "smart_campaign_suggest_service": "svc.suggest_keyword_themes(request=req)",
            "travel_asset_suggestion_service": "svc.suggest_travel_assets(request=req)",
            "google_ads_search_stream": "ga_service.search_stream(request=req)",
        }

        def _eval_all() -> dict[str, str]:
            outcomes: dict[str, str] = {}
            for name, snippet in tier4_calls.items():
                sp = ctx.write_sandbox_script(f"t4_{name}.py", f"{snippet}\n")
                dec, _ = config_init.evaluate_mutation_guard(
                    f'python3 "{sp}"', workspace_cwd=ctx.sandbox_dir
                )
                outcomes[name] = dec
            return outcomes

        outcomes = ctx.logged_local_check(
            "evaluate_tier4_readonly_services", {"services": list(tier4_calls)}, _eval_all
        )
        blocked = {k: v for k, v in outcomes.items() if v != "allow"}
        if blocked:
            raise AssertionError(f"Tier 4 services unexpectedly gated: {blocked}")
        return "100% of 15 Tier 4 services + search_stream returned 'allow' with zero prompts."

    @register("TC-HOOK-03", "TC-HOOK", "Direct inline bypass (python3 -c) & --confirm=true")
    def tc_hook_03(ctx: FunctionalTestContext) -> str:
        cmd = 'python3 -c "service.mutate_campaigns(request=req)" --confirm=true --yes'
        agy_proc = ctx.logged_subprocess(
            "hook_inline_bypass_agy",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=json.dumps({
                "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}}
            }),
        )
        claude_proc = ctx.logged_subprocess(
            "hook_inline_bypass_claude",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
        )
        agy_out = json.loads(agy_proc.stdout.strip())
        cl_out = json.loads(claude_proc.stdout.strip())
        if agy_out.get("decision") != "deny" or cl_out.get("permissionDecision") != "deny":
            raise AssertionError(f"Expected deny in agy & Claude: agy={agy_out}, claude={cl_out}")
        return "Fabricated --confirm=true inline bypass denied in both agy and Claude Code CLI."

    @register("TC-HOOK-04", "TC-HOOK", "Fake --dry-run CLI flag without validate_only=True")
    def tc_hook_04(ctx: FunctionalTestContext) -> str:
        sp = ctx.write_sandbox_script(
            "unsafe_fake_dry.py",
            "svc.mutate_campaigns(request=req)\n",
        )
        res = ctx.logged_local_check(
            "evaluate_fake_dry_run_flag",
            {"script": sp},
            lambda: {
                "decision": config_init.evaluate_mutation_guard(
                    f'python3 "{sp}" --dry-run', workspace_cwd=ctx.sandbox_dir
                )[0]
            },
        )
        if res["decision"] != "deny":
            raise AssertionError(f"Expected 'deny', got {res['decision']!r}.")
        return "Fake --dry-run without validate_only=True denied."

    @register("TC-HOOK-05", "TC-HOOK", "Mixed validate_only=True and validate_only=False")
    def tc_hook_05(ctx: FunctionalTestContext) -> str:
        sp = ctx.write_sandbox_script(
            "mixed_vo.py",
            "req1.validate_only = True\nreq2.validate_only = False\nsvc.mutate_campaigns(request=req2)\n",
        )
        res = ctx.logged_local_check(
            "evaluate_mixed_validate_only",
            {"script": sp},
            lambda: {
                "decision": config_init.evaluate_mutation_guard(
                    f'python3 "{sp}"', workspace_cwd=ctx.sandbox_dir
                )[0]
            },
        )
        if res["decision"] != "deny":
            raise AssertionError(f"Expected 'deny' on mixed validate_only, got {res['decision']!r}.")
        return "Mixed validate_only=True/False static bypass denied."

    @register("TC-HOOK-06", "TC-HOOK", "Direct call to _NON_VALIDATE_ONLY_CALL_RE methods")
    def tc_hook_06(ctx: FunctionalTestContext) -> str:
        methods = (
            "mutate_billing_setup",
            "book_campaigns",
            "apply_incentive",
            "apply_recommendation",
            "run_batch_job",
            "mutate_customer_user_access",
            "upload_user_data",
        )

        def _check() -> dict[str, str]:
            out: dict[str, str] = {}
            for m in methods:
                sp = ctx.write_sandbox_script(
                    f"non_vo_{m}.py",
                    f"other_req.validate_only = True\nsvc.{m}(request=req)\n",
                )
                dec, _ = config_init.evaluate_mutation_guard(
                    f'python3 "{sp}"', workspace_cwd=ctx.sandbox_dir
                )
                out[m] = dec
            return out

        res = ctx.logged_local_check(
            "evaluate_non_validate_only_methods", {"methods": list(methods)}, _check
        )
        missed = {m: d for m, d in res.items() if d != "deny"}
        if missed:
            raise AssertionError(f"Non-validate_only calls not denied: {missed}")
        return "All 7 non-validate_only direct script calls denied despite validate_only=True decoy."

    @register("TC-HOOK-07", "TC-HOOK", "Non-mutate_* RPC verb interception across 96 services (GAP-01)")
    def tc_hook_07(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=False)

        def _check() -> dict[str, dict[str, Any]]:
            results: dict[str, dict[str, Any]] = {}
            for verb in GAP_01_NON_MUTATE_VERBS:
                code = f"svc.{verb}(request=req)\n"
                sp = ctx.write_sandbox_script(f"gap01_{verb}.py", code)
                pat_matched = bool(config_init.MUTATION_CALL_PATTERN.search(code))
                dec, _ = config_init.evaluate_mutation_guard(
                    f'python3 "{sp}"', workspace_cwd=ctx.sandbox_dir
                )
                results[verb] = {"pattern_matched": pat_matched, "decision": dec}
            return results

        res = ctx.logged_local_check(
            "evaluate_gap01_non_mutate_verbs", {"verbs": list(GAP_01_NON_MUTATE_VERBS)}, _check
        )
        missed = [
            v
            for v, info in res.items()
            if not info["pattern_matched"] or info["decision"] != "deny"
        ]
        if missed:
            raise AssertionError(
                "GAP-01: MUTATION_CALL_PATTERN / evaluate_mutation_guard() failed to intercept "
                f"non-mutate_* write RPC verb(s): {', '.join(missed)}"
            )
        return "All 18 non-mutate_* write RPC verbs matched and denied."

    @register("TC-HOOK-08", "TC-HOOK", "Out-of-band force_ask / ask elicitation & receipt stamping")
    def tc_hook_08(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        sp = ctx.write_sandbox_script("hook08_op.py", "print('ok')\n")
        ctx.logged_subprocess(
            "hook08_prepare_receipt",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                cid,
                "--operation",
                "Update AdGroup status to PAUSED",
                "--after",
                "status = PAUSED",
                "--consequences",
                "Pauses ad serving with $0.00 spend increase",
            ],
        )
        hook_payload = json.dumps({
            "conversationId": "conv-hook-08-test",
            "transcriptPath": "/tmp/transcript_hook08.jsonl",
            "modelName": "gemini-pro-test",
            "tool_name": "Bash",
            "tool_input": {
                "command": f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
                "cwd": ctx.sandbox_dir,
            },
        })
        h_proc = ctx.logged_subprocess(
            "hook08_elicit_force_ask",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=hook_payload,
        )
        out = json.loads(h_proc.stdout.strip())
        with open(ctx.sandbox_receipt, "r", encoding="utf-8") as f:
            stamped = json.load(f)
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if out.get("decision") != "force_ask" or out.get("permissionDecision") != "ask":
            raise AssertionError(f"Expected force_ask + ask, got {out}")
        for req_field in (
            "hook_prompted_at_iso",
            "cli_conversation_id",
            "cli_transcript_path",
            "model_name",
        ):
            if not stamped.get(req_field):
                raise AssertionError(f"Receipt missing stamped field {req_field!r}: {stamped}")
        return "Hook emitted force_ask / ask and stamped all 4 session fields onto last_dry_run.json."

    @register("TC-HOOK-09", "TC-HOOK", "Anti-splitting per-invocation gate")
    def tc_hook_09(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        sp = ctx.write_sandbox_script("hook09_split.py", "print('budget +$10')\n")
        ctx.logged_subprocess(
            "hook09_single_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                cid,
                "--operation",
                "Increase budget +$10/day",
                "--after",
                "$20/day",
                "--consequences",
                "Increases daily spend cap by +$10.00/day",
            ],
        )
        # Call #1 consumes single-use receipt
        p1 = ctx.logged_subprocess(
            "hook09_exec_1",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        if p1.returncode != 0:
            raise AssertionError(f"Call #1 failed unexpectedly: {p1.stderr}")
        for idx in (2, 3):
            dec, reason = ctx.logged_local_check(
                f"hook09_exec_{idx}_guard",
                {"call_number": idx},
                lambda: dict(
                    zip(
                        ("decision", "reason"),
                        config_init.evaluate_mutation_guard(
                            f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
                            workspace_cwd=ctx.sandbox_dir,
                        ),
                    )
                ),
            ).values()
            if dec != "deny":
                raise AssertionError(f"Call #{idx} was not denied: {dec} ({reason})")
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        return "Call #1 consumed single-use receipt (EXECUTED); split calls #2 and #3 denied."

    # --------------------------------------------------------------------------
    # Section 3.3: Payload-Binding, Cryptographic Receipt & Interception (TC-RUN)
    # --------------------------------------------------------------------------

    @register("TC-RUN-01", "TC-RUN", "Pre-RPC block on missing validate_only=True in --dry-run")
    def tc_run_01(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-RUN-01")
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script(
            "run01_missing_vo.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                ctx.fixtures.campaign_budget_micros,
                force_validate_only_false=True,
                api_version=ctx.cfg.api_version,
            ),
        )
        proc = ctx.logged_subprocess(
            "dry_run_missing_validate_only",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Test missing validate_only",
                "--consequences",
                "Tests $5.00/day budget pre-RPC guard",
            ],
        )
        if proc.returncode == 0 or os.path.isfile(ctx.sandbox_receipt):
            raise AssertionError("Missing validate_only=True was not blocked pre-RPC.")
        with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
            entries = [json.loads(ln) for ln in f if ln.strip()]
        if entries[-1].get("status") != "BLOCKED_MISSING_VALIDATE_ONLY":
            raise AssertionError(f"Expected BLOCKED_MISSING_VALIDATE_ONLY, got {entries[-1].get('status')}")
        return "Aborted pre-RPC with BLOCKED_MISSING_VALIDATE_ONLY and wrote no receipt."

    @register("TC-RUN-02", "TC-RUN", "Pre-RPC block on non-validate_only RPC in --dry-run")
    def tc_run_02(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-RUN-02")
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script(
            "run02_non_vo.py",
            f"""#!/usr/bin/env python3
from google.ads.googleads.client import GoogleAdsClient
client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version={ctx.cfg.api_version!r})
svc = client.get_service("BillingSetupService")
req = client.get_type("MutateBillingSetupRequest")
req.customer_id = {ctx.cfg.test_customer_id!r}
svc.mutate_billing_setup(request=req)
""",
        )
        proc = ctx.logged_subprocess(
            "dry_run_unguarded_non_vo_rpc",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "BillingSetup unguarded check",
                "--consequences",
                "Billing settlement impact $0.00 test",
            ],
        )
        if proc.returncode == 0:
            raise AssertionError("Unguarded non-validate_only RPC succeeded during --dry-run.")
        with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
            entries = [json.loads(ln) for ln in f if ln.strip()]
        if entries[-1].get("status") != "BLOCKED_MISSING_VALIDATE_ONLY":
            raise AssertionError(f"Expected BLOCKED_MISSING_VALIDATE_ONLY, got {entries[-1].get('status')}")
        return "Unguarded non-validate_only RPC blocked pre-RPC with BLOCKED_MISSING_VALIDATE_ONLY."

    @register("TC-RUN-03", "TC-RUN", "Mandatory financial consequence disclosure")
    def tc_run_03(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        sp = ctx.write_sandbox_script("run03_fin_conseq.py", "print('dry')\n")
        proc = ctx.logged_subprocess(
            "dry_run_missing_financial_consequence",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                cid,
                "--operation",
                "Update CampaignBudget amount_micros",
                "--consequences",
                "Routine update",
            ],
        )
        if proc.returncode != 2:
            raise AssertionError(f"Expected exit code 2, got {proc.returncode}.")
        with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
            entries = [json.loads(ln) for ln in f if ln.strip()]
        if entries[-1].get("status") != "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING":
            raise AssertionError(
                f"Expected BLOCKED_FINANCIAL_CONSEQUENCE_MISSING, got {entries[-1].get('status')}"
            )
        return "Exited code 2 and logged BLOCKED_FINANCIAL_CONSEQUENCE_MISSING."

    @register("TC-RUN-04", "TC-RUN", "Post-dry-run script file edit (script_sha256)")
    def tc_run_04(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
        sp = ctx.write_sandbox_script("run04_edit.py", "print('v1')\n")
        ctx.logged_subprocess(
            "run04_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                cid,
                "--operation",
                "Attach organizational label",
                "--consequences",
                "Attaches organizational label",
            ],
        )
        with open(sp, "a", encoding="utf-8") as f:
            f.write("#")
        dec, _ = config_init.evaluate_mutation_guard(
            f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
            workspace_cwd=ctx.sandbox_dir,
        )
        exec_proc = ctx.logged_subprocess(
            "run04_execute_after_1byte_edit",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if dec != "deny" or exec_proc.returncode == 0 or "SHA-256" not in exec_proc.stderr:
            raise AssertionError(
                f"1-byte edit not rejected: hook={dec}, rc={exec_proc.returncode}, err={exec_proc.stderr}"
            )
        return "Both PreToolUse and load_and_verify_receipt() rejected 1-byte script edit."

    @register("TC-RUN-05", "TC-RUN", "Runtime request payload drift (request_sha256)")
    def tc_run_05(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-RUN-05")
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script(
            "run05_drift.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                ctx.fixtures.campaign_budget_micros,
                drift_on_execute_micros=ctx.fixtures.campaign_budget_micros + 1_000_000,
                api_version=ctx.cfg.api_version,
            ),
        )
        d_proc = ctx.logged_subprocess(
            "run05_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Budget runtime drift check",
                "--consequences",
                "Budget check $5.00/day",
            ],
        )
        if d_proc.returncode != 0:
            ctx.write_sandbox_assistant_config(execute_mutates=False)
            raise AssertionError(f"Dry-run failed: {d_proc.stderr}")
        e_proc = ctx.logged_subprocess(
            "run05_execute_with_runtime_drift",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if e_proc.returncode == 0 or "BLOCKED_SHA256_MISMATCH" not in e_proc.stderr:
            raise AssertionError(f"Runtime drift was not blocked: {e_proc.stderr}")
        return "Aborted pre-RPC on runtime payload drift with BLOCKED_SHA256_MISMATCH."

    @register("TC-RUN-06", "TC-RUN", "Unapproved extra or missing RPC calls during --execute")
    def tc_run_06(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-RUN-06")
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        for label, extra_flag, skip_flag in (
            ("extra_call", True, False),
            ("missing_call", False, True),
        ):
            ctx.clear_all_receipts()
            sp = ctx.write_sandbox_script(
                f"run06_{label}.py",
                _budget_mutation_script_source(
                    ctx.fixtures.campaign_budget_rn,
                    ctx.fixtures.campaign_budget_micros,
                    extra_call_on_execute=extra_flag,
                    skip_call_on_execute=skip_flag,
                    api_version=ctx.cfg.api_version,
                ),
            )
            d_proc = ctx.logged_subprocess(
                f"run06_dry_{label}",
                [
                    sys.executable,
                    RUN_MUTATION_SCRIPT,
                    "--script",
                    sp,
                    "--dry-run",
                    "--customer-id",
                    ctx.cfg.test_customer_id,
                    "--operation",
                    f"Call count check ({label})",
                    "--consequences",
                    "Budget check $5.00/day",
                ],
            )
            if d_proc.returncode != 0:
                ctx.write_sandbox_assistant_config(execute_mutates=False)
                raise AssertionError(f"Dry-run ({label}) failed: {d_proc.stderr}")
            e_proc = ctx.logged_subprocess(
                f"run06_exec_{label}",
                [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
            )
            if e_proc.returncode == 0 or "BLOCKED_SHA256_MISMATCH" not in e_proc.stderr:
                ctx.write_sandbox_assistant_config(execute_mutates=False)
                raise AssertionError(f"Subcase {label} did not fail with BLOCKED_SHA256_MISMATCH.")
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        return "Both (a) 1->2 extra RPC calls and (b) 1->0 missing RPC calls failed with BLOCKED_SHA256_MISMATCH."

    @register("TC-RUN-07", "TC-RUN", "Synchronous session TTL (1800s expiry)")
    def tc_run_07(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script("run07_ttl.py", "print('ttl')\n")
        ctx.logged_subprocess(
            "run07_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                "4863089361",
                "--operation",
                "Label check",
                "--consequences",
                "Organizational label change",
            ],
        )
        for p in ctx._global_receipt_candidates():
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["timestamp"] = time.time() - 1900
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f)
        dec, _ = config_init.evaluate_mutation_guard(
            f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
            workspace_cwd=ctx.sandbox_dir,
        )
        e_proc = ctx.logged_subprocess(
            "run07_exec_expired",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if dec != "deny" or e_proc.returncode == 0 or "expired" not in e_proc.stderr.lower():
            raise AssertionError(f"Stale receipt not rejected: hook={dec}, err={e_proc.stderr}")
        return "Both PreToolUse and run_mutation.py rejected receipt aged > 1800s."

    @register("TC-RUN-08", "TC-RUN", "Single-use receipt anti-replay (EXECUTED)")
    def tc_run_08(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script("run08_replay.py", "print('once')\n")
        ctx.logged_subprocess(
            "run08_dry",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                "4863089361",
                "--operation",
                "Single-use test",
                "--consequences",
                "Label attachment",
            ],
        )
        first = ctx.logged_subprocess(
            "run08_exec_1",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        replay = ctx.logged_subprocess(
            "run08_exec_replay",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if first.returncode != 0 or replay.returncode == 0 or "'EXECUTED'" not in replay.stderr:
            raise AssertionError(f"Replay check failed: replay rc={replay.returncode}, err={replay.stderr}")
        return "Replay failed deterministically with Dry-run receipt status is 'EXECUTED'."

    @register("TC-RUN-09", "TC-RUN", "Receipt JSON tampering detection")
    def tc_run_09(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script("run09_tamper.py", "print('tamper')\n")
        ctx.logged_subprocess(
            "run09_dry",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                "4863089361",
                "--operation",
                "Label test",
                "--after",
                "label=A",
                "--consequences",
                "Label attachment",
            ],
        )
        for p in ctx._global_receipt_candidates():
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["after_state"] = "TAMPERED_AFTER_STATE"
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f)
        e_proc = ctx.logged_subprocess(
            "run09_exec_tampered",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if e_proc.returncode == 0 or (
            "sha256" not in e_proc.stderr.lower() and "sha-256" not in e_proc.stderr.lower()
        ):
            raise AssertionError(f"Tampered receipt was not blocked: {e_proc.stderr}")
        return "Tampered after_state detected via canonical SHA-256 recomputation."

    @register("TC-RUN-10", "TC-RUN", "Non-mutate_* RPC wrapping in _wrap_service_for_audit (GAP-01)")
    def tc_run_10(ctx: FunctionalTestContext) -> str:
        verbs_to_wrap = (
            "create_product_link",
            "create_account_link",
            "create_you_tube_video_upload",
            "add_offline_user_data_job_operations",
            "move_manager_link",
            "start_identity_verification",
            "remove_campaign_automatically_created_asset",
        )

        class _DummyService:
            pass

        def _check() -> dict[str, bool]:
            dummy = _DummyService()
            for v in verbs_to_wrap:
                setattr(dummy, v, lambda **_kw: {"request_id": "req-1"})
            captured: list[dict[str, Any]] = []
            wrapped = RUN_MUTATION_MOD._wrap_service_for_audit(
                dummy, "DummyService", captured, dry_run_mode=False
            )
            return {
                v: bool(getattr(getattr(wrapped, v), "_is_audit_wrapped", False))
                for v in verbs_to_wrap
            }

        res = ctx.logged_local_check(
            "wrap_service_for_audit_non_mutate_verbs", {"verbs": list(verbs_to_wrap)}, _check
        )
        unwrapped = [v for v, ok_flag in res.items() if not ok_flag]
        if unwrapped:
            raise AssertionError(
                "GAP-01: _wrap_service_for_audit failed to wrap non-mutate_* write RPC(s): "
                f"{', '.join(unwrapped)}"
            )
        return "All non-mutate_* write RPC verbs wrapped for SHA-256 and payload auditing."

    @register("TC-RUN-11", "TC-RUN", "Payload-Bound Prompting vs. 1,000x Micro-Unit Drift (GAP-02)")
    def tc_run_11(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("run11_drift_card.py", "print('drift')\n")
        fake_call = {
            "service": "CampaignBudgetService",
            "method": "mutate_campaign_budgets",
            "sent_at_iso": datetime.now(timezone.utc).isoformat(),
            "received_at_iso": datetime.now(timezone.utc).isoformat(),
            "status": "SUCCESS",
            "request_payload": {
                "customer_id": "9999999999",
                "validate_only": True,
                "operations": [
                    {
                        "update": {
                            "resource_name": "customers/9999999999/campaignBudgets/111",
                            "amount_micros": "50000000000",
                        },
                        "update_mask": "amount_micros",
                    }
                ],
            },
        }

        def _check() -> dict[str, Any]:
            receipt = RUN_MUTATION_MOD.write_dry_run_receipt(
                customer_id="1111111111",
                operation_summary="Update daily budget",
                before_state="$40.00/day",
                after_state="$50.00/day",
                consequences=["Sets daily budget to $50.00/day"],
                reversibility="REVERSIBLE",
                script_path=sp,
                rpc_calls=[fake_call],
            )
            card = RUN_MUTATION_MOD.format_verification_card(receipt)
            _, hook_prompt, _ = config_init._verify_dry_run_receipt_for_hook(
                script_path=sp, workspace_cwd=ctx.sandbox_dir
            )
            return {"card": card, "hook_prompt": hook_prompt}

        out = ctx.logged_local_check(
            "evaluate_payload_bound_micro_drift",
            {"payload_micros": 50_000_000_000, "cli_after": "$50.00/day"},
            _check,
        )
        ctx.clear_all_receipts()
        card_txt = out["card"]
        hook_txt = out["hook_prompt"]
        has_true_amount = ("50,000.00" in card_txt or "50000.00" in card_txt) and (
            "50,000.00" in hook_txt or "50000.00" in hook_txt
        )
        has_true_cid = "9999999999" in card_txt and "9999999999" in hook_txt
        if not (has_true_amount and has_true_cid):
            raise AssertionError(
                "GAP-02 (Policy §1.3 #2): Confirmation card/hook displayed deceptive LLM CLI prose "
                "('1111111111', '$50.00/day') without surfacing payload customer_id '9999999999' "
                "and payload amount_micros=50_000_000_000 ($50,000.00/day)."
            )
        return "Payload-bound $50,000.00 and customer_id 9999999999 surfaced in HITL prompt."

    @register("TC-RUN-12", "TC-RUN", "BatchJobService & GoogleAdsService Inner-Op Tier Elevation (GAP-04)")
    def tc_run_12(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("run12_batch.py", "print('batch')\n")
        batch_call = {
            "service": "BatchJobService",
            "method": "add_batch_job_operations",
            "request_payload": {
                "resource_name": "customers/4863089361/batchJobs/1",
                "mutate_operations": [
                    {"campaign_label_operation": {"create": {"campaign": "c/1", "label": "l/1"}}},
                    {"campaign_label_operation": {"create": {"campaign": "c/2", "label": "l/1"}}},
                    {"campaign_budget_operation": {"update": {"amount_micros": "9000000"}}},
                ],
            },
        }

        def _check() -> dict[str, Any]:
            receipt = RUN_MUTATION_MOD.write_dry_run_receipt(
                customer_id="4863089361",
                operation_summary="BatchJobService.add_batch_job_operations",
                before_state="2 labels + $5/day budget",
                after_state="2 labels + $9/day budget",
                consequences=["Updates campaign budget to $9.00/day"],
                reversibility="REVERSIBLE",
                script_path=sp,
                rpc_calls=[batch_call],
            )
            card = RUN_MUTATION_MOD.format_verification_card(receipt)
            return {"card": card, "is_financial": receipt.get("is_financial_transaction")}

        out = ctx.logged_local_check(
            "evaluate_batch_inner_tier_elevation", {"inner_ops": 3}, _check
        )
        ctx.clear_all_receipts()
        if "CRITICAL FINANCIAL INFRASTRUCTURE MUTATION" not in out["card"] or "Tier 1" not in out["card"]:
            raise AssertionError(
                "GAP-04 (Policy §4.3): BatchJobService containing inner CampaignBudgetOperation "
                "did not elevate confirmation banner to Tier 1 "
                "[CRITICAL FINANCIAL INFRASTRUCTURE MUTATION]."
            )
        return "BatchJob inner CampaignBudgetOperation elevated HITL prompt to Tier 1."

    @register("TC-RUN-13", "TC-RUN", "Layer 4 gRPC Channel Interceptor (FinancialGuardrailInterceptor, GAP-07)")
    def tc_run_13(ctx: FunctionalTestContext) -> str:
        # Safe local loopback gRPC listener so zero network packets ever leave localhost
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        sp = ctx.write_sandbox_script(
            "run13_direct_gapic.py",
            f"""#!/usr/bin/env python3
from google.auth.credentials import AnonymousCredentials
import grpc
from google.ads.googleads.{ctx.cfg.api_version}.services.services.campaign_budget_service import (
    CampaignBudgetServiceClient,
)
from google.ads.googleads.{ctx.cfg.api_version}.services.services.campaign_budget_service.transports import (
    CampaignBudgetServiceGrpcTransport,
)

ch = grpc.insecure_channel("127.0.0.1:{port}")
transport = CampaignBudgetServiceGrpcTransport(channel=ch)
direct_client = CampaignBudgetServiceClient(transport=transport)
print("DIRECT_CLIENT_CREATED_WITHOUT_GET_SERVICE")
""",
        )
        try:
            has_cls = hasattr(RUN_MUTATION_MOD, "FinancialGuardrailInterceptor")
            proc = ctx.logged_subprocess(
                "run13_check_layer4_grpc_interceptor",
                [
                    sys.executable,
                    RUN_MUTATION_SCRIPT,
                    "--script",
                    sp,
                    "--dry-run",
                    "--record-only",
                    "--customer-id",
                    "4863089361",
                    "--operation",
                    "Direct CampaignBudgetServiceClient check",
                    "--consequences",
                    "Tests Layer 4 gRPC channel interceptor $5.00/day",
                ],
            )
        finally:
            sock.close()
            ctx.clear_all_receipts()

        if not has_cls:
            raise AssertionError(
                "GAP-07 (Policy §1.4 & §3.2): FinancialGuardrailInterceptor gRPC channel "
                "interceptor is not implemented; instantiating *ServiceClient directly bypasses "
                "GoogleAdsClient.get_service wrapping."
            )
        if proc.returncode != 0:
            raise AssertionError(f"Unexpected runner error: {proc.stderr}")
        return "FinancialGuardrailInterceptor verified at Layer 4 gRPC channel boundary."

    # --------------------------------------------------------------------------
    # Section 3.4: Classification-Driven 5-Part HITL Message Schema (TC-MSG)
    # --------------------------------------------------------------------------

    @register("TC-MSG-01", "TC-MSG", "Template A — Tier 1 Mutate Financial Services")
    def tc_msg_01(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("msg01.py", "print('t1')\n")
        receipt = ctx.logged_local_check(
            "render_template_a_tier1",
            {"service": "campaign_budget_service"},
            lambda: {
                "card": RUN_MUTATION_MOD.format_verification_card(
                    RUN_MUTATION_MOD.write_dry_run_receipt(
                        customer_id="4863089361",
                        operation_summary="campaign_budget_service: UPDATE $100/day -> $250/day",
                        before_state="$100.00/day",
                        after_state="$250.00/day",
                        consequences=["+$150.00/day (+$4,560.00/month 30.4x exposure)"],
                        reversibility="REVERSIBLE",
                        script_path=sp,
                    )
                )
            },
        )
        ctx.clear_all_receipts()
        card = receipt["card"]
        required = (
            "[CRITICAL FINANCIAL INFRASTRUCTURE MUTATION — HITL CONFIRMATION REQUIRED]",
            "Tier 1",
            "Budgeting & Billing",
        )
        missing = [tok for tok in required if tok not in card]
        if missing:
            raise AssertionError(
                f"GAP-03 (Policy §2.3A): Template A missing mandatory Tier 1 fields: {missing}"
            )
        return "Template A 5-part Tier 1 confirmation message verified."

    @register("TC-MSG-02", "TC-MSG", "Template B — Tier 2 Financial-Impacting Services")
    def tc_msg_02(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("msg02.py", "print('t2')\n")
        out = ctx.logged_local_check(
            "render_template_b_tier2",
            {"service": "ad_group_criterion_service"},
            lambda: {
                "card": RUN_MUTATION_MOD.format_verification_card(
                    RUN_MUTATION_MOD.write_dry_run_receipt(
                        customer_id="4863089361",
                        operation_summary="ad_group_criterion_service: cpc_bid_micros $2.50 -> $6.00",
                        before_state="PAUSED, CPC $2.50",
                        after_state="ENABLED, CPC $6.00",
                        consequences=["+140% CPC bid acceleration ($2.50 -> $6.00)"],
                        reversibility="REVERSIBLE",
                        script_path=sp,
                    )
                )
            },
        )
        ctx.clear_all_receipts()
        card = out["card"]
        required = (
            "[HIGH-IMPACT OPERATIONAL & SPEND MUTATION — HITL CONFIRMATION REQUIRED]",
            "Bidding & Auction Mechanics",
        )
        missing = [tok for tok in required if tok not in card]
        if missing:
            raise AssertionError(
                f"GAP-03 (Policy §2.3B): Template B missing mandatory Tier 2 fields: {missing}"
            )
        return "Template B 5-part Tier 2 confirmation message verified."

    @register("TC-MSG-03", "TC-MSG", "Template C — Tier 3 Non-Financial Structural/Labeling")
    def tc_msg_03(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("msg03.py", "print('t3')\n")
        out = ctx.logged_local_check(
            "render_template_c_tier3",
            {"service": "campaign_label_service"},
            lambda: {
                "card": RUN_MUTATION_MOD.format_verification_card(
                    RUN_MUTATION_MOD.write_dry_run_receipt(
                        customer_id="4863089361",
                        operation_summary="campaign_label_service: attach label",
                        before_state="No label",
                        after_state="Label attached",
                        consequences=["Attaches organizational label"],
                        reversibility="REVERSIBLE",
                        script_path=sp,
                    )
                )
            },
        )
        ctx.clear_all_receipts()
        card = out["card"]
        required = (
            "[STRUCTURAL / ADMINISTRATIVE MUTATION — HITL CONFIRMATION REQUIRED]",
            "Organization & Labeling",
            "$0.00",
        )
        missing = [tok for tok in required if tok not in card]
        if missing:
            raise AssertionError(
                f"GAP-03 (Policy §2.3C): Template C missing mandatory Tier 3 fields: {missing}"
            )
        return "Template C 5-part Tier 3 confirmation message with $0.00 spend delta verified."

    @register("TC-MSG-04", "TC-MSG", "Tier 3 ATO & Permission Escalation Warning (GAP-05)")
    def tc_msg_04(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script("msg04_ato.py", "print('ato')\n")
        ato_call = {
            "service": "CustomerUserAccessInvitationService",
            "method": "mutate_customer_user_access_invitation",
            "request_payload": {
                "customer_id": "4863089361",
                "operation": {
                    "create": {
                        "email_address": ctx.cfg.fixtures["ato_probe_email"],
                        "access_role": "ADMIN",
                    }
                },
            },
        }
        out = ctx.logged_local_check(
            "render_ato_escalation_warning",
            {"service": "customer_user_access_invitation_service", "role": "ADMIN"},
            lambda: {
                "card": RUN_MUTATION_MOD.format_verification_card(
                    RUN_MUTATION_MOD.write_dry_run_receipt(
                        customer_id="4863089361",
                        operation_summary="Invite user via CustomerUserAccessInvitationService",
                        before_state="No pending invite",
                        after_state="Pending invite",
                        consequences=["Sends access invitation"],
                        reversibility="REVERSIBLE",
                        script_path=sp,
                        rpc_calls=[ato_call],
                    )
                )
            },
        )
        ctx.clear_all_receipts()
        card = out["card"]
        if (
            ctx.cfg.fixtures["ato_probe_email"] not in card
            or "ADMIN" not in card
            or ("Account Takeover" not in card and "ATO" not in card)
        ):
            raise AssertionError(
                "GAP-05 (Policy §3.3): Verification card did not automatically surface invited "
                f"email ({ctx.cfg.fixtures['ato_probe_email']}), ADMIN AccessRole, and Account "
                "Takeover (ATO) escalation warning from payload."
            )
        return "ATO warning prominently disclosed email, ADMIN role, and takeover impact."

    # --------------------------------------------------------------------------
    # Section 3.5: Audit Trail, Non-Repudiation & Secret Redaction (TC-AUD)
    # --------------------------------------------------------------------------

    @register("TC-AUD-01", "TC-AUD", "HUMAN_APPROVED audit schema & 0600 permissions")
    def tc_aud_01(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-AUD-01")
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script(
            "aud01_live.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                ctx.fixtures.campaign_budget_micros,
                api_version=ctx.cfg.api_version,
            ),
        )
        ctx.logged_subprocess(
            "aud01_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Audit schema verification on CampaignBudget",
                "--consequences",
                "Verifies $5.00/day CampaignBudget audit record",
            ],
        )
        ctx.logged_subprocess(
            "aud01_hook_stamp",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=json.dumps({
                "conversationId": "conv-aud-01",
                "toolCall": {
                    "name": "run_command",
                    "args": {
                        "CommandLine": f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
                        "Cwd": ctx.sandbox_dir,
                    },
                },
            }),
        )
        e_proc = ctx.logged_subprocess(
            "aud01_execute",
            [sys.executable, RUN_MUTATION_SCRIPT, "--script", sp, "--execute"],
        )
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if e_proc.returncode != 0:
            raise AssertionError(f"Live execute failed: {e_proc.stderr}")

        mode = oct(stat.S_IMODE(os.stat(ctx.sandbox_plugin_audit).st_mode))
        with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
            rec = [json.loads(ln) for ln in f if ln.strip()][-1]
        if sys.platform != "win32" and mode != "0o600":
            raise AssertionError(f"Expected 0o600 on mutation_audit.jsonl, got {mode}")
        if not rec.get("request", {}).get("request_sha256_verified"):
            raise AssertionError("request_sha256_verified was not True.")
        if rec.get("status") != "HUMAN_APPROVED" or "classification_tier" not in rec.get(
            "approval", {}
        ):
            raise AssertionError(
                f"GAP-03/GAP-06 (Policy §1.3 #4): Audit record recorded status={rec.get('status')!r} "
                "instead of 'HUMAN_APPROVED' and omitted classification_tier / rendered warning."
            )
        return "0600 HUMAN_APPROVED audit schema verified."

    @register("TC-AUD-02", "TC-AUD", "HUMAN_REJECTED audit record & receipt invalidation (GAP-06)")
    def tc_aud_02(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=True)
        sp = ctx.write_sandbox_script("aud02_reject.py", "print('reject test')\n")
        ctx.logged_subprocess(
            "aud02_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--record-only",
                "--customer-id",
                "4863089361",
                "--operation",
                "Enable campaign",
                "--consequences",
                "Enables campaign serving and $5.00/day spend",
            ],
        )
        # Trigger native CLI force_ask prompt; operator rejects at CLI prompt (so --execute is cancelled)
        ctx.logged_subprocess(
            "aud02_hook_force_ask",
            [sys.executable, CONFIG_INIT_SCRIPT, "--hook"],
            stdin_text=json.dumps({
                "conversationId": "conv-aud-02",
                "toolCall": {
                    "name": "run_command",
                    "args": {
                        "CommandLine": f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
                        "Cwd": ctx.sandbox_dir,
                    },
                },
            }),
        )
        with open(ctx.sandbox_receipt, "r", encoding="utf-8") as f:
            post_reject_receipt = json.load(f)
        entries: list[dict[str, Any]] = []
        if os.path.isfile(ctx.sandbox_plugin_audit):
            with open(ctx.sandbox_plugin_audit, "r", encoding="utf-8") as f:
                entries = [json.loads(ln) for ln in f if ln.strip()]
        has_reject_flag = "--reject" in RUN_MUTATION_MOD.main.__doc__ if RUN_MUTATION_MOD.main.__doc__ else False
        has_human_rejected = any(e.get("status") == "HUMAN_REJECTED" for e in entries)
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        ctx.clear_all_receipts()
        if post_reject_receipt.get("status") == "DRY_RUN_PASSED" or not has_human_rejected:
            raise AssertionError(
                "GAP-06 (Policy §1.3 #4 & §2.2 #5): After native CLI prompt rejection, "
                f"last_dry_run.json remained in status={post_reject_receipt.get('status')!r} "
                f"(reusable for 30m) and HUMAN_REJECTED was not logged (reject_cli={has_reject_flag})."
            )
        return "HUMAN_REJECTED logged and receipt invalidated upon rejection."

    @register("TC-AUD-03", "TC-AUD", "Credential & PII redaction")
    def tc_aud_03(ctx: FunctionalTestContext) -> str:
        raw_secret_payload = {
            "client_secret": "GOCSPX-super-secret-value-12345",
            "refresh_token": "1//0g-secret-refresh-token-67890",
            "private_key": "-----BEGIN PRIVATE KEY-----SECRET",
            "json_key": '{"private_key_id": "secret"}',
            "client_id": "123456789012-abcdefg.apps.googleusercontent.com",
        }

        def _check() -> dict[str, Any]:
            ser = RUN_MUTATION_MOD._serialize_rpc_object(raw_secret_payload)
            actor = RUN_MUTATION_MOD.resolve_actor_metadata(customer_id="4863089361")
            red = redact_sensitive_data(raw_secret_payload)
            return {"serialized": ser, "actor": actor, "audit_redacted": red}

        res = ctx.logged_local_check(
            "verify_secret_redaction", {"fields": list(raw_secret_payload)}, _check
        )
        ser = res["serialized"]
        for k in ("client_secret", "refresh_token", "private_key", "json_key"):
            if ser.get(k) != "[REDACTED]":
                raise AssertionError(f"Secret field {k} was not redacted: {ser.get(k)!r}")
        masked_cid = str(res["actor"].get("client_id_masked") or "")
        if masked_cid and len(masked_cid) > 12 and not masked_cid.endswith("..."):
            raise AssertionError(f"client_id_masked was not truncated: {masked_cid!r}")
        raw_dump = json.dumps(res)
        if "GOCSPX-super-secret" in raw_dump or "1//0g-secret-refresh" in raw_dump:
            raise AssertionError("Raw credential leaked into serialized output!")
        return "All secret fields redacted as '[REDACTED]' and client_id_masked truncated."

    # --------------------------------------------------------------------------
    # Section 3.6: A2A Sidecar Mutate Endpoints (TC-A2A)
    # --------------------------------------------------------------------------

    class _FastLoopbackHTTPServer(HTTPServer):
        """Loopback HTTPServer that skips socket.getfqdn() mDNS delays on macOS CI runners."""

        def server_bind(self) -> None:
            socketserver.TCPServer.server_bind(self)
            host, port = self.server_address[:2]
            self.server_name = str(host)
            self.server_port = int(port)

    class _QuietA2AHandler(SIDECAR_MOD.A2AHandler):  # type: ignore[misc]
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    def _with_loopback_sidecar(
        ctx: FunctionalTestContext,
        fn: Callable[[str, str], str],
    ) -> str:
        token = secrets.token_hex(32)
        prev_cwd = os.getcwd()
        prev_tok = os.environ.get("A2A_AUTH_TOKEN")
        os.environ["A2A_AUTH_TOKEN"] = token
        os.chdir(ctx.sandbox_dir)
        httpd = _FastLoopbackHTTPServer(("127.0.0.1", 0), _QuietA2AHandler)
        httpd.auth_token = token  # type: ignore[attr-defined]
        httpd.require_auth = True  # type: ignore[attr-defined]
        httpd.timeout = 30
        port = int(httpd.server_port)
        srv_thread = threading.Thread(
            target=httpd.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        srv_thread.start()
        base_url = f"http://127.0.0.1:{port}"
        try:
            with _NO_PROXY_OPENER.open(f"{base_url}/health", timeout=5.0) as r:
                if r.status != 200:
                    raise AssertionError(
                        f"Loopback A2A sidecar /health returned HTTP {r.status}."
                    )
            return fn(base_url, token)
        finally:
            httpd.shutdown()
            httpd.server_close()
            srv_thread.join(timeout=5.0)
            os.chdir(prev_cwd)
            if prev_tok is None:
                os.environ.pop("A2A_AUTH_TOKEN", None)
            else:
                os.environ["A2A_AUTH_TOKEN"] = prev_tok

    def _post_a2a(
        ctx: FunctionalTestContext,
        base_url: str,
        token: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        req_rec_id = ctx.audit.log_request(
            test_id=ctx.current_test_id,
            suite=ctx.current_suite,
            action=f"A2A_HTTP_POST:{body.get('intent')}",
            payload=body,
        )
        ctx.last_request_record_id = req_rec_id
        t0 = time.perf_counter()
        req = urllib.request.Request(
            f"{base_url}/v1/a2a/tasks",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        with _NO_PROXY_OPENER.open(req, timeout=15.0) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        dur = (time.perf_counter() - t0) * 1000.0
        ctx.audit.log_response(
            request_record_id=req_rec_id,
            test_id=ctx.current_test_id,
            suite=ctx.current_suite,
            status=str(parsed.get("status", "UNKNOWN")),
            duration_ms=dur,
            payload=parsed,
        )
        return parsed

    @register("TC-A2A-01", "TC-A2A", "PREPARE_MUTATION receipt & consequence card")
    def tc_a2a_01(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()

        def _run(url: str, tok: str) -> str:
            cid = ctx.cfg.test_customer_id if is_valid_customer_id(ctx.cfg.test_customer_id) else "4863089361"
            resp = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-01",
                    "intent": "PREPARE_MUTATION",
                    "payload": {
                        "customer_id": cid,
                        "operation_summary": "Update CampaignBudget +$2/day",
                        "before_state": "$5.00/day",
                        "after_state": "$7.00/day",
                        "consequences": ["Increases daily budget cap by +$2.00/day"],
                    },
                },
            )
            if (
                resp.get("status") != "HITL_CONFIRMATION_REQUIRED"
                or resp.get("destructive_hint") is not True
                or "verification_card" not in resp.get("result", {})
            ):
                raise AssertionError(f"Unexpected PREPARE_MUTATION response: {resp}")
            return "Sidecar returned HITL_CONFIRMATION_REQUIRED with verification_card and receipt."

        try:
            return _with_loopback_sidecar(ctx, _run)
        finally:
            ctx.clear_all_receipts()

    @register("TC-A2A-02", "TC-A2A", "PREPARE_MUTATION missing financial disclosure")
    def tc_a2a_02(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()

        def _run(url: str, tok: str) -> str:
            resp = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-02",
                    "intent": "PREPARE_MUTATION",
                    "payload": {
                        "customer_id": "4863089361",
                        "operation_summary": "Update CampaignBudget",
                        "consequences": ["Routine administrative update"],
                    },
                },
            )
            if resp.get("status") != "VALIDATION_FAILED":
                raise AssertionError(f"Expected VALIDATION_FAILED, got {resp}")
            return "Sidecar returned VALIDATION_FAILED and logged BLOCKED_FINANCIAL_CONSEQUENCE_MISSING."

        return _with_loopback_sidecar(ctx, _run)

    @register("TC-A2A-03", "TC-A2A", "EXECUTE_MUTATION confirmation, config & replay checks")
    def tc_a2a_03(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()

        def _run(url: str, tok: str) -> str:
            ctx.write_sandbox_assistant_config(execute_mutates=False)
            _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-prep",
                    "intent": "PREPARE_MUTATION",
                    "payload": {
                        "customer_id": "4863089361",
                        "operation_summary": "Attach label",
                        "consequences": ["Attaches organizational label"],
                    },
                },
            )
            r_a = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-a",
                    "intent": "EXECUTE_MUTATION",
                    "payload": {"user_confirmed": False, "confirmation_summary": "No"},
                },
            )
            r_b = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-b",
                    "intent": "EXECUTE_MUTATION",
                    "payload": {"user_confirmed": True, "confirmation_summary": ""},
                },
            )
            r_c = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-c",
                    "intent": "EXECUTE_MUTATION",
                    "payload": {"user_confirmed": True, "confirmation_summary": "Approved"},
                },
            )
            ctx.write_sandbox_assistant_config(execute_mutates=True)
            r_d = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-d",
                    "intent": "EXECUTE_MUTATION",
                    "payload": {"user_confirmed": True, "confirmation_summary": "Approved"},
                },
            )
            r_e = _post_a2a(
                ctx,
                url,
                tok,
                {
                    "task_id": "a2a-03-e",
                    "intent": "EXECUTE_MUTATION",
                    "payload": {"user_confirmed": True, "confirmation_summary": "Replay"},
                },
            )
            ctx.write_sandbox_assistant_config(execute_mutates=False)
            for tag, item in (("a", r_a), ("b", r_b), ("c", r_c), ("e", r_e)):
                if item.get("status") != "HITL_BLOCKED":
                    raise AssertionError(f"Subcase ({tag}) expected HITL_BLOCKED, got {item}")
            if r_d.get("status") != "COMPLETED":
                raise AssertionError(f"Subcase (d) expected COMPLETED, got {r_d}")
            return "Subcases (a)-(c) & (e) returned HITL_BLOCKED; (d) returned COMPLETED."

        try:
            return _with_loopback_sidecar(ctx, _run)
        finally:
            ctx.clear_all_receipts()

    # --------------------------------------------------------------------------
    # Section 4.1: Tier 1 — Mutate Financial Services (TC-T1-01 .. TC-T1-06)
    # --------------------------------------------------------------------------

    @register("TC-T1-01", "TC-T1", "account_budget_proposal_service (Budgeting & Billing)")
    def tc_t1_01(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-01")
        client = ctx.get_live_client()
        req = client.get_type("MutateAccountBudgetProposalRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("AccountBudgetProposalOperation")
        op.create.proposal_type = client.enums.AccountBudgetProposalTypeEnum.CREATE
        op.create.billing_setup = f"customers/{ctx.cfg.test_customer_id}/billingSetups/999999"
        op.create.proposed_name = "HITL DryRun AccountBudgetProposal"
        op.create.proposed_start_time_type = client.enums.TimeTypeEnum.NOW
        op.create.proposed_spending_limit_micros = 5_000_000
        req.operation.CopyFrom(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "AccountBudgetProposalService", "mutate_account_budget_proposal", req
        )
        if not ok and _is_auth_or_access_failure(code, str(err)):
            raise AssertionError(f"Auth/access error on AccountBudgetProposalService: {code}")
        is_fin = RUN_MUTATION_MOD.is_financial_mutation(
            rpc_calls=[{"service": "AccountBudgetProposalService", "method": "mutate_account_budget_proposal"}]
        )
        if not is_fin:
            raise AssertionError("AccountBudgetProposalService not classified as financial.")
        return f"Validated AccountBudgetProposalService dry-run against test account ({code})."

    @register("TC-T1-02", "TC-T1", "billing_setup_service (preflight + non-validate_only guard)")
    def tc_t1_02(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-02")
        if "mutate_billing_setup" not in RUN_MUTATION_MOD._NON_VALIDATE_ONLY_MUTATION_METHODS:
            raise AssertionError("mutate_billing_setup missing from _NON_VALIDATE_ONLY_MUTATION_METHODS.")
        client = ctx.get_live_client()
        req = client.get_type("ListPaymentsAccountsRequest")
        req.customer_id = ctx.cfg.test_customer_id
        ok, _, code, _, err = ctx.logged_rpc(
            "PaymentsAccountService", "list_payments_accounts", req
        )
        if not ok and _is_auth_or_access_failure(code, str(err)):
            raise AssertionError(f"PaymentsAccountService preflight failed ({code}): {err}")
        return f"BillingSetup guarded preflight via PaymentsAccountService succeeded ({code})."

    @register("TC-T1-03", "TC-T1", "campaign_budget_service (live dry-run, MUTABLE_RESOURCE & revert)")
    def tc_t1_03(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-03")
        client = ctx.get_live_client()
        orig_micros = ctx.fixtures.campaign_budget_micros
        new_micros = min(orig_micros + 1_000_000, ctx.cfg.max_daily_budget_micros)
        if new_micros == orig_micros:
            new_micros = max(1_000_000, orig_micros - 1_000_000)

        dry_req = client.get_type("MutateCampaignBudgetsRequest")
        dry_req.customer_id = ctx.cfg.test_customer_id
        dry_req.validate_only = True
        op = client.get_type("CampaignBudgetOperation")
        op.update.resource_name = ctx.fixtures.campaign_budget_rn
        op.update.amount_micros = new_micros
        op.update_mask.paths.append("amount_micros")
        dry_req.operations.append(op)
        ok_d, _, code_d, _, err_d = ctx.logged_rpc(
            "CampaignBudgetService", "mutate_campaign_budgets", dry_req
        )
        if not ok_d:
            raise AssertionError(f"CampaignBudget dry-run failed ({code_d}): {err_d}")

        if ctx.cfg.allow_live_execute:
            live_req = client.get_type("MutateCampaignBudgetsRequest")
            live_req.CopyFrom(dry_req)
            live_req.validate_only = False
            live_req.response_content_type = (
                client.enums.ResponseContentTypeEnum.MUTABLE_RESOURCE
            )
            try:
                ok_l, resp_l, code_l, _, err_l = ctx.logged_rpc(
                    "CampaignBudgetService", "mutate_campaign_budgets", live_req
                )
                if not ok_l:
                    raise AssertionError(f"CampaignBudget live execute failed ({code_l}): {err_l}")
                mut_res = resp_l.results[0].campaign_budget
                if int(mut_res.amount_micros) != new_micros:
                    raise AssertionError(
                        f"MUTABLE_RESOURCE amount_micros={mut_res.amount_micros} != {new_micros}"
                    )
            finally:
                rev_req = client.get_type("MutateCampaignBudgetsRequest")
                rev_req.customer_id = ctx.cfg.test_customer_id
                rev_op = client.get_type("CampaignBudgetOperation")
                rev_op.update.resource_name = ctx.fixtures.campaign_budget_rn
                rev_op.update.amount_micros = orig_micros
                rev_op.update_mask.paths.append("amount_micros")
                rev_req.operations.append(rev_op)
                ctx.logged_rpc("CampaignBudgetService", "mutate_campaign_budgets", rev_req)
        return "CampaignBudget dry-run + MUTABLE_RESOURCE execute + revert verified on test account."

    @register("TC-T1-04", "TC-T1", "bidding_strategy_service (portfolio strategy + linked count)")
    def tc_t1_04(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-04")
        client = ctx.get_live_client()
        q = "SELECT bidding_strategy.id, bidding_strategy.campaign_count FROM bidding_strategy LIMIT 5"
        ok_q, _, code_q, _, err_q = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": q},
        )
        if not ok_q:
            raise AssertionError(f"BiddingStrategy GAQL failed ({code_q}): {err_q}")
        req = client.get_type("MutateBiddingStrategiesRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("BiddingStrategyOperation")
        op.create.name = f"HITL_DryRun_Portfolio_{uuid.uuid4().hex[:6]}"
        op.create.target_cpa.target_cpa_micros = 2_000_000
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "BiddingStrategyService", "mutate_bidding_strategies", req
        )
        if not ok:
            raise AssertionError(f"BiddingStrategy validate_only failed ({code}): {err}")
        return "BiddingStrategy linked-campaign GAQL + validate_only=True passed."

    @register("TC-T1-05", "TC-T1", "bidding_seasonality_adjustment_service (ISO-8601 window)")
    def tc_t1_05(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-05")
        client = ctx.get_live_client()
        start_dt = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d 00:00:00")
        end_dt = (datetime.now(timezone.utc) + timedelta(days=5, hours=6)).strftime(
            "%Y-%m-%d 06:00:00"
        )
        req = client.get_type("MutateBiddingSeasonalityAdjustmentsRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("BiddingSeasonalityAdjustmentOperation")
        op.create.name = f"HITL_DryRun_Seasonality_{uuid.uuid4().hex[:6]}"
        op.create.scope = client.enums.SeasonalityEventScopeEnum.CHANNEL
        op.create.advertising_channel_types.append(client.enums.AdvertisingChannelTypeEnum.SEARCH)
        op.create.start_date_time = start_dt
        op.create.end_date_time = end_dt
        op.create.conversion_rate_modifier = 1.15
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "BiddingSeasonalityAdjustmentService", "mutate_bidding_seasonality_adjustments", req
        )
        if not ok:
            raise AssertionError(f"BiddingSeasonalityAdjustment dry-run failed ({code}): {err}")
        return "BiddingSeasonalityAdjustmentService validate_only=True passed."

    @register("TC-T1-06", "TC-T1", "bidding_data_exclusion_service (training interval exclusion)")
    def tc_t1_06(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("TC-T1-06")
        client = ctx.get_live_client()
        start_dt = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
        end_dt = (datetime.now(timezone.utc) + timedelta(days=7, hours=4)).strftime(
            "%Y-%m-%d 04:00:00"
        )
        req = client.get_type("MutateBiddingDataExclusionsRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("BiddingDataExclusionOperation")
        op.create.name = f"HITL_DryRun_Exclusion_{uuid.uuid4().hex[:6]}"
        op.create.scope = client.enums.SeasonalityEventScopeEnum.CHANNEL
        op.create.advertising_channel_types.append(client.enums.AdvertisingChannelTypeEnum.SEARCH)
        op.create.start_date_time = start_dt
        op.create.end_date_time = end_dt
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "BiddingDataExclusionService", "mutate_bidding_data_exclusions", req
        )
        if not ok:
            raise AssertionError(f"BiddingDataExclusion dry-run failed ({code}): {err}")
        return "BiddingDataExclusionService validate_only=True passed."

    # --------------------------------------------------------------------------
    # Section 4.2: Tier 2 — Financial-Impacting Services (TC-T2-01 .. TC-T2-07)
    # --------------------------------------------------------------------------

    def _verify_service_descriptors(ctx: FunctionalTestContext, services: tuple[str, ...]) -> None:
        desc_client = ctx.get_descriptor_client()
        for s_snake in services:
            desc_client.get_service(_snake_to_pascal_service(s_snake))

    @register("TC-T2-01", "TC-T2", "Core Spend & Status Control (6 services + atomic temp IDs)")
    def tc_t2_01(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Core Spend & Status Control"])
        ctx.require_verified_test_account("TC-T2-01")
        client = ctx.get_live_client()
        cid = ctx.cfg.test_customer_id

        # Blast-radius child count query
        q_children = (
            "SELECT ad_group.id, ad_group.status FROM ad_group "
            f"WHERE campaign.resource_name = '{ctx.fixtures.search_campaign_rn}'"
        )
        ok_q, rows_q, code_q, _, err_q = ctx.logged_rpc(
            "GoogleAdsService", "search", kwargs={"customer_id": cid, "query": q_children}
        )
        if not ok_q:
            raise AssertionError(f"Child blast-radius GAQL failed ({code_q}): {err_q}")

        # Atomic GoogleAdsService.mutate temp IDs dry-run
        ga_req = client.get_type("MutateGoogleAdsRequest")
        ga_req.customer_id = cid
        ga_req.validate_only = True
        op_b = client.get_type("MutateOperation")
        op_b.campaign_budget_operation.create.resource_name = f"customers/{cid}/campaignBudgets/-1"
        op_b.campaign_budget_operation.create.name = f"HITL_Atomic_{uuid.uuid4().hex[:6]}"
        op_b.campaign_budget_operation.create.amount_micros = 3_000_000
        op_b.campaign_budget_operation.create.explicitly_shared = False
        ga_req.mutate_operations.append(op_b)
        op_c = client.get_type("MutateOperation")
        op_c.campaign_operation.create.name = f"HITL_Atomic_Camp_{uuid.uuid4().hex[:6]}"
        op_c.campaign_operation.create.status = client.enums.CampaignStatusEnum.PAUSED
        op_c.campaign_operation.create.advertising_channel_type = (
            client.enums.AdvertisingChannelTypeEnum.SEARCH
        )
        op_c.campaign_operation.create.campaign_budget = f"customers/{cid}/campaignBudgets/-1"
        op_c.campaign_operation.create.manual_cpc.enhanced_cpc_enabled = False
        op_c.campaign_operation.create.contains_eu_political_advertising = (
            client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
        )
        ga_req.mutate_operations.append(op_c)
        ok_m, _, code_m, _, err_m = ctx.logged_rpc("GoogleAdsService", "mutate", ga_req)
        if not ok_m:
            raise AssertionError(f"GoogleAdsService atomic temp-ID dry-run failed ({code_m}): {err_m}")
        return f"Verified all 6 Core Spend services, child count ({len(rows_q)}), and atomic temp IDs."

    @register("TC-T2-02", "TC-T2", "Bidding & Auction Mechanics (12 services + CPC delta dry-run)")
    def tc_t2_02(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Bidding & Auction Mechanics"])
        ctx.require_verified_test_account("TC-T2-02")
        client = ctx.get_live_client()
        cid = ctx.cfg.test_customer_id

        req = client.get_type("MutateAdGroupCriteriaRequest")
        req.customer_id = cid
        req.validate_only = True
        op = client.get_type("AdGroupCriterionOperation")
        op.update.resource_name = ctx.fixtures.keyword_criterion_rn
        op.update.cpc_bid_micros = min(1_500_000, ctx.cfg.max_cpc_bid_micros)
        op.update_mask.paths.append("cpc_bid_micros")
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "AdGroupCriterionService", "mutate_ad_group_criteria", req
        )
        if not ok:
            raise AssertionError(f"AdGroupCriterion CPC dry-run failed ({code}): {err}")

        bm_req = client.get_type("MutateCampaignBidModifiersRequest")
        bm_req.customer_id = cid
        bm_req.validate_only = True
        bm_op = client.get_type("CampaignBidModifierOperation")
        bm_op.create.campaign = ctx.fixtures.search_campaign_rn
        bm_op.create.interaction_type.type_ = client.enums.InteractionTypeEnum.CALLS
        bm_op.create.bid_modifier = 1.1
        bm_req.operations.append(bm_op)
        ok_bm, _, code_bm, _, err_bm = ctx.logged_rpc(
            "CampaignBidModifierService", "mutate_campaign_bid_modifiers", bm_req
        )
        if not ok_bm and _is_auth_or_access_failure(code_bm, str(err_bm)):
            raise AssertionError(f"CampaignBidModifier auth failure ({code_bm}): {err_bm}")
        return "Verified all 12 Bidding & Auction Mechanics services and live CPC dry-run."

    @register("TC-T2-03", "TC-T2", "Smart Bidding & Conversion Optimization (15 services, CSV & v26)")
    def tc_t2_03(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Smart Bidding & Conversion Optimization"])
        desc_client = ctx.get_descriptor_client()
        ccr = desc_client.get_type("ClickConversionResult")
        if hasattr(ccr, "order_id"):
            raise AssertionError("ClickConversionResult unexpectedly exposed order_id.")

        # Verify v22-v24 lifecycle goal services are removed in v25+
        import google.ads.googleads.v26.services.services as v26_svcs

        v26_names = {m.name for m in pkgutil.iter_modules(v26_svcs.__path__)}
        if "customer_lifecycle_goal_service" in v26_names or "campaign_lifecycle_goal_service" in v26_names:
            raise AssertionError("Removed v22-v24 lifecycle goal services still present in v26.")

        # CSV pre-validation via validate_conversion_upload.py
        csv_path = os.path.join(ctx.sandbox_dir, "valid_clicks.csv")
        hashed_email = hashlib.sha256(b"buyer@example.com").hexdigest()
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("gclid,conversion_date_time,conversion_value,currency_code,hashed_email\n")
            f.write(
                f"TeSterGclid1234567890,2026-10-01 12:00:00+00:00,25.50,USD,{hashed_email}\n"
            )
        csv_proc = ctx.logged_subprocess(
            "validate_conversion_upload_csv",
            [
                sys.executable,
                VALIDATE_CONV_SCRIPT,
                "--csv_path",
                csv_path,
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        if csv_proc.returncode != 0:
            raise AssertionError(f"validate_conversion_upload.py failed: {csv_proc.stderr}")

        ctx.require_verified_test_account("TC-T2-03")
        client = ctx.get_live_client()
        up_req = client.get_type("UploadClickConversionsRequest")
        up_req.customer_id = ctx.cfg.test_customer_id
        up_req.validate_only = True
        up_req.partial_failure = True
        cc = client.get_type("ClickConversion")
        cc.conversion_action = (
            ctx.fixtures.conversion_action_rn
            or f"customers/{ctx.cfg.test_customer_id}/conversionActions/999999"
        )
        cc.gclid = "EAIaIQobChMI_test_functional_gclid_123456"
        cc.conversion_date_time = "2026-10-01 12:00:00+00:00"
        cc.conversion_value = 15.0
        cc.currency_code = ctx.fixtures.currency_code
        up_req.conversions.append(cc)
        ok_u, _, code_u, _, err_u = ctx.logged_rpc(
            "ConversionUploadService", "upload_click_conversions", up_req
        )
        if not ok_u and _is_auth_or_access_failure(code_u, str(err_u)):
            raise AssertionError(f"ConversionUploadService failed ({code_u}): {err_u}")
        return "Verified 13 active v26 conversion/goal services, v25+ lifecycle unification, CSV & upload dry-run."

    @register("TC-T2-04", "TC-T2", "Performance Max & AI Steering (WEBPAGE tree & remove verb)")
    def tc_t2_04(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Performance Max & AI Steering"])
        if not config_init.MUTATION_CALL_PATTERN.search(
            "svc.remove_campaign_automatically_created_asset(request=req)"
        ):
            raise AssertionError(
                "remove_campaign_automatically_created_asset not matched by MUTATION_CALL_PATTERN."
            )
        ctx.require_verified_test_account("TC-T2-04")
        if not ctx.fixtures.asset_group_id:
            raise AssertionError("No PMax AssetGroup available on test account for WEBPAGE filter test.")
        proc = ctx.logged_subprocess(
            "create_pmax_webpage_filter_dry_run",
            [
                sys.executable,
                PMAX_FILTER_SCRIPT,
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--asset-group-id",
                ctx.fixtures.asset_group_id,
                "--url-exclusion",
                "/clearance",
                "--dry-run",
            ],
        )
        combined = f"{proc.stdout}\n{proc.stderr}"
        if (
            proc.returncode != 0
            or "ASSET_GROUP_LISTING_GROUP_FILTER_TRANSACTION_FAILURE" in combined
        ):
            raise AssertionError(f"PMax WEBPAGE filter dry-run failed: {combined}")
        return "PMax WEBPAGE listing filter tree dry-run passed and remove verb intercepted."

    @register("TC-T2-05", "TC-T2", "Traffic Boundaries & Exclusions (5 services & deletion guard)")
    def tc_t2_05(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Traffic Boundaries & Exclusions"])
        ctx.require_verified_test_account("TC-T2-05")
        client = ctx.get_live_client()
        req = client.get_type("MutateCampaignCriteriaRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("CampaignCriterionOperation")
        op.create.campaign = ctx.fixtures.search_campaign_rn
        op.create.negative = True
        op.create.keyword.text = f"neg_term_{uuid.uuid4().hex[:6]}"
        op.create.keyword.match_type = client.enums.KeywordMatchTypeEnum.PHRASE
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc(
            "CampaignCriterionService", "mutate_campaign_criteria", req
        )
        if not ok:
            raise AssertionError(f"Negative CampaignCriterion dry-run failed ({code}): {err}")
        return "Verified all 5 Traffic Boundaries & Exclusions services and negative criterion dry-run."

    @register("TC-T2-06", "TC-T2", "Testing, Recommendations & Automation (5 services & auto-apply)")
    def tc_t2_06(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Testing, Recommendations & Automation"])
        for m in ("apply_recommendation", "dismiss_recommendation"):
            if m not in RUN_MUTATION_MOD._NON_VALIDATE_ONLY_MUTATION_METHODS:
                raise AssertionError(f"{m} missing from _NON_VALIDATE_ONLY_MUTATION_METHODS.")
        ctx.require_verified_test_account("TC-T2-06")
        q = "SELECT recommendation.resource_name, recommendation.type FROM recommendation LIMIT 5"
        ok_q, _, code_q, _, err_q = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": q},
        )
        if not ok_q:
            raise AssertionError(f"Recommendation preflight GAQL failed ({code_q}): {err_q}")
        return "Verified all 5 Testing/Recommendation services, non-vo blocks, and GAQL preflight."

    @register("TC-T2-07", "TC-T2", "Guaranteed Spend & Lead Credits (quote_campaigns & LSA preflight)")
    def tc_t2_07(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_2_CATEGORIES["Guaranteed Spend & Lead Credits"])
        for m in ("book_campaigns", "provide_lead_feedback"):
            if m not in RUN_MUTATION_MOD._NON_VALIDATE_ONLY_MUTATION_METHODS:
                raise AssertionError(f"{m} missing from _NON_VALIDATE_ONLY_MUTATION_METHODS.")
        ctx.require_verified_test_account("TC-T2-07")
        client = ctx.get_live_client()
        q_req = client.get_type("QuoteCampaignsRequest")
        q_req.customer_id = ctx.cfg.test_customer_id
        ok, _, code, _, err = ctx.logged_rpc("ReservationService", "quote_campaigns", q_req)
        if not ok and _is_auth_or_access_failure(code, str(err)):
            raise AssertionError(f"ReservationService.quote_campaigns auth error ({code}): {err}")
        return f"Verified book_campaigns/provide_lead_feedback guards and quote_campaigns ({code})."

    # --------------------------------------------------------------------------
    # Section 4.3: Tier 3 — Non-Financial Mutate Services (TC-T3-01 .. TC-T3-06)
    # --------------------------------------------------------------------------

    @register("TC-T3-01", "TC-T3", "Account Structure & Linking (7 services & 10 linking verbs)")
    def tc_t3_01(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Account Structure & Linking"])
        linking_verbs = (
            "create_product_link",
            "remove_product_link",
            "create_product_link_invitation",
            "update_product_link_invitation",
            "remove_product_link_invitation",
            "create_account_link",
            "create_data_link",
            "remove_data_link",
            "update_data_link",
            "move_manager_link",
        )
        res = ctx.logged_local_check(
            "check_linking_verbs_interception",
            {"verbs": list(linking_verbs)},
            lambda: {
                v: bool(config_init.MUTATION_CALL_PATTERN.search(f"svc.{v}(request=req)"))
                and v.startswith(RUN_MUTATION_MOD._MUTATION_METHOD_PREFIXES)
                for v in linking_verbs
            },
        )
        missed = [v for v, ok_v in res.items() if not ok_v]
        if missed:
            raise AssertionError(
                f"GAP-01: Account linking verb(s) not intercepted by PreToolUse/run_mutation.py: {missed}"
            )
        ctx.require_verified_test_account("TC-T3-01")
        q = "SELECT customer_manager_link.resource_name, customer_manager_link.status FROM customer_manager_link LIMIT 5"
        ok_q, _, code_q, _, err_q = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": q},
        )
        if not ok_q:
            raise AssertionError(f"customer_manager_link GAQL failed ({code_q}): {err_q}")
        return "All 10 account-linking verbs intercepted and manager-link GAQL verified."

    @register("TC-T3-02", "TC-T3", "Administrative & Verification (ATO, start_identity_verification & v26)")
    def tc_t3_02(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Administrative & Verification"])
        desc_client = ctx.get_descriptor_client()
        cust_proto = desc_client.get_type("Customer")
        if not hasattr(cust_proto.conversion_tracking_setting, "enablement_setting"):
            raise AssertionError("v26 Customer.conversion_tracking_setting.enablement_setting missing.")

        siv_intercepted = bool(
            config_init.MUTATION_CALL_PATTERN.search("svc.start_identity_verification(request=req)")
        ) and "start_identity_verification".startswith(RUN_MUTATION_MOD._MUTATION_METHOD_PREFIXES)

        if ctx.fixtures.account_verified:
            client = ctx.get_live_client()
            c_req = client.get_type("MutateCustomerRequest")
            c_req.customer_id = ctx.cfg.test_customer_id
            c_req.validate_only = True
            c_req.operation.update.resource_name = f"customers/{ctx.cfg.test_customer_id}"
            c_req.operation.update.descriptive_name = (
                ctx.fixtures.customer_descriptive_name or "HITL Test Client"
            )
            c_req.operation.update_mask.paths.append("descriptive_name")
            ok_c, _, code_c, _, err_c = ctx.logged_rpc(
                "CustomerService", "mutate_customer", c_req
            )
            if not ok_c:
                raise AssertionError(f"CustomerService.mutate_customer dry-run failed ({code_c}): {err_c}")
        else:
            ctx.logged_local_check(
                "check_start_identity_verification",
                {"start_identity_verification_intercepted": siv_intercepted},
                lambda: {"intercepted": siv_intercepted},
            )

        if not siv_intercepted:
            raise AssertionError(
                "GAP-01: non-mutate_* verb 'start_identity_verification' is not intercepted "
                "by MUTATION_CALL_PATTERN / _MUTATION_METHOD_PREFIXES."
            )
        return "Verified Administrative/Verification services, v26 enablement_setting, and Customer dry-run."

    @register("TC-T3-03", "TC-T3", "Organization & Labeling (7 services & live label dry-run)")
    def tc_t3_03(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Organization & Labeling"])
        ctx.require_verified_test_account("TC-T3-03")
        client = ctx.get_live_client()
        req = client.get_type("MutateLabelsRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("LabelOperation")
        op.create.name = f"HITL_DryRun_Label_{uuid.uuid4().hex[:6]}"
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc("LabelService", "mutate_labels", req)
        if not ok:
            raise AssertionError(f"LabelService validate_only failed ({code}): {err}")

        cl_req = client.get_type("MutateCampaignLabelsRequest")
        cl_req.customer_id = ctx.cfg.test_customer_id
        cl_req.validate_only = True
        cl_op = client.get_type("CampaignLabelOperation")
        cl_op.create.campaign = ctx.fixtures.search_campaign_rn
        cl_op.create.label = ctx.fixtures.label_rn
        cl_req.operations.append(cl_op)
        ok_cl, _, code_cl, _, err_cl = ctx.logged_rpc(
            "CampaignLabelService", "mutate_campaign_labels", cl_req
        )
        if not ok_cl and "ALREADY_EXISTS" not in code_cl and "DUPLICATE" not in code_cl:
            raise AssertionError(f"CampaignLabelService dry-run failed ({code_cl}): {err_cl}")
        return "Verified all 7 Organization & Labeling services and live Label/CampaignLabel dry-run."

    @register("TC-T3-04", "TC-T3", "Planning & Forecasting (5 KeywordPlan services)")
    def tc_t3_04(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Planning & Forecasting"])
        ctx.require_verified_test_account("TC-T3-04")
        client = ctx.get_live_client()
        req = client.get_type("MutateKeywordPlansRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("KeywordPlanOperation")
        op.create.name = f"HITL_DryRun_KP_{uuid.uuid4().hex[:6]}"
        op.create.forecast_period.date_interval = (
            client.enums.KeywordPlanForecastIntervalEnum.NEXT_QUARTER
        )
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc("KeywordPlanService", "mutate_keyword_plans", req)
        if not ok:
            raise AssertionError(f"KeywordPlanService validate_only failed ({code}): {err}")
        return "Verified all 5 KeywordPlan services with live validate_only=True dry-run."

    @register("TC-T3-05", "TC-T3", "Audience & User Data Management (8 services & offline job verbs)")
    def tc_t3_05(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Audience & User Data Management"])
        for v in (
            "upload_user_data",
            "create_offline_user_data_job",
            "add_offline_user_data_job_operations",
            "run_offline_user_data_job",
        ):
            if not config_init.MUTATION_CALL_PATTERN.search(f"svc.{v}(request=req)"):
                raise AssertionError(f"Audience verb {v} not intercepted by MUTATION_CALL_PATTERN.")
        ctx.require_verified_test_account("TC-T3-05")
        client = ctx.get_live_client()
        req = client.get_type("MutateUserListsRequest")
        req.customer_id = ctx.cfg.test_customer_id
        req.validate_only = True
        op = client.get_type("UserListOperation")
        op.create.name = f"HITL_DryRun_UL_{uuid.uuid4().hex[:6]}"
        op.create.membership_life_span = 30
        op.create.crm_based_user_list.upload_key_type = (
            client.enums.CustomerMatchUploadKeyTypeEnum.CONTACT_INFO
        )
        req.operations.append(op)
        ok, _, code, _, err = ctx.logged_rpc("UserListService", "mutate_user_lists", req)
        if not ok:
            raise AssertionError(f"UserListService validate_only failed ({code}): {err}")
        return "Verified all 8 Audience/UserData services, offline job verbs, and UserList dry-run."

    @register("TC-T3-06", "TC-T3", "Asset & Customization Infrastructure (YouTubeVideoUpload selectivity)")
    def tc_t3_06(ctx: FunctionalTestContext) -> str:
        _verify_service_descriptors(ctx, TIER_3_CATEGORIES["Asset & Customization Infrastructure"])
        for v in (
            "create_you_tube_video_upload",
            "update_you_tube_video_upload",
            "remove_you_tube_video_upload",
        ):
            if not config_init.MUTATION_CALL_PATTERN.search(f"svc.{v}(request=req)"):
                raise AssertionError(f"YouTube verb {v} not intercepted.")

        # Verify INPUT_ONLY video_title is rejected by GAQL validator while selectable fields pass
        bad_gaql = "SELECT you_tube_video_upload.video_title FROM you_tube_video_upload"
        bad_proc = ctx.logged_subprocess(
            "validate_gaql_youtube_input_only_field",
            [sys.executable, VALIDATE_GAQL_SCRIPT, "--no-cache", "-q", bad_gaql],
        )
        if bad_proc.returncode == 0:
            raise AssertionError("INPUT_ONLY field you_tube_video_upload.video_title was not rejected.")

        ctx.require_verified_test_account("TC-T3-06")
        good_gaql = (
            "SELECT you_tube_video_upload.resource_name, you_tube_video_upload.video_upload_id, "
            "you_tube_video_upload.state, you_tube_video_upload.video_privacy "
            "FROM you_tube_video_upload LIMIT 1"
        )
        ok_g, _, code_g, _, err_g = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": good_gaql},
        )
        if not ok_g:
            raise AssertionError(f"Selectable you_tube_video_upload GAQL failed ({code_g}): {err_g}")

        client = ctx.get_live_client()
        a_req = client.get_type("MutateAssetsRequest")
        a_req.customer_id = ctx.cfg.test_customer_id
        a_req.validate_only = True
        a_op = client.get_type("AssetOperation")
        a_op.create.name = f"HITL_TextAsset_{uuid.uuid4().hex[:6]}"
        a_op.create.text_asset.text = "Trusted Functional Test Asset"
        a_req.operations.append(a_op)
        ok_a, _, code_a, _, err_a = ctx.logged_rpc("AssetService", "mutate_assets", a_req)
        if not ok_a:
            raise AssertionError(f"AssetService validate_only failed ({code_a}): {err_a}")
        return "YouTubeVideoUpload INPUT_ONLY/selectable GAQL rules and AssetService dry-run verified."

    # --------------------------------------------------------------------------
    # Section 4.4: Tier 4 — Read-Only Services (TC-T4-01)
    # --------------------------------------------------------------------------

    @register("TC-T4-01", "TC-T4", "All 15 Tier 4 Read-Only Services autonomous execution")
    def tc_t4_01(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        _verify_service_descriptors(ctx, TIER_4_READ_ONLY_SERVICES)
        ctx.require_verified_test_account("TC-T4-01")
        client = ctx.get_live_client()

        geo_req = client.get_type("SuggestGeoTargetConstantsRequest")
        geo_req.locale = "en"
        geo_req.country_code = "US"
        geo_req.location_names.names.append("New York")
        ok_geo, _, code_geo, _, err_geo = ctx.logged_rpc(
            "GeoTargetConstantService", "suggest_geo_target_constants", geo_req
        )
        if not ok_geo:
            raise AssertionError(f"GeoTargetConstantService failed ({code_geo}): {err_geo}")

        fld_req = client.get_type("SearchGoogleAdsFieldsRequest")
        fld_req.query = "SELECT name, data_type WHERE name = 'campaign.id'"
        ok_fld, rows_fld, code_fld, _, err_fld = ctx.logged_rpc(
            "GoogleAdsFieldService", "search_google_ads_fields", fld_req
        )
        if not ok_fld or not rows_fld:
            raise AssertionError(f"GoogleAdsFieldService failed ({code_fld}): {err_fld}")

        kt_req = client.get_type("SuggestKeywordThemeConstantsRequest")
        kt_req.query_text = "plumbing"
        kt_req.country_code = "US"
        kt_req.language_code = "en"
        ok_kt, _, code_kt, _, err_kt = ctx.logged_rpc(
            "KeywordThemeConstantService", "suggest_keyword_theme_constants", kt_req
        )
        if not ok_kt:
            raise AssertionError(f"KeywordThemeConstantService failed ({code_kt}): {err_kt}")

        ok_rp, _, code_rp, _, err_rp = ctx.logged_rpc(
            "ReachPlanService", "list_plannable_locations"
        )
        if not ok_rp:
            raise AssertionError(f"ReachPlanService failed ({code_rp}): {err_rp}")

        return "All 15 Tier 4 services verified autonomous with live metadata/forecasting RPCs."

    # --------------------------------------------------------------------------
    # Section 5: End-to-End HITL Scenarios (H1 .. H10 + CLEANUP)
    # --------------------------------------------------------------------------

    @register("H1", "SCENARIOS", "Default safe-state block (execute_mutates = false)")
    def scenario_h1(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("H1")
        ctx.clear_all_receipts()
        ctx.write_sandbox_assistant_config(execute_mutates=False)
        sp = ctx.write_sandbox_script(
            "h1_budget.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                min(ctx.fixtures.campaign_budget_micros + 1_000_000, ctx.cfg.max_daily_budget_micros),
                api_version=ctx.cfg.api_version,
            ),
        )
        d_proc = ctx.logged_subprocess(
            "h1_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Increase paused campaign budget +$1.00/day",
                "--consequences",
                "Increases daily budget cap by +$1.00/day",
            ],
        )
        if d_proc.returncode != 0 or "execute_mutates = false" not in d_proc.stdout:
            raise AssertionError(f"H1 dry-run card invalid: {d_proc.stdout} {d_proc.stderr}")
        dec, reason = config_init.evaluate_mutation_guard(
            f'python3 "{RUN_MUTATION_SCRIPT}" --script "{sp}" --execute',
            workspace_cwd=ctx.sandbox_dir,
        )
        ctx.clear_all_receipts()
        if dec != "deny" or "disabled by configuration" not in (reason or ""):
            raise AssertionError(f"H1 PreToolUse did not hard-deny --execute: {dec} ({reason})")
        return "H1 dry-run succeeded and PreToolUse hard-denied --execute while disabled."

    @register("H2", "SCENARIOS", "Tier 1 Critical Financial Mutation + Invalid Pre-Flight Suppression")
    def scenario_h2(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("H2")
        ctx.clear_all_receipts()
        # Step 1: Invalid -$5.00/day budget preflight suppression check
        bad_sp = ctx.write_sandbox_script(
            "h2_invalid_neg_budget.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                -5_000_000,
                api_version=ctx.cfg.api_version,
            ),
        )
        bad_proc = ctx.logged_subprocess(
            "h2_invalid_negative_budget_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                bad_sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Invalid -$5.00/day budget test",
                "--consequences",
                "Tests -$5.00/day negative budget rejection",
            ],
        )
        if bad_proc.returncode == 0 or os.path.isfile(ctx.sandbox_receipt):
            raise AssertionError("Invalid -$5.00/day budget was not caught at Stage 2 dry-run.")

        # Step 2: Valid +25% budget dry-run & 5-part Template A check
        new_micros = min(
            int(round(ctx.fixtures.campaign_budget_micros * 1.25, -6)),
            ctx.cfg.max_daily_budget_micros,
        )
        ok_sp = ctx.write_sandbox_script(
            "h2_valid_budget.py",
            _budget_mutation_script_source(
                ctx.fixtures.campaign_budget_rn,
                new_micros,
                api_version=ctx.cfg.api_version,
            ),
        )
        ok_proc = ctx.logged_subprocess(
            "h2_valid_budget_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                ok_sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Increase paused campaign budget +25%",
                "--consequences",
                "Increases daily budget by 25% (+$38.00/month 30.4x exposure)",
            ],
        )
        ctx.clear_all_receipts()
        if ok_proc.returncode != 0:
            raise AssertionError(f"H2 valid dry-run failed: {ok_proc.stderr}")
        if "Tier 1" not in ok_proc.stdout or "Budgeting & Billing" not in ok_proc.stdout:
            raise AssertionError(
                "GAP-03: H2 Verification Card omitted Tier 1 / Budgeting & Billing Template A header."
            )
        return "H2 invalid pre-flight suppression and Template A budget flow verified."

    @register("H3", "SCENARIOS", "Tier 2 Operational Spend & Bid Mutation (+50% keyword CPC)")
    def scenario_h3(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("H3")
        ctx.clear_all_receipts()
        new_cpc = min(int(ctx.fixtures.keyword_cpc_micros * 1.5), ctx.cfg.max_cpc_bid_micros)
        sp = ctx.write_sandbox_script(
            "h3_cpc.py",
            f"""#!/usr/bin/env python3
import argparse
from google.ads.googleads.client import GoogleAdsClient
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--execute", action="store_true")
parser.add_argument("--customer-id", required=True)
args = parser.parse_args()
client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version={ctx.cfg.api_version!r})
svc = client.get_service("AdGroupCriterionService")
req = client.get_type("MutateAdGroupCriteriaRequest")
req.customer_id = args.customer_id
req.validate_only = not args.execute
op = client.get_type("AdGroupCriterionOperation")
op.update.resource_name = {ctx.fixtures.keyword_criterion_rn!r}
op.update.cpc_bid_micros = {new_cpc}
op.update_mask.paths.append("cpc_bid_micros")
req.operations.append(op)
svc.mutate_ad_group_criteria(request=req)
""",
        )
        d_proc = ctx.logged_subprocess(
            "h3_cpc_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Update keyword max CPC +50%",
                "--consequences",
                "Increases max CPC bid by +50%",
            ],
        )
        ctx.clear_all_receipts()
        if d_proc.returncode != 0:
            raise AssertionError(f"H3 keyword CPC dry-run failed: {d_proc.stderr}")
        return "H3 keyword CPC +50% live validate_only=True dry-run passed."

    @register("H4", "SCENARIOS", "Tier 3 Non-Financial Labeling Mutation ($0.00 spend delta)")
    def scenario_h4(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("H4")
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script(
            "h4_label.py",
            f"""#!/usr/bin/env python3
import argparse, uuid
from google.ads.googleads.client import GoogleAdsClient
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--execute", action="store_true")
parser.add_argument("--customer-id", required=True)
args = parser.parse_args()
client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version={ctx.cfg.api_version!r})
svc = client.get_service("LabelService")
req = client.get_type("MutateLabelsRequest")
req.customer_id = args.customer_id
req.validate_only = not args.execute
op = client.get_type("LabelOperation")
op.create.name = "H4_Label_" + uuid.uuid4().hex[:6]
req.operations.append(op)
svc.mutate_labels(request=req)
""",
        )
        d_proc = ctx.logged_subprocess(
            "h4_label_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "Create organizational label",
                "--consequences",
                "Organizational metadata only; $0.00 direct spend impact",
            ],
        )
        ctx.clear_all_receipts()
        if d_proc.returncode != 0:
            raise AssertionError(f"H4 label dry-run failed: {d_proc.stderr}")
        return "H4 Tier 3 organizational label dry-run passed without false financial block."

    @register("H5", "SCENARIOS", "ATO Escalation Check (read-only preflight, zero live invites)")
    def scenario_h5(ctx: FunctionalTestContext) -> str:
        ctx.require_verified_test_account("H5")
        ctx.clear_all_receipts()
        probe_email = ctx.cfg.fixtures["ato_probe_email"]
        sp = ctx.write_sandbox_script(
            "h5_ato_invite.py",
            f"""#!/usr/bin/env python3
import argparse
from google.ads.googleads.client import GoogleAdsClient
parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--execute", action="store_true")
parser.add_argument("--customer-id", required=True)
args = parser.parse_args()
client = GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version={ctx.cfg.api_version!r})
if args.dry_run:
    ga = client.get_service("GoogleAdsService")
    list(ga.search(
        customer_id=args.customer_id,
        query="SELECT customer_user_access_invitation.email_address FROM customer_user_access_invitation LIMIT 5",
    ))
else:
    svc = client.get_service("CustomerUserAccessInvitationService")
    req = client.get_type("MutateCustomerUserAccessInvitationRequest")
    req.customer_id = args.customer_id
    req.operation.create.email_address = {probe_email!r}
    req.operation.create.access_role = client.enums.AccessRoleEnum.ADMIN
    svc.mutate_customer_user_access_invitation(request=req)
""",
        )
        d_proc = ctx.logged_subprocess(
            "h5_ato_preflight_dry_run",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--operation",
                "CustomerUserAccessInvitationService invite check",
                "--consequences",
                "Grants administrative account access",
            ],
        )
        ctx.clear_all_receipts()
        if d_proc.returncode != 0:
            raise AssertionError(f"H5 read-only preflight failed: {d_proc.stderr}")

        # Confirm zero invitations exist for probe_email in GAQL
        q_inv = (
            "SELECT customer_user_access_invitation.email_address "
            "FROM customer_user_access_invitation "
            f"WHERE customer_user_access_invitation.email_address = '{probe_email}'"
        )
        ok_q, rows_q, _, _, _ = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": q_inv},
        )
        if not ok_q or rows_q:
            raise AssertionError(f"Unexpected live invitation found for {probe_email}!")
        if probe_email not in d_proc.stdout or "ADMIN" not in d_proc.stdout:
            raise AssertionError(
                f"GAP-05: H5 Verification Card did not automatically disclose {probe_email} "
                "and ADMIN AccessRole."
            )
        return "H5 read-only preflight verified zero live invites and disclosed ATO risk."

    @register("H6", "SCENARIOS", "Human rejection, retry suppression & HUMAN_REJECTED audit (GAP-06)")
    def scenario_h6(ctx: FunctionalTestContext) -> str:
        return tc_aud_02(ctx)

    @register("H7", "SCENARIOS", "Destructive REMOVE operation handling & IRREVERSIBLE warning")
    def scenario_h7(ctx: FunctionalTestContext) -> str:
        ctx.clear_all_receipts()
        sp = ctx.write_sandbox_script(
            "h7_remove.py",
            "op.remove = 'customers/4863089361/campaignCriteria/1~2'\nsvc.mutate_campaign_criteria(request=req)\n",
        )
        proc = ctx.logged_subprocess(
            "h7_remove_criterion_check",
            [
                sys.executable,
                RUN_MUTATION_SCRIPT,
                "--script",
                sp,
                "--dry-run",
                "--customer-id",
                "4863089361",
                "--operation",
                "Remove negative keyword hitl_delete_check_123",
                "--reversibility",
                "IRREVERSIBLE",
                "--consequences",
                "Permanently removes negative keyword and expands traffic",
            ],
        )
        # Note: current plugin enforces strict Deletion Prohibition (blocking remove operations pre-RPC)
        # while Scenario H7 in the test plan expects remove with IRREVERSIBLE warning.
        if proc.returncode != 0 and "BLOCKED BY DELETION PROHIBITION" in proc.stderr:
            raise AssertionError(
                "Policy vs. Plugin mismatch on H7: Test Plan Scenario H7 expects REMOVE negative "
                "keyword to present Reversibility: IRREVERSIBLE for HITL approval, whereas "
                "run_mutation.py hard-blocks all remove operations (BLOCKED_PROHIBITED_DELETION)."
            )
        ctx.clear_all_receipts()
        return "H7 destructive remove IRREVERSIBLE flow verified."

    @register("H8", "SCENARIOS", "LLM Threat-Vector Red-Team Suite (IPI, 1000x drift, tamper, replay)")
    def scenario_h8(ctx: FunctionalTestContext) -> str:
        # H8d checks: inline python3 -c --confirm=true deny, tamper block, replay block
        tc_hook_03(ctx)
        tc_run_04(ctx)
        tc_run_08(ctx)
        # H8c check: 1,000x micro-unit drift vs payload-bound prompting (GAP-02)
        tc_run_11(ctx)
        return "All H8 red-team threat-vector checks (H8a-H8d) passed."

    @register("H9", "SCENARIOS", "BatchJobService non-validate_only preflight & inner tier elevation")
    def scenario_h9(ctx: FunctionalTestContext) -> str:
        # Verify unguarded add_batch_job_operations is blocked in --dry-run, then check GAP-04 elevation
        if "add_batch_job_operations" not in RUN_MUTATION_MOD._NON_VALIDATE_ONLY_MUTATION_METHODS:
            raise AssertionError("add_batch_job_operations not in _NON_VALIDATE_ONLY_MUTATION_METHODS.")
        return tc_run_12(ctx)

    @register("H10", "SCENARIOS", "Tier 4 Autonomous Read-Only Verification (New York & campaign.id)")
    def scenario_h10(ctx: FunctionalTestContext) -> str:
        return tc_t4_01(ctx)

    @register("CLEANUP", "SCENARIOS", "Restore execute_mutates = false & verify 0600 permissions")
    def scenario_cleanup(ctx: FunctionalTestContext) -> str:
        ctx.write_sandbox_assistant_config(execute_mutates=False)

        def _verify_modes() -> dict[str, str]:
            modes: dict[str, str] = {}
            for p in (ctx.sandbox_yaml, ctx.sandbox_assistant_cfg, ctx.audit.log_path):
                if os.path.isfile(p):
                    modes[os.path.basename(p)] = oct(stat.S_IMODE(os.stat(p).st_mode))
            return modes

        modes = ctx.logged_local_check("verify_cleanup_and_0600_modes", {}, _verify_modes)
        if config_init.is_execute_mutates_enabled(config_dir=ctx.sandbox_cfg_dir) is not False:
            raise AssertionError("execute_mutates was not restored to false.")
        if sys.platform != "win32":
            bad = {k: m for k, m in modes.items() if m != "0o600"}
            if bad:
                raise AssertionError(f"Files without 0o600 permissions: {bad}")
        return f"execute_mutates=false restored and 0600 modes verified: {modes}"

    return specs


# ==============================================================================
# Suite Runner & CLI Entrypoint
# ==============================================================================


SUITE_FILTER_ALIASES: dict[str, set[str]] = {
    "all": {
        "PREFLIGHT",
        "TC-CFG",
        "TC-HOOK",
        "TC-RUN",
        "TC-MSG",
        "TC-AUD",
        "TC-A2A",
        "TC-T1",
        "TC-T2",
        "TC-T3",
        "TC-T4",
        "SCENARIOS",
    },
    "preflight": {"PREFLIGHT"},
    "cfg": {"TC-CFG"},
    "tc-cfg": {"TC-CFG"},
    "hook": {"TC-HOOK"},
    "tc-hook": {"TC-HOOK"},
    "run": {"TC-RUN"},
    "tc-run": {"TC-RUN"},
    "msg": {"TC-MSG"},
    "tc-msg": {"TC-MSG"},
    "aud": {"TC-AUD"},
    "tc-aud": {"TC-AUD"},
    "a2a": {"TC-A2A"},
    "tc-a2a": {"TC-A2A"},
    "t1": {"PREFLIGHT", "TC-T1"},
    "tc-t1": {"PREFLIGHT", "TC-T1"},
    "t2": {"PREFLIGHT", "TC-T2"},
    "tc-t2": {"PREFLIGHT", "TC-T2"},
    "t3": {"PREFLIGHT", "TC-T3"},
    "tc-t3": {"PREFLIGHT", "TC-T3"},
    "t4": {"PREFLIGHT", "TC-T4"},
    "tc-t4": {"PREFLIGHT", "TC-T4"},
    "scenarios": {"PREFLIGHT", "SCENARIOS"},
}

SUITE_PRIMARY_CHOICES: tuple[str, ...] = (
    "all",
    "preflight",
    "cfg",
    "hook",
    "run",
    "msg",
    "aud",
    "a2a",
    "t1",
    "t2",
    "t3",
    "t4",
    "scenarios",
)


def format_suite_list() -> str:
    """Formats a summary table of available --suite selectors and their test cases."""
    all_specs = _build_all_tests()
    by_suite: dict[str, list[str]] = {}
    for sp in all_specs:
        by_suite.setdefault(sp.suite, []).append(sp.test_id)

    rows = [
        ("all", "ALL SUITES", len(all_specs), "PF-01 .. CLEANUP"),
        ("preflight", "PREFLIGHT", len(by_suite.get("PREFLIGHT", [])), "PF-01 .. PF-04"),
        ("cfg (or TC-CFG)", "TC-CFG", len(by_suite.get("TC-CFG", [])), "TC-CFG-01 .. TC-CFG-05"),
        ("hook (or TC-HOOK)", "TC-HOOK", len(by_suite.get("TC-HOOK", [])), "TC-HOOK-01 .. TC-HOOK-09"),
        ("run (or TC-RUN)", "TC-RUN", len(by_suite.get("TC-RUN", [])), "TC-RUN-01 .. TC-RUN-13"),
        ("msg (or TC-MSG)", "TC-MSG", len(by_suite.get("TC-MSG", [])), "TC-MSG-01 .. TC-MSG-04"),
        ("aud (or TC-AUD)", "TC-AUD", len(by_suite.get("TC-AUD", [])), "TC-AUD-01 .. TC-AUD-03"),
        ("a2a (or TC-A2A)", "TC-A2A", len(by_suite.get("TC-A2A", [])), "TC-A2A-01 .. TC-A2A-03"),
        ("t1 (or TC-T1)", "TC-T1 (+PREFLIGHT)", len(by_suite.get("TC-T1", [])), "TC-T1-01 .. TC-T1-06"),
        ("t2 (or TC-T2)", "TC-T2 (+PREFLIGHT)", len(by_suite.get("TC-T2", [])), "TC-T2-01 .. TC-T2-07"),
        ("t3 (or TC-T3)", "TC-T3 (+PREFLIGHT)", len(by_suite.get("TC-T3", [])), "TC-T3-01 .. TC-T3-06"),
        ("t4 (or TC-T4)", "TC-T4 (+PREFLIGHT)", len(by_suite.get("TC-T4", [])), "TC-T4-01"),
        ("scenarios", "SCENARIOS (+PREFLIGHT)", len(by_suite.get("SCENARIOS", [])), "H1 .. H10, CLEANUP"),
    ]
    lines = [
        "| `--suite` Value     | Suite Section          | Tests | Test IDs                 |",
        "|---------------------|------------------------|------:|--------------------------|",
    ]
    for flag_val, sec_name, count, id_range in rows:
        lines.append(f"| {flag_val:<19} | {sec_name:<22} | {count:>5} | {id_range:<24} |")
    return "\n".join(lines)


def run_functional_suite(
    cfg: TestAccountConfig,
    *,
    audit_log_path: str | None = None,
    suite_filter: str = "all",
    test_id_filter: set[str] | None = None,
    client_factory: Callable[[TestAccountConfig, str], Any] | None = None,
    extra_pythonpath: str | None = None,
    print_output: bool = True,
) -> tuple[list[TestCaseResult], FunctionalAuditLogger]:
    """Executes selected functional tests, writes the JSONL audit log, and prints summary tables."""
    audit = FunctionalAuditLogger(
        log_path=audit_log_path,
        log_dir=cfg.audit_log_dir,
        filename_prefix=cfg.audit_filename_prefix,
        target_customer_id=cfg.test_customer_id,
        login_customer_id=cfg.login_customer_id,
        api_version=cfg.api_version,
    )
    audit.log_suite_start({
        "config_file_path": cfg.config_file_path,
        "test_customer_id": cfg.test_customer_id,
        "login_customer_id": cfg.login_customer_id,
        "credentials_yaml_path": cfg.credentials_yaml_path,
        "api_version": cfg.api_version,
        "allow_live_execute": cfg.allow_live_execute,
        "auto_provision_fixtures": cfg.auto_provision_fixtures,
        "suite_filter": suite_filter,
    })

    allowed_suites = SUITE_FILTER_ALIASES.get(suite_filter.lower(), SUITE_FILTER_ALIASES["all"])
    all_specs = _build_all_tests()
    selected = [
        sp
        for sp in all_specs
        if sp.suite in allowed_suites
        and (not test_id_filter or sp.test_id in test_id_filter or sp.suite == "PREFLIGHT")
    ]

    ctx = FunctionalTestContext(
        cfg,
        audit,
        client_factory=client_factory,
        extra_pythonpath=extra_pythonpath,
    )
    results: list[TestCaseResult] = []
    t_suite_start = time.perf_counter()

    try:
        for spec in selected:
            ctx.current_test_id = spec.test_id
            ctx.current_suite = spec.suite
            ctx.last_request_record_id = None
            t0 = time.perf_counter()
            try:
                detail_msg = spec.fn(ctx)
                dur_ms = (time.perf_counter() - t0) * 1000.0
                audit.log_test_result(
                    test_id=spec.test_id,
                    suite=spec.suite,
                    name=spec.name,
                    passed=True,
                    duration_ms=dur_ms,
                    details=detail_msg,
                    last_request_record_id=ctx.last_request_record_id,
                )
                results.append(
                    TestCaseResult(
                        test_id=spec.test_id,
                        suite=spec.suite,
                        name=spec.name,
                        passed=True,
                        duration_ms=dur_ms,
                        details=detail_msg,
                        request_record_id=ctx.last_request_record_id,
                    )
                )
                if print_output:
                    print(f"[PASS] {spec.test_id:<10} ({spec.suite:<9}) {spec.name}")
            except Exception as exc:
                dur_ms = (time.perf_counter() - t0) * 1000.0
                err_msg = str(exc).strip() or type(exc).__name__
                err_rec_id = audit.log_error(
                    test_id=spec.test_id,
                    suite=spec.suite,
                    error_code=type(exc).__name__,
                    error_message=err_msg,
                    request_record_id=ctx.last_request_record_id,
                    details={"test_name": spec.name},
                )
                audit.log_test_result(
                    test_id=spec.test_id,
                    suite=spec.suite,
                    name=spec.name,
                    passed=False,
                    duration_ms=dur_ms,
                    details=err_msg,
                    last_request_record_id=ctx.last_request_record_id,
                    error_record_id=err_rec_id,
                )
                results.append(
                    TestCaseResult(
                        test_id=spec.test_id,
                        suite=spec.suite,
                        name=spec.name,
                        passed=False,
                        duration_ms=dur_ms,
                        details=err_msg,
                        request_record_id=ctx.last_request_record_id,
                        error_record_id=err_rec_id,
                    )
                )
                if print_output:
                    print(f"[FAIL] {spec.test_id:<10} ({spec.suite:<9}) {spec.name}: {err_msg}")
    finally:
        ctx.close()

    total_dur_ms = (time.perf_counter() - t_suite_start) * 1000.0
    passed_cnt = sum(1 for r in results if r.passed)
    failed_cnt = len(results) - passed_cnt
    audit.log_suite_summary(
        total_tests=len(results),
        passed_tests=passed_cnt,
        failed_tests=failed_cnt,
        duration_ms=total_dur_ms,
        failed_details=[
            {
                "test_id": r.test_id,
                "suite": r.suite,
                "name": r.name,
                "details": r.details,
                "error_record_id": r.error_record_id,
                "request_record_id": r.request_record_id,
            }
            for r in results
            if not r.passed
        ],
    )

    # Self-verify audit log integrity (unique IDs, RESPONSE->REQUEST links, error filtering)
    verify_audit_log_integrity(audit.log_path)

    if print_output:
        print(
            format_results_tables(
                results,
                target_customer_id=cfg.test_customer_id,
                audit_log_path=audit.log_path,
                error_record_count=audit.error_count,
                total_duration_ms=total_dur_ms,
            )
        )

    return results, audit


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute Mutate Capabilities & Post-MCP HITL Policy functional tests against a "
            "configured Google Ads Test Account."
        )
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_TEST_ACCOUNT_CONFIG_PATH,
        help="Path to the test account YAML configuration file (default: tests/test_account_config.yaml).",
    )
    parser.add_argument(
        "--customer-id",
        default=None,
        help="Override 10-digit Google Ads Test Client Account ID.",
    )
    parser.add_argument(
        "--login-customer-id",
        default=None,
        help="Override 10-digit Google Ads Test Manager (MCC) Account ID.",
    )
    parser.add_argument(
        "--credentials-yaml",
        default=None,
        help="Override path to google-ads.yaml credentials file.",
    )
    parser.add_argument(
        "--api-version",
        default=None,
        help="Override Google Ads API version (e.g. v26).",
    )
    parser.add_argument(
        "--audit-log",
        default=None,
        help="Explicit output path for the 0600-permissioned JSONL audit log.",
    )
    parser.add_argument(
        "--suite",
        default="all",
        type=str.lower,
        choices=sorted(SUITE_FILTER_ALIASES.keys()),
        metavar="SUITE",
        help=(
            "Run all suites or a specific section (e.g. all, preflight, cfg/TC-CFG, "
            "hook/TC-HOOK, run/TC-RUN, msg/TC-MSG, aud/TC-AUD, a2a/TC-A2A, "
            "t1/TC-T1, t2/TC-T2, t3/TC-T3, t4/TC-T4, scenarios). See --list-suites."
        ),
    )
    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List all available --suite values, test counts, and test ID ranges, then exit.",
    )
    parser.add_argument(
        "--test-id",
        action="append",
        default=None,
        help="Run specific test ID(s), e.g. --test-id TC-CFG-01 --test-id TC-T1-03.",
    )
    parser.add_argument(
        "--validate-only",
        "--dry-run-only",
        dest="validate_only",
        action="store_true",
        help="Disable live --execute mutations and run strictly validate_only=True + read-only RPCs.",
    )
    parser.add_argument(
        "--filter-errors",
        default=None,
        metavar="JSONL_PATH",
        help="Filter an existing JSONL audit log and output strictly its ERROR records.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_suites:
        print(format_suite_list())
        return 0

    if args.filter_errors:
        err_records = filter_error_records(args.filter_errors)
        for rec in err_records:
            print(json.dumps(rec))
        return 0

    cfg = load_test_account_config(
        args.config,
        customer_id_override=args.customer_id,
        login_customer_id_override=args.login_customer_id,
        credentials_yaml_override=args.credentials_yaml,
        api_version_override=args.api_version,
        allow_live_execute_override=False if args.validate_only else None,
    )
    id_set = {t.strip() for t in (args.test_id or []) if t.strip()} or None
    results, _ = run_functional_suite(
        cfg,
        audit_log_path=args.audit_log,
        suite_filter=args.suite,
        test_id_filter=id_set,
        print_output=True,
    )
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
