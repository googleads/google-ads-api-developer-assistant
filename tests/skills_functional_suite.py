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

"""Full functional test suite for non-mutation skills, creation helpers, sidecar & runtime shims.

Complements `tests/hitl_policy_functional_suite.py` by providing end-to-end CLI,
subprocess, loopback HTTP/MCP, and Google Ads Test Account functional validation
for every remaining component of the Google Ads API Developer Assistant:
  - ext-version (`get_extension_version.py`, `get_latest_api_version.py`)
  - inspect-object (`inspect_object.py`)
  - validate-gaql (`validate_gaql.py`, static rules + live/test dry-run + SHA-256 disk cache)
  - get-cids-under-mcc (`get_cids_under_mcc.py`)
  - troubleshoot-conversions (`troubleshoot_conversions.py`, `get_recent_gclids.py`,
    `validate_conversion_upload.py`)
  - sync-client-libs (`sync_client_libs.py`)
  - set_financial_limits (skill script, config wrapper, and root wrapper)
  - creation helpers (`create_account.py`, `create_campaign.py`, `create_ad_group.py`,
    `create_ad.py`, `create_pmax_webpage_filter.py`)
  - A2A HTTP & MCP stdio sidecar (`sidecars/google-ads-a2a-service/server.py`)
  - Cross-directory runtime path resolution (`config/sitecustomize.py`)

Usage:
    # Run all suites against configured Google Ads Test Account:
    python3 tests/skills_functional_suite.py

    # Run strictly offline-capable skill suites without Google Ads credentials:
    python3 tests/skills_functional_suite.py --offline

    # List available suites:
    python3 tests/skills_functional_suite.py --list-suites

    # Run a single suite (e.g., SK-GAQL, SK-CREATE, SK-SIDECAR):
    python3 tests/skills_functional_suite.py --suite create
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from http.server import HTTPServer
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
import secrets
import shutil
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.request

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.json_format import MessageToDict
import yaml

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from hitl_audit_logger import (  # noqa: E402
    DEFAULT_TEST_ACCOUNT_CONFIG_PATH,
    PLUGIN_ROOT,
    REPO_ROOT,
    FunctionalAuditLogger,
    TestAccountConfig,
    TestCaseResult,
    filter_error_records,
    format_results_tables,
    is_valid_customer_id,
    load_test_account_config,
    verify_audit_log_integrity,
)

if PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, PLUGIN_ROOT)

SCRIPTS = {
    "ext_version": os.path.join(
        PLUGIN_ROOT, "skills", "ext-version", "scripts", "get_extension_version.py"
    ),
    "latest_api": os.path.join(
        PLUGIN_ROOT, "skills", "ext-version", "scripts", "get_latest_api_version.py"
    ),
    "inspect_object": os.path.join(
        PLUGIN_ROOT, "skills", "inspect-object", "scripts", "inspect_object.py"
    ),
    "validate_gaql": os.path.join(
        PLUGIN_ROOT, "skills", "validate-gaql", "scripts", "validate_gaql.py"
    ),
    "get_cids": os.path.join(
        PLUGIN_ROOT, "skills", "get-cids-under-mcc", "scripts", "get_cids_under_mcc.py"
    ),
    "troubleshoot_conv": os.path.join(
        PLUGIN_ROOT,
        "skills",
        "troubleshoot-conversions",
        "scripts",
        "troubleshoot_conversions.py",
    ),
    "recent_gclids": os.path.join(
        PLUGIN_ROOT,
        "skills",
        "troubleshoot-conversions",
        "scripts",
        "get_recent_gclids.py",
    ),
    "validate_conv_csv": os.path.join(
        PLUGIN_ROOT,
        "skills",
        "troubleshoot-conversions",
        "scripts",
        "validate_conversion_upload.py",
    ),
    "sync_client_libs": os.path.join(
        PLUGIN_ROOT, "skills", "sync-client-libs", "scripts", "sync_client_libs.py"
    ),
    "set_fin_limits_skill": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "set_financial_limits.py"
    ),
    "set_fin_limits_cfg": os.path.join(PLUGIN_ROOT, "config", "set_financial_limits.py"),
    "set_fin_limits_root": os.path.join(REPO_ROOT, "set_financial_limits.py"),
    "create_account": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "create_account.py"
    ),
    "create_campaign": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "create_campaign.py"
    ),
    "create_ad_group": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "create_ad_group.py"
    ),
    "create_ad": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "create_ad.py"
    ),
    "pmax_filter": os.path.join(
        PLUGIN_ROOT,
        "skills",
        "pmax-listing-filter",
        "scripts",
        "create_pmax_webpage_filter.py",
    ),
    "sidecar": os.path.join(
        PLUGIN_ROOT, "sidecars", "google-ads-a2a-service", "server.py"
    ),
    "run_mutation": os.path.join(
        PLUGIN_ROOT, "skills", "execute-mutation", "scripts", "run_mutation.py"
    ),
}

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _load_module(name: str, path: str) -> Any:
    spec = spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load module {path}")
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _proto_to_dict(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    pb = getattr(obj, "_pb", obj)
    if hasattr(pb, "DESCRIPTOR"):
        try:
            return MessageToDict(pb, preserving_proto_field_name=True)
        except Exception:
            pass
    if isinstance(obj, dict):
        return {str(k): _proto_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_proto_to_dict(i) for i in obj]
    return str(obj)


@dataclass
class SkillTestSpec:
    test_id: str
    suite: str
    name: str
    requires_account: bool
    fn: Callable[[SkillsFunctionalContext], str]


class SkillsFunctionalContext:
    """Isolated sandbox & test-account session state for non-mutation skill tests."""

    def __init__(
        self,
        cfg: TestAccountConfig,
        audit: FunctionalAuditLogger,
        *,
        client_factory: Callable[[TestAccountConfig, str], Any] | None = None,
        extra_pythonpath: str | None = None,
        offline_only: bool = False,
    ) -> None:
        self.cfg = cfg
        self.audit = audit
        self._client_factory = client_factory
        self._extra_pythonpath = extra_pythonpath
        self.offline_only = offline_only
        self.sandbox_dir = tempfile.mkdtemp(prefix="gads_skills_func_")
        self.sandbox_cfg_dir = os.path.join(self.sandbox_dir, "config")
        self.sandbox_data_dir = os.path.join(self.sandbox_dir, "saved", "data")
        self.sandbox_logs_dir = os.path.join(self.sandbox_dir, "saved", "logs")
        os.makedirs(self.sandbox_cfg_dir, exist_ok=True)
        os.makedirs(self.sandbox_data_dir, exist_ok=True)
        os.makedirs(self.sandbox_logs_dir, exist_ok=True)

        self.sandbox_yaml = os.path.join(self.sandbox_cfg_dir, "google-ads.yaml")
        self.sandbox_assistant_cfg = os.path.join(
            self.sandbox_cfg_dir, "assistant_config"
        )
        self.sandbox_fin_limits = os.path.join(
            self.sandbox_cfg_dir, "financial_limits"
        )
        self.sandbox_receipt = os.path.join(
            self.sandbox_data_dir, "last_dry_run.json"
        )
        self.sandbox_audit = os.path.join(
            self.sandbox_logs_dir, "mutation_audit.jsonl"
        )
        self.sandbox_gaql_cache = os.path.join(
            self.sandbox_data_dir, "gaql_validation_cache.json"
        )

        self.current_test_id = "INIT"
        self.current_suite = "PREFLIGHT"
        self.last_request_record_id: str | None = None
        self.account_verified = False
        self.account_error: str | None = None
        self.discovered_campaign_id = "111111111"
        self.discovered_ad_group_id = "222222222"
        self.discovered_asset_group_id = "333333333"
        self._live_client: Any = None
        self._seed_sandbox()

    def _seed_sandbox(self) -> None:
        creds_data: dict[str, Any] = {}
        if os.path.isfile(self.cfg.credentials_yaml_path):
            with open(self.cfg.credentials_yaml_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                creds_data = loaded
        if self.cfg.login_customer_id:
            creds_data["login_customer_id"] = str(self.cfg.login_customer_id)
        if not creds_data:
            creds_data = {
                "developer_token": "OFFLINE_SANDBOX_TOKEN",
                "client_id": "1234567890-offline.apps.googleusercontent.com",
                "client_secret": "offline-secret",
                "refresh_token": "offline-refresh",
                "use_proto_plus": True,
            }
        else:
            creds_data.setdefault("use_proto_plus", True)

        fd = os.open(self.sandbox_yaml, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(creds_data, f, sort_keys=False)
        if sys.platform != "win32":
            os.chmod(self.sandbox_yaml, 0o600)

        cid = (
            self.cfg.test_customer_id
            if is_valid_customer_id(self.cfg.test_customer_id)
            else "4863089361"
        )
        acfg = (
            f'api_version = "{self.cfg.api_version}"\n'
            f'customer_id = "{cid}"\n'
            "execute_mutates = false\n"
            "allow_tier1_financial_mutates = false\n"
            "enabled = true\n"
        )
        fd_a = os.open(
            self.sandbox_assistant_cfg, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        with os.fdopen(fd_a, "w", encoding="utf-8") as f:
            f.write(acfg)
        if sys.platform != "win32":
            os.chmod(self.sandbox_assistant_cfg, 0o600)

        rm = _load_module("_skills_run_mutation_seed", SCRIPTS["run_mutation"])
        fd_fl = os.open(
            self.sandbox_fin_limits, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
        )
        with os.fdopen(fd_fl, "w", encoding="utf-8") as f_fl:
            for k in sorted(rm.FINANCIAL_LIMIT_SPECS.keys()):
                f_fl.write(f'"{k}" = 100000000000\n')
        if sys.platform != "win32":
            os.chmod(self.sandbox_fin_limits, 0o600)

    def close(self) -> None:
        shutil.rmtree(self.sandbox_dir, ignore_errors=True)

    def subprocess_env(
        self, extra: dict[str, str] | None = None
    ) -> dict[str, str]:
        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("GOOGLE_ADS_EXECUTE_MUTATES", None)
        env.pop("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", None)
        env["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = self.sandbox_yaml
        env["GOOGLE_ADS_ASSISTANT_CONFIG_DIR"] = self.sandbox_cfg_dir
        env["GOOGLE_ADS_ASSISTANT_DIR"] = PLUGIN_ROOT
        env["GOOGLE_ADS_FINANCIAL_LIMITS_FILE"] = self.sandbox_fin_limits
        env["GOOGLE_ADS_MUTATION_RECEIPT_PATH"] = self.sandbox_receipt
        env["GOOGLE_ADS_MUTATION_AUDIT_LOG"] = self.sandbox_audit

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
            env.update(extra)
        return env

    def get_live_client(self) -> Any:
        if self._live_client is not None:
            return self._live_client
        if self._client_factory is not None:
            self._live_client = self._client_factory(self.cfg, self.sandbox_yaml)
        else:
            self._live_client = GoogleAdsClient.load_from_storage(
                path=self.sandbox_yaml,
                version=self.cfg.api_version,
            )
        return self._live_client

    def require_verified_test_account(self, desc: str) -> None:
        if self.account_verified:
            return
        reason = (
            self.account_error
            or "Google Ads Test Account was not verified during SK-PF preflight."
        )
        raise AssertionError(f"Requires verified Google Ads Test Account ({desc}): {reason}")

    def logged_subprocess(
        self,
        action: str,
        argv: list[str],
        *,
        cwd: str | None = None,
        stdin_text: str | None = None,
        extra_env: dict[str, str] | None = None,
        timeout: int = 90,
    ) -> subprocess.CompletedProcess[str]:
        req_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=action,
            payload={"argv": argv, "cwd": cwd or self.sandbox_dir},
        )
        self.last_request_record_id = req_id
        t0 = time.perf_counter()
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            cwd=cwd or self.sandbox_dir,
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
    ) -> tuple[bool, Any, str, dict[str, Any]]:
        req_id = self.audit.log_request(
            test_id=self.current_test_id,
            suite=self.current_suite,
            action=f"GoogleAdsRPC:{service_name}.{method_name}",
            service=service_name,
            method=method_name,
            payload=_proto_to_dict(request_obj) if request_obj is not None else dict(kwargs or {}),
        )
        self.last_request_record_id = req_id
        t0 = time.perf_counter()
        try:
            client = self.get_live_client()
            svc = client.get_service(service_name)
            fn = getattr(svc, method_name)
            raw = (
                fn(request=request_obj)
                if request_obj is not None
                else (fn(**kwargs) if kwargs else fn())
            )
            if method_name in ("search", "search_stream"):
                rows = list(raw)
                dur = (time.perf_counter() - t0) * 1000.0
                self.audit.log_response(
                    request_record_id=req_id,
                    test_id=self.current_test_id,
                    suite=self.current_suite,
                    status="OK",
                    duration_ms=dur,
                    payload={"row_count": len(rows)},
                )
                return True, rows, "OK", {"row_count": len(rows)}
            dur = (time.perf_counter() - t0) * 1000.0
            ser = _proto_to_dict(raw)
            self.audit.log_response(
                request_record_id=req_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status="OK",
                duration_ms=dur,
                payload=ser,
            )
            return True, raw, "OK", ser
        except GoogleAdsException as ex:
            dur = (time.perf_counter() - t0) * 1000.0
            code = ex.error.code().name if hasattr(ex.error, "code") else "GOOGLE_ADS_ERROR"
            err = {"code": code, "message": str(ex)}
            self.audit.log_response(
                request_record_id=req_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status=code,
                duration_ms=dur,
                payload=err,
            )
            return False, None, code, err
        except Exception as ex:
            dur = (time.perf_counter() - t0) * 1000.0
            code = type(ex).__name__
            err = {"code": code, "message": str(ex)}
            self.audit.log_response(
                request_record_id=req_id,
                test_id=self.current_test_id,
                suite=self.current_suite,
                status=code,
                duration_ms=dur,
                payload=err,
            )
            return False, None, code, err


def _build_skill_test_specs() -> list[SkillTestSpec]:
    specs: list[SkillTestSpec] = []

    def register(
        test_id: str, suite: str, name: str, *, requires_account: bool = False
    ) -> Callable[[Callable[[SkillsFunctionalContext], str]], Callable[[SkillsFunctionalContext], str]]:
        def _dec(fn: Callable[[SkillsFunctionalContext], str]) -> Callable[[SkillsFunctionalContext], str]:
            specs.append(
                SkillTestSpec(
                    test_id=test_id,
                    suite=suite,
                    name=name,
                    requires_account=requires_account,
                    fn=fn,
                )
            )
            return fn

        return _dec

    # ------------------------------------------------------------------
    # SK-PF: Fail-Closed Test Account Preflight
    # ------------------------------------------------------------------
    @register("SK-PF-01", "SK-PF", "Test account config & 0600 credentials check", requires_account=True)
    def sk_pf_01(ctx: SkillsFunctionalContext) -> str:
        if not is_valid_customer_id(ctx.cfg.test_customer_id):
            ctx.account_error = f"Invalid test_customer_id {ctx.cfg.test_customer_id!r}"
            raise AssertionError(ctx.account_error)
        if not os.path.isfile(ctx.sandbox_yaml):
            ctx.account_error = "Sandbox credentials YAML missing."
            raise AssertionError(ctx.account_error)
        if sys.platform != "win32":
            mode = oct(stat.S_IMODE(os.stat(ctx.sandbox_yaml).st_mode))
            if mode != "0o600":
                raise AssertionError(f"Expected 0o600 on sandbox YAML, got {mode}")
        return f"Validated CID {ctx.cfg.test_customer_id} and 0600 credentials."

    @register("SK-PF-02", "SK-PF", "Caller OAuth/SA access (list_accessible_customers)", requires_account=True)
    def sk_pf_02(ctx: SkillsFunctionalContext) -> str:
        ok, resp, code, err = ctx.logged_rpc(
            "CustomerService", "list_accessible_customers"
        )
        if not ok or not resp:
            ctx.account_error = f"list_accessible_customers failed ({code}): {err}"
            raise AssertionError(ctx.account_error)
        rns = list(getattr(resp, "resource_names", []) or [])
        if not rns:
            ctx.account_error = "list_accessible_customers returned zero accessible accounts."
            raise AssertionError(ctx.account_error)
        return f"Authenticated caller can access {len(rns)} customer(s)."

    @register("SK-PF-03", "SK-PF", "Verify customer.test_account == True & discover entities", requires_account=True)
    def sk_pf_03(ctx: SkillsFunctionalContext) -> str:
        q = (
            "SELECT customer.id, customer.descriptive_name, customer.test_account "
            "FROM customer LIMIT 1"
        )
        ok, rows, code, err = ctx.logged_rpc(
            "GoogleAdsService",
            "search",
            kwargs={"customer_id": ctx.cfg.test_customer_id, "query": q},
        )
        if not ok or not rows:
            ctx.account_error = f"Customer GAQL preflight failed ({code}): {err}"
            raise AssertionError(ctx.account_error)
        cust = rows[0].customer
        if not bool(getattr(cust, "test_account", False)):
            ctx.account_error = (
                f"FATAL_NON_TEST_ACCOUNT: CID {ctx.cfg.test_customer_id} is NOT a test account."
            )
            raise AssertionError(ctx.account_error)
        ctx.account_verified = True
        # Best-effort discovery of an existing campaign/ad_group/asset_group ID for dry-run helpers
        for entity_q, attr_chain, target_attr in (
            ("SELECT campaign.id FROM campaign WHERE campaign.status != 'REMOVED' LIMIT 1", ("campaign", "id"), "discovered_campaign_id"),
            ("SELECT ad_group.id FROM ad_group WHERE ad_group.status != 'REMOVED' LIMIT 1", ("ad_group", "id"), "discovered_ad_group_id"),
            ("SELECT asset_group.id FROM asset_group LIMIT 1", ("asset_group", "id"), "discovered_asset_group_id"),
        ):
            ok_e, rows_e, _, _ = ctx.logged_rpc(
                "GoogleAdsService",
                "search",
                kwargs={"customer_id": ctx.cfg.test_customer_id, "query": entity_q},
            )
            if ok_e and rows_e:
                obj = rows_e[0]
                for a in attr_chain:
                    obj = getattr(obj, a, None)
                if obj:
                    setattr(ctx, target_attr, str(obj))
        return f"Verified test_account=True on CID {ctx.cfg.test_customer_id}."

    # ------------------------------------------------------------------
    # SK-VER: ext-version scripts
    # ------------------------------------------------------------------
    @register("SK-VER-01", "SK-VER", "get_extension_version.py matches plugin.json")
    def sk_ver_01(ctx: SkillsFunctionalContext) -> str:
        with open(os.path.join(PLUGIN_ROOT, "plugin.json"), "r", encoding="utf-8") as f:
            expected = json.load(f)["version"]
        proc = ctx.logged_subprocess(
            "get_extension_version", [sys.executable, SCRIPTS["ext_version"]]
        )
        if proc.returncode != 0 or proc.stdout.strip() != expected:
            raise AssertionError(
                f"Expected version {expected!r}, got rc={proc.returncode}, out={proc.stdout!r}"
            )
        return f"Extension version verified: {expected}"

    @register("SK-VER-02", "SK-VER", "get_latest_api_version.py --no-update resolves SDK version")
    def sk_ver_02(ctx: SkillsFunctionalContext) -> str:
        proc = ctx.logged_subprocess(
            "get_latest_api_version",
            [sys.executable, SCRIPTS["latest_api"], "--no-update", "--config-dir", ctx.sandbox_cfg_dir],
        )
        ver = proc.stdout.strip().splitlines()[-1].strip() if proc.stdout.strip() else ""
        if proc.returncode != 0 or not ver.startswith("v") or not ver[1:].isdigit():
            raise AssertionError(
                f"Invalid latest API version output: rc={proc.returncode}, out={proc.stdout!r}, err={proc.stderr!r}"
            )
        return f"Dynamically resolved active API version: {ver}"

    # ------------------------------------------------------------------
    # SK-INSPECT: inspect-object
    # ------------------------------------------------------------------
    @register("SK-INSPECT-01", "SK-INSPECT", "inspect_object.py inspects Campaign Protobuf fields")
    def sk_inspect_01(ctx: SkillsFunctionalContext) -> str:
        proc = ctx.logged_subprocess(
            "inspect_campaign",
            [
                sys.executable,
                SCRIPTS["inspect_object"],
                "--object_name",
                "Campaign",
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        if proc.returncode != 0 or "advertising_channel_type" not in proc.stdout:
            raise AssertionError(
                f"inspect_object Campaign failed: rc={proc.returncode}, out={proc.stdout[:400]}, err={proc.stderr[:400]}"
            )
        return f"Inspected Campaign descriptor on {ctx.cfg.api_version}."

    @register("SK-INSPECT-02", "SK-INSPECT", "inspect_object.py inspects CampaignStatusEnum values")
    def sk_inspect_02(ctx: SkillsFunctionalContext) -> str:
        proc = ctx.logged_subprocess(
            "inspect_campaign_status_enum",
            [
                sys.executable,
                SCRIPTS["inspect_object"],
                "--object_name",
                "CampaignStatusEnum",
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        if proc.returncode != 0 or "PAUSED" not in proc.stdout or "ENABLED" not in proc.stdout:
            raise AssertionError(
                f"inspect_object CampaignStatusEnum failed: rc={proc.returncode}, out={proc.stdout[:400]}"
            )
        return "Inspected CampaignStatusEnum (ENABLED, PAUSED)."

    @register("SK-INSPECT-03", "SK-INSPECT", "inspect_object.py returns fuzzy suggestion for typo")
    def sk_inspect_03(ctx: SkillsFunctionalContext) -> str:
        proc = ctx.logged_subprocess(
            "inspect_typo",
            [
                sys.executable,
                SCRIPTS["inspect_object"],
                "--object_name",
                "Campain",
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        combined = proc.stdout + "\n" + proc.stderr
        if proc.returncode == 0 or "Campaign" not in combined:
            raise AssertionError(
                f"Expected non-zero with 'Campaign' fuzzy match, got rc={proc.returncode}, out={combined[:400]}"
            )
        return "Fuzzy suggestion surfaced 'Campaign' for typo 'Campain'."

    # ------------------------------------------------------------------
    # SK-GAQL: validate-gaql
    # ------------------------------------------------------------------
    @register("SK-GAQL-01", "SK-GAQL", "validate_gaql.py live dry-run & disk cache write", requires_account=True)
    def sk_gaql_01(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-GAQL-01")
        q = "SELECT campaign.id, campaign.name FROM campaign LIMIT 5"
        proc = ctx.logged_subprocess(
            "validate_gaql_live",
            [
                sys.executable,
                SCRIPTS["validate_gaql"],
                "--customer_id",
                ctx.cfg.test_customer_id,
                "--api_version",
                ctx.cfg.api_version,
                "--cache-path",
                ctx.sandbox_gaql_cache,
                "-q",
                q,
            ],
        )
        if proc.returncode != 0 or "SUCCESS" not in proc.stdout:
            raise AssertionError(f"validate_gaql valid query failed: {proc.stdout} {proc.stderr}")
        if not os.path.isfile(ctx.sandbox_gaql_cache):
            raise AssertionError("validate_gaql did not write SHA-256 disk cache.")
        return "Live GAQL dry-run succeeded and wrote SHA-256 cache."

    @register("SK-GAQL-02", "SK-GAQL", "validate_gaql.py SHA-256 cache hit skips network call", requires_account=True)
    def sk_gaql_02(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-GAQL-02")
        q = "SELECT campaign.id, campaign.name FROM campaign LIMIT 5"
        proc = ctx.logged_subprocess(
            "validate_gaql_cached",
            [
                sys.executable,
                SCRIPTS["validate_gaql"],
                "--customer_id",
                ctx.cfg.test_customer_id,
                "--api_version",
                ctx.cfg.api_version,
                "--cache-path",
                ctx.sandbox_gaql_cache,
                "-q",
                q,
            ],
        )
        if proc.returncode != 0 or "(cached)" not in proc.stdout:
            raise AssertionError(f"Expected '(cached)' hit, got rc={proc.returncode}, out={proc.stdout}")
        return "Second identical GAQL call resolved via SHA-256 disk cache hit."

    @register("SK-GAQL-03", "SK-GAQL", "validate_gaql.py rejects OR, COUNT(), and segments.hour_of_day")
    def sk_gaql_03(ctx: SkillsFunctionalContext) -> str:
        bad_queries = [
            "SELECT campaign.id FROM campaign WHERE campaign.id = 1 OR campaign.id = 2",
            "SELECT COUNT(campaign.id) FROM campaign",
            "SELECT segments.hour_of_day FROM campaign",
        ]
        for idx, bq in enumerate(bad_queries, 1):
            proc = ctx.logged_subprocess(
                f"validate_gaql_bad_{idx}",
                [
                    sys.executable,
                    SCRIPTS["validate_gaql"],
                    "--customer_id",
                    "4863089361",
                    "--api_version",
                    ctx.cfg.api_version,
                    "--no-cache",
                    "-q",
                    bq,
                ],
            )
            if proc.returncode == 0:
                raise AssertionError(f"Forbidden GAQL unexpectedly passed: {bq}")
        return "All 3 forbidden GAQL patterns rejected statically."

    @register("SK-GAQL-04", "SK-GAQL", "validate_gaql.py --clear-cache clears disk cache")
    def sk_gaql_04(ctx: SkillsFunctionalContext) -> str:
        with open(ctx.sandbox_gaql_cache, "w", encoding="utf-8") as f:
            json.dump({"dummy_stale_entry": {"valid": True}}, f)
        # Pass a statically rejected query alongside --clear-cache so this test stays
        # 100% offline-capable while still exercising the CLI --clear-cache execution path.
        ctx.logged_subprocess(
            "validate_gaql_clear_cache",
            [
                sys.executable,
                SCRIPTS["validate_gaql"],
                "--customer_id",
                "4863089361",
                "--api_version",
                ctx.cfg.api_version,
                "--cache-path",
                ctx.sandbox_gaql_cache,
                "--clear-cache",
                "-q",
                "SELECT campaign.id FROM campaign WHERE campaign.id = 1 OR campaign.id = 2",
            ],
        )
        if os.path.isfile(ctx.sandbox_gaql_cache):
            with open(ctx.sandbox_gaql_cache, "r", encoding="utf-8") as f:
                remaining = json.load(f)
            if "dummy_stale_entry" in remaining:
                raise AssertionError(
                    f"--clear-cache did not clear stale entry from cache: {remaining}"
                )
        return "GAQL disk cache cleared cleanly via --clear-cache."

    # ------------------------------------------------------------------
    # SK-MCC: get-cids-under-mcc
    # ------------------------------------------------------------------
    @register("SK-MCC-01", "SK-MCC", "get_cids_under_mcc.py --json returns hierarchy JSON", requires_account=True)
    def sk_mcc_01(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-MCC-01")
        cid_target = ctx.cfg.login_customer_id or ctx.cfg.test_customer_id
        proc = ctx.logged_subprocess(
            "get_cids_json",
            [
                sys.executable,
                SCRIPTS["get_cids"],
                "-c",
                cid_target,
                "-v",
                ctx.cfg.api_version,
                "--json",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"get_cids_under_mcc --json failed: {proc.stdout} {proc.stderr}")
        parsed = json.loads(proc.stdout.strip())
        if not isinstance(parsed, (list, dict)):
            raise AssertionError(f"Expected JSON list/dict, got: {type(parsed)}")
        return f"get_cids_under_mcc.py --json succeeded for CID {cid_target}."

    @register("SK-MCC-02", "SK-MCC", "get_cids_under_mcc.py --print-cids prints CID table", requires_account=True)
    def sk_mcc_02(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-MCC-02")
        cid_target = ctx.cfg.login_customer_id or ctx.cfg.test_customer_id
        proc = ctx.logged_subprocess(
            "get_cids_print",
            [
                sys.executable,
                SCRIPTS["get_cids"],
                "-c",
                cid_target,
                "-v",
                ctx.cfg.api_version,
                "--print-cids",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"get_cids_under_mcc --print-cids failed: {proc.stderr}")
        return "get_cids_under_mcc.py --print-cids completed cleanly."

    # ------------------------------------------------------------------
    # SK-CONV: troubleshoot-conversions suite
    # ------------------------------------------------------------------
    @register("SK-CONV-01", "SK-CONV", "troubleshoot_conversions.py --json runs diagnostic report", requires_account=True)
    def sk_conv_01(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CONV-01")
        proc = ctx.logged_subprocess(
            "troubleshoot_conversions_json",
            [
                sys.executable,
                SCRIPTS["troubleshoot_conv"],
                "-c",
                ctx.cfg.test_customer_id,
                "-v",
                ctx.cfg.api_version,
                "--json",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"troubleshoot_conversions failed: {proc.stdout} {proc.stderr}")
        parsed = json.loads(proc.stdout.strip())
        if "customer_id" not in parsed:
            raise AssertionError(f"Missing customer_id in diagnostic JSON: {parsed}")
        return "troubleshoot_conversions.py --json completed against test account."

    @register("SK-CONV-02", "SK-CONV", "get_recent_gclids.py queries click_view on test account", requires_account=True)
    def sk_conv_02(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CONV-02")
        proc = ctx.logged_subprocess(
            "get_recent_gclids",
            [
                sys.executable,
                SCRIPTS["recent_gclids"],
                "-c",
                ctx.cfg.test_customer_id,
                "-v",
                ctx.cfg.api_version,
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"get_recent_gclids failed: {proc.stdout} {proc.stderr}")
        return "get_recent_gclids.py executed click_view query cleanly."

    @register("SK-CONV-03", "SK-CONV", "validate_conversion_upload.py accepts valid hashed CSV")
    def sk_conv_03(ctx: SkillsFunctionalContext) -> str:
        csv_ok = os.path.join(ctx.sandbox_dir, "conv_valid.csv")
        hashed = hashlib.sha256(b"customer@example.com").hexdigest()
        with open(csv_ok, "w", encoding="utf-8") as f:
            f.write("gclid,conversion_date_time,conversion_value,currency_code,hashed_email\n")
            f.write(f"TestGclid1234567890,2026-10-15 10:30:00+00:00,42.50,USD,{hashed}\n")
        proc = ctx.logged_subprocess(
            "validate_conv_csv_ok",
            [
                sys.executable,
                SCRIPTS["validate_conv_csv"],
                "--csv_path",
                csv_ok,
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"Valid CSV rejected: {proc.stdout} {proc.stderr}")
        return "Valid conversion upload CSV passed validation."

    @register("SK-CONV-04", "SK-CONV", "validate_conversion_upload.py rejects malformed CSV & raw PII")
    def sk_conv_04(ctx: SkillsFunctionalContext) -> str:
        csv_bad = os.path.join(ctx.sandbox_dir, "conv_bad.csv")
        with open(csv_bad, "w", encoding="utf-8") as f:
            f.write("gclid,conversion_date_time,conversion_value,currency_code,hashed_email\n")
            f.write("TestGclid1234567890,2026-10-15 10:30:00,42.50,USD,unhashed@example.com\n")
        proc = ctx.logged_subprocess(
            "validate_conv_csv_bad",
            [
                sys.executable,
                SCRIPTS["validate_conv_csv"],
                "--csv_path",
                csv_bad,
                "--api_version",
                ctx.cfg.api_version,
            ],
        )
        if proc.returncode == 0:
            raise AssertionError("Malformed CSV (missing tz + unhashed email) unexpectedly passed.")
        return "Malformed CSV and unhashed PII rejected cleanly."

    # ------------------------------------------------------------------
    # SK-SYNC: sync-client-libs
    # ------------------------------------------------------------------
    @register("SK-SYNC-01", "SK-SYNC", "sync_client_libs.py discovers local client_libs without mutating")
    def sk_sync_01(ctx: SkillsFunctionalContext) -> str:
        proc = ctx.logged_subprocess(
            "sync_client_libs_help_and_module",
            [
                sys.executable,
                "-c",
                (
                    "import importlib.util, json, os; "
                    f"spec=importlib.util.spec_from_file_location('scl', {SCRIPTS['sync_client_libs']!r}); "
                    "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
                    f"d=os.path.join({PLUGIN_ROOT!r}, 'client_libs'); "
                    "py_path=os.path.join(d, 'google-ads-python'); "
                    "py_ver=m.detect_installed_version('google-ads-python', py_path); "
                    "api_ver=m.detect_lib_api_version(py_path); "
                    "print(json.dumps({'python_local': py_ver, 'api_version': api_ver}))"
                ),
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"sync_client_libs local discovery failed: {proc.stderr}")
        parsed = json.loads(proc.stdout.strip())
        if not parsed.get("python_local") or not parsed.get("api_version"):
            raise AssertionError(f"Could not detect local google-ads-python version: {parsed}")
        return (
            f"Detected local google-ads-python={parsed['python_local']} "
            f"(api_version={parsed['api_version']})."
        )

    # ------------------------------------------------------------------
    # SK-LIMITS: set_financial_limits (skill, config, and root wrappers)
    # ------------------------------------------------------------------
    @register("SK-LIMITS-01", "SK-LIMITS", "set_financial_limits.py --set, --list --json, --reset & 0600")
    def sk_limits_01(ctx: SkillsFunctionalContext) -> str:
        lim_dir = os.path.join(ctx.sandbox_dir, "limits_cfg")
        os.makedirs(lim_dir, exist_ok=True)
        lim_file = os.path.join(lim_dir, "financial_limits")
        env_ovr = {"GOOGLE_ADS_FINANCIAL_LIMITS_FILE": lim_file}
        p_set = ctx.logged_subprocess(
            "set_fin_limits_set",
            [
                sys.executable,
                SCRIPTS["set_fin_limits_skill"],
                "--config-dir",
                lim_dir,
                "--set",
                "CampaignBudgetService.amount_micros=50000000",
            ],
            extra_env=env_ovr,
        )
        if p_set.returncode != 0:
            raise AssertionError(f"--set failed: {p_set.stderr}")
        if sys.platform != "win32":
            mode = oct(stat.S_IMODE(os.stat(lim_file).st_mode))
            if mode != "0o600":
                raise AssertionError(f"Expected 0o600 on financial_limits, got {mode}")
        p_list = ctx.logged_subprocess(
            "set_fin_limits_list",
            [
                sys.executable,
                SCRIPTS["set_fin_limits_skill"],
                "--config-dir",
                lim_dir,
                "--list",
                "--json",
            ],
            extra_env=env_ovr,
        )
        data = json.loads(p_list.stdout)
        limits_map = data.get("limits", data)
        if int(limits_map.get("CampaignBudgetService.amount_micros", 0)) != 50_000_000:
            raise AssertionError(f"Expected 50000000 in --list --json, got: {limits_map}")
        p_rst = ctx.logged_subprocess(
            "set_fin_limits_reset",
            [
                sys.executable,
                SCRIPTS["set_fin_limits_skill"],
                "--config-dir",
                lim_dir,
                "--reset",
                "CampaignBudgetService.amount_micros",
            ],
            extra_env=env_ovr,
        )
        if p_rst.returncode != 0:
            raise AssertionError(f"--reset failed: {p_rst.stderr}")
        return "set_financial_limits.py --set / --list --json / --reset + 0600 verified."

    @register("SK-LIMITS-02", "SK-LIMITS", "Root & config set_financial_limits.py wrappers execute end-to-end")
    def sk_limits_02(ctx: SkillsFunctionalContext) -> str:
        for label, script_key in (
            ("root_wrapper", "set_fin_limits_root"),
            ("config_wrapper", "set_fin_limits_cfg"),
        ):
            proc = ctx.logged_subprocess(
                f"fin_limits_{label}",
                [sys.executable, SCRIPTS[script_key], "--list", "--json"],
            )
            if proc.returncode != 0:
                raise AssertionError(f"{label} failed: {proc.stderr}")
            parsed = json.loads(proc.stdout)
            if not isinstance(parsed, dict) or not parsed:
                raise AssertionError(f"{label} returned empty JSON.")
        return "Both root and config/ set_financial_limits.py wrappers verified."

    @register("SK-LIMITS-03", "SK-LIMITS", "set_financial_limits.py rejects negative and NaN values")
    def sk_limits_03(ctx: SkillsFunctionalContext) -> str:
        for bad_val in ("-100", "nan", "inf"):
            proc = ctx.logged_subprocess(
                f"fin_limits_bad_{bad_val}",
                [
                    sys.executable,
                    SCRIPTS["set_fin_limits_skill"],
                    "--set",
                    f"CampaignBudgetService.amount_micros={bad_val}",
                ],
            )
            if proc.returncode == 0:
                raise AssertionError(f"Invalid financial limit {bad_val!r} unexpectedly accepted.")
        return "Negative, NaN, and Inf financial limits rejected cleanly."

    # ------------------------------------------------------------------
    # SK-CREATE: Built-in creation helper scripts (--dry-run)
    # ------------------------------------------------------------------
    @register("SK-CREATE-01", "SK-CREATE", "create_account.py --dry-run validates account creation", requires_account=True)
    def sk_create_01(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CREATE-01")
        mgr = ctx.cfg.login_customer_id or ctx.cfg.test_customer_id
        proc = ctx.logged_subprocess(
            "create_account_dry_run",
            [
                sys.executable,
                SCRIPTS["create_account"],
                "-m",
                mgr,
                "-v",
                ctx.cfg.api_version,
                "--name",
                "Skills_Func_DryRun_Account",
                "--currency-code",
                "USD",
                "--time-zone",
                "America/New_York",
                "--dry-run",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"create_account.py --dry-run failed: {proc.stdout} {proc.stderr}")
        return "create_account.py --dry-run passed."

    @register("SK-CREATE-02", "SK-CREATE", "create_campaign.py --dry-run validates atomic budget+campaign", requires_account=True)
    def sk_create_02(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CREATE-02")
        proc = ctx.logged_subprocess(
            "create_campaign_dry_run",
            [
                sys.executable,
                SCRIPTS["create_campaign"],
                "-c",
                ctx.cfg.test_customer_id,
                "-v",
                ctx.cfg.api_version,
                "--name",
                "Skills_Func_DryRun_Campaign",
                "--budget-amount-micros",
                "5000000",
                "--channel-type",
                "SEARCH",
                "--status",
                "PAUSED",
                "--dry-run",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"create_campaign.py --dry-run failed: {proc.stdout} {proc.stderr}")
        return "create_campaign.py --dry-run passed."

    @register("SK-CREATE-03", "SK-CREATE", "create_ad_group.py --dry-run validates ad group creation", requires_account=True)
    def sk_create_03(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CREATE-03")
        proc = ctx.logged_subprocess(
            "create_ad_group_dry_run",
            [
                sys.executable,
                SCRIPTS["create_ad_group"],
                "-c",
                ctx.cfg.test_customer_id,
                "-v",
                ctx.cfg.api_version,
                "--campaign-id",
                ctx.discovered_campaign_id,
                "--name",
                "Skills_Func_DryRun_AdGroup",
                "--cpc-bid-micros",
                "1000000",
                "--status",
                "PAUSED",
                "--dry-run",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"create_ad_group.py --dry-run failed: {proc.stdout} {proc.stderr}")
        return "create_ad_group.py --dry-run passed."

    @register("SK-CREATE-04", "SK-CREATE", "create_ad.py --dry-run validates RSA creation", requires_account=True)
    def sk_create_04(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CREATE-04")
        proc = ctx.logged_subprocess(
            "create_ad_dry_run",
            [
                sys.executable,
                SCRIPTS["create_ad"],
                "-c",
                ctx.cfg.test_customer_id,
                "-v",
                ctx.cfg.api_version,
                "--ad-group-id",
                ctx.discovered_ad_group_id,
                "--final-url",
                "https://example.com/skills-test",
                "--headline",
                "Functional Test One",
                "--headline",
                "Functional Test Two",
                "--headline",
                "Functional Test Three",
                "--description",
                "Automated validation description one.",
                "--description",
                "Automated validation description two.",
                "--status",
                "PAUSED",
                "--dry-run",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"create_ad.py --dry-run failed: {proc.stdout} {proc.stderr}")
        return "create_ad.py --dry-run passed."

    @register("SK-CREATE-05", "SK-CREATE", "create_pmax_webpage_filter.py --dry-run validates WEBPAGE filter", requires_account=True)
    def sk_create_05(ctx: SkillsFunctionalContext) -> str:
        ctx.require_verified_test_account("SK-CREATE-05")
        proc = ctx.logged_subprocess(
            "create_pmax_filter_dry_run",
            [
                sys.executable,
                SCRIPTS["pmax_filter"],
                "--customer-id",
                ctx.cfg.test_customer_id,
                "--asset-group-id",
                ctx.discovered_asset_group_id,
                "--url-exclusion",
                "/out-of-stock",
                "--dry-run",
            ],
        )
        if proc.returncode != 0:
            raise AssertionError(f"create_pmax_webpage_filter.py --dry-run failed: {proc.stdout} {proc.stderr}")
        return "create_pmax_webpage_filter.py --dry-run passed."

    # ------------------------------------------------------------------
    # SK-SIDECAR: A2A HTTP & MCP stdio end-to-end
    # ------------------------------------------------------------------
    @register("SK-SIDECAR-01", "SK-SIDECAR", "A2A HTTP GET /health, Bearer auth, & task intents")
    def sk_sidecar_01(ctx: SkillsFunctionalContext) -> str:
        sidecar_mod = _load_module("_skills_sidecar_mod", SCRIPTS["sidecar"])
        token = f"sk-tok-{secrets.token_hex(8)}"
        prev_tok = os.environ.get("A2A_AUTH_TOKEN")
        prev_cfg = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR")
        prev_rec = os.environ.get("GOOGLE_ADS_MUTATION_RECEIPT_PATH")
        prev_aud = os.environ.get("GOOGLE_ADS_MUTATION_AUDIT_LOG")
        os.environ["A2A_AUTH_TOKEN"] = token
        os.environ["GOOGLE_ADS_ASSISTANT_CONFIG_DIR"] = ctx.sandbox_cfg_dir
        os.environ["GOOGLE_ADS_MUTATION_RECEIPT_PATH"] = ctx.sandbox_receipt
        os.environ["GOOGLE_ADS_MUTATION_AUDIT_LOG"] = ctx.sandbox_audit

        class _LoopbackServer(socketserver.ThreadingMixIn, HTTPServer):
            daemon_threads = True

        srv = _LoopbackServer(("127.0.0.1", 0), sidecar_mod.A2AHandler)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            # 1. GET /health
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/health", timeout=10) as resp:
                health = json.loads(resp.read().decode("utf-8"))
            if health.get("status") != "healthy" or not health.get("version"):
                raise AssertionError(f"Invalid health response: {health}")

            # 2. POST /v1/a2a/tasks INSPECT_OBJECT
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/a2a/tasks",
                data=json.dumps({
                    "task_id": "sk-sc-inspect",
                    "intent": "INSPECT_OBJECT",
                    "payload": {
                        "object_name": "Campaign",
                        "api_version": ctx.cfg.api_version,
                    },
                }).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                method="POST",
            )
            with _NO_PROXY_OPENER.open(req, timeout=15) as resp:
                inspect_out = json.loads(resp.read().decode("utf-8"))
            if inspect_out.get("status") != "COMPLETED":
                raise AssertionError(f"Sidecar INSPECT_OBJECT failed: {inspect_out}")

            # 3. POST /v1/a2a/tasks PREPARE_MUTATION + REJECT_MUTATION
            last_out: dict[str, Any] = {}
            for payload_body in (
                {
                    "task_id": "sk-sc-prep",
                    "intent": "PREPARE_MUTATION",
                    "payload": {
                        "customer_id": "4863089361",
                        "operation_summary": "Attach label",
                        "consequences": ["Organizational label change"],
                    },
                },
                {
                    "task_id": "sk-sc-rej",
                    "intent": "REJECT_MUTATION",
                    "payload": {"reason": "Functional test sidecar rejection"},
                },
            ):
                r_post = urllib.request.Request(
                    f"http://127.0.0.1:{port}/v1/a2a/tasks",
                    data=json.dumps(payload_body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    method="POST",
                )
                with _NO_PROXY_OPENER.open(r_post, timeout=15) as resp:
                    last_out = json.loads(resp.read().decode("utf-8"))
            if last_out.get("status") != "HUMAN_REJECTED":
                raise AssertionError(f"Sidecar REJECT_MUTATION failed: {last_out}")
            return "A2A HTTP /health, Bearer auth, INSPECT_OBJECT, and REJECT_MUTATION verified."
        finally:
            srv.shutdown()
            srv.server_close()
            for k, prev in (
                ("A2A_AUTH_TOKEN", prev_tok),
                ("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", prev_cfg),
                ("GOOGLE_ADS_MUTATION_RECEIPT_PATH", prev_rec),
                ("GOOGLE_ADS_MUTATION_AUDIT_LOG", prev_aud),
            ):
                if prev is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = prev

    @register("SK-SIDECAR-02", "SK-SIDECAR", "MCP stdio JSON-RPC initialize, tools/list, and tools/call")
    def sk_sidecar_02(ctx: SkillsFunctionalContext) -> str:
        rpc_msgs = "\n".join([
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "inspect_object",
                    "arguments": {
                        "object_name": "Campaign",
                        "api_version": ctx.cfg.api_version,
                    },
                },
            }),
        ]) + "\n"
        proc = ctx.logged_subprocess(
            "mcp_stdio_roundtrip",
            [sys.executable, SCRIPTS["sidecar"], "--mcp"],
            stdin_text=rpc_msgs,
        )
        if proc.returncode != 0:
            raise AssertionError(f"MCP stdio failed: rc={proc.returncode}, err={proc.stderr}")
        responses = [
            json.loads(line) for line in proc.stdout.splitlines() if line.strip()
        ]
        if len(responses) < 3:
            raise AssertionError(f"Expected 3 JSON-RPC responses, got {len(responses)}: {responses}")
        if "protocolVersion" not in responses[0].get("result", {}):
            raise AssertionError(f"Invalid MCP initialize response: {responses[0]}")
        tools = responses[1].get("result", {}).get("tools", [])
        if len(tools) < 5:
            raise AssertionError(f"Expected >=5 MCP tools, got {len(tools)}")
        if responses[2].get("result", {}).get("isError"):
            raise AssertionError(f"MCP tools/call inspect_object errored: {responses[2]}")
        return f"MCP stdio initialize, tools/list ({len(tools)} tools), and tools/call verified."

    # ------------------------------------------------------------------
    # SK-CWD: Cross-directory sitecustomize.py runtime path resolution
    # ------------------------------------------------------------------
    @register("SK-CWD-01", "SK-CWD", "sitecustomize.py resolves config/google-ads.yaml from outside CWD")
    def sk_cwd_01(ctx: SkillsFunctionalContext) -> str:
        outside_dir = os.path.join(ctx.sandbox_dir, "arbitrary_outside_dir")
        os.makedirs(outside_dir, exist_ok=True)
        probe_code = (
            "import os\n"
            "assert os.path.isfile('config/google-ads.yaml')\n"
            "with open('config/google-ads.yaml', 'r', encoding='utf-8') as f:\n"
            "    txt = f.read()\n"
            "assert 'use_proto_plus' in txt\n"
            "print('SITECUSTOMIZE_RESOLVED_OK')\n"
        )
        proc = ctx.logged_subprocess(
            "sitecustomize_outside_cwd",
            [sys.executable, "-c", probe_code],
            cwd=outside_dir,
        )
        if proc.returncode != 0 or "SITECUSTOMIZE_RESOLVED_OK" not in proc.stdout:
            raise AssertionError(
                f"sitecustomize.py resolution from outside dir failed: rc={proc.returncode}, "
                f"out={proc.stdout}, err={proc.stderr}"
            )
        return "sitecustomize.py transparently resolved config/google-ads.yaml from outside CWD."

    return specs


SUITE_FILTER_ALIASES: dict[str, set[str]] = {
    "all": {
        "SK-PF",
        "SK-VER",
        "SK-INSPECT",
        "SK-GAQL",
        "SK-MCC",
        "SK-CONV",
        "SK-SYNC",
        "SK-LIMITS",
        "SK-CREATE",
        "SK-SIDECAR",
        "SK-CWD",
    },
    "preflight": {"SK-PF"},
    "sk-pf": {"SK-PF"},
    "ver": {"SK-VER"},
    "sk-ver": {"SK-VER"},
    "inspect": {"SK-INSPECT"},
    "sk-inspect": {"SK-INSPECT"},
    "gaql": {"SK-PF", "SK-GAQL"},
    "sk-gaql": {"SK-PF", "SK-GAQL"},
    "mcc": {"SK-PF", "SK-MCC"},
    "sk-mcc": {"SK-PF", "SK-MCC"},
    "conv": {"SK-PF", "SK-CONV"},
    "sk-conv": {"SK-PF", "SK-CONV"},
    "sync": {"SK-SYNC"},
    "sk-sync": {"SK-SYNC"},
    "limits": {"SK-LIMITS"},
    "sk-limits": {"SK-LIMITS"},
    "create": {"SK-PF", "SK-CREATE"},
    "sk-create": {"SK-PF", "SK-CREATE"},
    "sidecar": {"SK-SIDECAR"},
    "sk-sidecar": {"SK-SIDECAR"},
    "cwd": {"SK-CWD"},
    "sk-cwd": {"SK-CWD"},
}


def format_suite_list() -> str:
    specs = _build_skill_test_specs()
    suites_order = [
        ("all", "ALL SUITES", None),
        ("preflight (or SK-PF)", "SK-PF", "SK-PF"),
        ("ver (or SK-VER)", "SK-VER", "SK-VER"),
        ("inspect (or SK-INSPECT)", "SK-INSPECT", "SK-INSPECT"),
        ("gaql (or SK-GAQL)", "SK-GAQL", "SK-GAQL"),
        ("mcc (or SK-MCC)", "SK-MCC", "SK-MCC"),
        ("conv (or SK-CONV)", "SK-CONV", "SK-CONV"),
        ("sync (or SK-SYNC)", "SK-SYNC", "SK-SYNC"),
        ("limits (or SK-LIMITS)", "SK-LIMITS", "SK-LIMITS"),
        ("create (or SK-CREATE)", "SK-CREATE", "SK-CREATE"),
        ("sidecar (or SK-SIDECAR)", "SK-SIDECAR", "SK-SIDECAR"),
        ("cwd (or SK-CWD)", "SK-CWD", "SK-CWD"),
    ]
    rows: list[tuple[str, str, int, str]] = []
    for label, section, key in suites_order:
        matched = specs if key is None else [s for s in specs if s.suite == key]
        id_range = (
            f"{matched[0].test_id} .. {matched[-1].test_id}"
            if len(matched) > 1
            else (matched[0].test_id if matched else "-")
        )
        rows.append((label, section, len(matched), id_range))
    lines = [
        "| `--suite` Value           | Suite Section | Tests | Test IDs                 |",
        "|---------------------------|---------------|------:|--------------------------|",
    ]
    for label, section, count, id_range in rows:
        lines.append(f"| {label:<25} | {section:<13} | {count:>5} | {id_range:<24} |")
    return "\n".join(lines)


def run_skills_functional_suite(
    cfg: TestAccountConfig,
    *,
    audit_log_path: str | None = None,
    suite_filter: str = "all",
    test_id_filter: set[str] | None = None,
    offline_only: bool = False,
    client_factory: Callable[[TestAccountConfig, str], Any] | None = None,
    extra_pythonpath: str | None = None,
    print_output: bool = True,
) -> tuple[list[TestCaseResult], FunctionalAuditLogger]:
    """Executes the non-mutation skills & creation helpers functional test suite."""
    all_specs = _build_skill_test_specs()
    allowed_suites = SUITE_FILTER_ALIASES.get(
        suite_filter.strip().lower(), SUITE_FILTER_ALIASES["all"]
    )
    selected = [s for s in all_specs if s.suite in allowed_suites]
    if test_id_filter:
        upper = {t.upper() for t in test_id_filter}
        selected = [s for s in all_specs if s.test_id.upper() in upper]
    if offline_only:
        selected = [s for s in selected if not s.requires_account]

    audit = FunctionalAuditLogger(
        log_path=audit_log_path,
        log_dir=cfg.audit_log_dir,
        filename_prefix="skills_functional_audit",
        target_customer_id=cfg.test_customer_id,
        login_customer_id=cfg.login_customer_id,
        api_version=cfg.api_version,
    )
    audit.log_suite_start(
        {
            "suite_name": "skills_functional_suite",
            "suite_filter": suite_filter,
            "offline_only": offline_only,
            "selected_test_count": len(selected),
        }
    )
    ctx = SkillsFunctionalContext(
        cfg,
        audit,
        client_factory=client_factory,
        extra_pythonpath=extra_pythonpath,
        offline_only=offline_only,
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
                details = spec.fn(ctx)
                dur_ms = (time.perf_counter() - t0) * 1000.0
                audit.log_test_result(
                    test_id=spec.test_id,
                    suite=spec.suite,
                    name=spec.name,
                    passed=True,
                    duration_ms=dur_ms,
                    details=details,
                    last_request_record_id=ctx.last_request_record_id,
                )
                results.append(
                    TestCaseResult(
                        test_id=spec.test_id,
                        suite=spec.suite,
                        name=spec.name,
                        passed=True,
                        duration_ms=dur_ms,
                        details=details,
                        request_record_id=ctx.last_request_record_id,
                    )
                )
                if print_output:
                    print(f"[PASS] {spec.test_id:<12} ({spec.suite:<10}) {spec.name}")
            except Exception as exc:
                dur_ms = (time.perf_counter() - t0) * 1000.0
                err_msg = f"{type(exc).__name__}: {exc}"
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
                    print(f"[FAIL] {spec.test_id:<12} ({spec.suite:<10}) {spec.name}: {err_msg}")
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
            "Execute full functional tests for all non-mutation skills, creation helpers, "
            "A2A/MCP sidecar, and sitecustomize runtime shims."
        )
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_TEST_ACCOUNT_CONFIG_PATH,
        help="Path to test account YAML config (default: tests/test_account_config.yaml).",
    )
    parser.add_argument("--customer-id", default=None, help="Override 10-digit Test Client CID.")
    parser.add_argument(
        "--login-customer-id", default=None, help="Override 10-digit Test MCC CID."
    )
    parser.add_argument(
        "--credentials-yaml", default=None, help="Override google-ads.yaml path."
    )
    parser.add_argument("--api-version", default=None, help="Override API version (v<N>).")
    parser.add_argument("--audit-log", default=None, help="Explicit output JSONL audit path.")
    parser.add_argument(
        "--suite",
        default="all",
        type=str.lower,
        choices=sorted(SUITE_FILTER_ALIASES.keys()),
        metavar="SUITE",
        help="Run all suites or a specific skill suite (see --list-suites).",
    )
    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List all available skill suites and test counts, then exit.",
    )
    parser.add_argument(
        "--test-id",
        action="append",
        default=None,
        help="Run specific test ID(s), e.g. --test-id SK-GAQL-01.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run strictly offline-capable functional tests (skips live Google Ads RPCs).",
    )
    parser.add_argument(
        "--filter-errors",
        default=None,
        metavar="JSONL_PATH",
        help="Output strictly ERROR records from an existing JSONL audit log.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.list_suites:
        print(format_suite_list())
        return 0
    if args.filter_errors:
        for rec in filter_error_records(args.filter_errors):
            print(json.dumps(rec))
        return 0
    cfg = load_test_account_config(
        args.config,
        customer_id_override=args.customer_id,
        login_customer_id_override=args.login_customer_id,
        credentials_yaml_override=args.credentials_yaml,
        api_version_override=args.api_version,
    )
    id_set = {t.strip() for t in (args.test_id or []) if t.strip()} or None
    results, _ = run_skills_functional_suite(
        cfg,
        audit_log_path=args.audit_log,
        suite_filter=args.suite,
        test_id_filter=id_set,
        offline_only=bool(args.offline),
        print_output=True,
    )
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
