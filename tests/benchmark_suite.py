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

"""Cross-Version Performance & Functionality Benchmark Suite.

Evaluates both functional correctness and execution performance (total ms,
per-op ms, p50/p95 latency, ops/sec) across core subsystems of the
Google Ads API Developer Assistant, and compares results against saved
version baselines (e.g., v4.0.0 vs v4.1.0) or git refs to detect regressions.

Benchmarks that test modules introduced in v4.1.0 (`config/config_init.py`,
`skills/execute-mutation/scripts/run_mutation.py`) are automatically skipped
when executed against a v4.0.0 checkout via `--compare-git-ref v4.0.0`.

Usage:
  # Run suite and compare against default baseline (if present)
  python3 tests/benchmark_suite.py

  # Save current run as a version baseline
  python3 tests/benchmark_suite.py --save-baseline tests/benchmarks/baseline_v4.1.0.json

  # Compare current code against v4.0.0 or v4.1.0 baseline
  python3 tests/benchmark_suite.py --compare-baseline tests/benchmarks/baseline_v4.0.0.json

  # Compare current workspace against another git ref (e.g. tag v4.0.0)
  python3 tests/benchmark_suite.py --compare-git-ref v4.0.0
"""

import argparse
import contextlib
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN_ROOT = os.path.join(
    REPO_ROOT, "plugins", "google-ads-api-developer-assistant"
)

for _path in [
    REPO_ROOT,
    PLUGIN_ROOT,
    os.path.join(PLUGIN_ROOT, "skills", "validate-gaql", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "inspect-object", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "get-cids-under-mcc", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "sync-client-libs", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "pmax-listing-filter", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "troubleshoot-conversions", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "ext-version", "scripts"),
    os.path.join(PLUGIN_ROOT, "skills", "execute-mutation", "scripts"),
    os.path.join(PLUGIN_ROOT, "sidecars", "google-ads-a2a-service"),
]:
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    import config.config_init as cfg_init  # type: ignore[import-not-found]
except ImportError:
    cfg_init = None  # type: ignore[assignment]

try:
    import run_mutation  # type: ignore[import-not-found]
except ImportError:
    run_mutation = None  # type: ignore[assignment]

import inspect_object  # noqa: E402
import server  # noqa: E402
import sync_client_libs  # noqa: E402
import validate_conversion_upload  # noqa: E402
import validate_gaql  # noqa: E402

DEFAULT_BASELINE_DIR = os.path.join(REPO_ROOT, "tests", "benchmarks")


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Computes a percentile from a pre-sorted list of floats."""
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _measure_benchmark(
    name: str,
    description: str,
    iterations: int,
    max_total_ms: float,
    step_fn: Callable[[int], None],
    verify_fn: Callable[[], Dict[str, Any]],
    min_version: str = "4.0.0",
) -> Dict[str, Any]:
    """Runs functional verification followed by timed iterations and returns metrics."""
    functional_passed = False
    functional_details: Dict[str, Any] = {}
    error_msg: Optional[str] = None

    try:
        functional_details = verify_fn() or {}
        functional_passed = True
    except (Exception, SystemExit) as exc:
        error_msg = f"{type(exc).__name__}: {exc}"

    samples_ms: List[float] = []
    if functional_passed:
        try:
            for i in range(iterations):
                t0 = time.perf_counter()
                step_fn(i)
                samples_ms.append((time.perf_counter() - t0) * 1000.0)
        except (Exception, SystemExit) as exc:
            functional_passed = False
            error_msg = f"{type(exc).__name__} during timing loop: {exc}"

    sorted_samples = sorted(samples_ms)
    total_ms = sum(samples_ms)
    mean_ms = statistics.mean(samples_ms) if samples_ms else 0.0
    p50_ms = _percentile(sorted_samples, 50.0)
    p95_ms = _percentile(sorted_samples, 95.0)
    ops_per_sec = (iterations / (total_ms / 1000.0)) if total_ms > 0 else 0.0
    perf_passed = functional_passed and (total_ms <= max_total_ms)

    return {
        "name": name,
        "description": description,
        "min_version": min_version,
        "iterations": iterations,
        "functional_passed": functional_passed,
        "functional_details": functional_details,
        "performance_passed": perf_passed,
        "max_total_ms": round(max_total_ms, 3),
        "total_ms": round(total_ms, 3),
        "mean_ms": round(mean_ms, 4),
        "p50_ms": round(p50_ms, 4),
        "p95_ms": round(p95_ms, 4),
        "ops_per_sec": round(ops_per_sec, 1),
        "error": error_msg,
    }


def _bench_version_resolution() -> Dict[str, Any]:
    """Benchmark 1: Plugin version resolution (v4.0.0 uncached vs v4.1.0 in-process cached)."""

    def verify() -> Dict[str, Any]:
        if hasattr(server, "_CACHED_PLUGIN_VERSION"):
            server._CACHED_PLUGIN_VERSION = None
        v_srv = server.get_plugin_version()
        assert v_srv.startswith("4."), f"Unexpected plugin version: {v_srv}"
        if cfg_init is not None:
            cfg_init._CACHED_VERSION = None
            v_cfg = cfg_init.get_version()
            assert v_cfg == v_srv, f"Version mismatch: {v_cfg} != {v_srv}"
        return {"resolved_version": v_srv}

    def step(_i: int) -> None:
        if cfg_init is not None:
            cfg_init.get_version()
        server.get_plugin_version()

    return _measure_benchmark(
        name="version_resolution_in_process",
        description="Resolve plugin version from plugin.json (uncached in v4.0.0; in-process cached in v4.1.0)",
        iterations=1000,
        max_total_ms=50.0,
        step_fn=step,
        verify_fn=verify,
        min_version="4.0.0",
    )


def _bench_config_sync_and_migration() -> Optional[Dict[str, Any]]:
    """Benchmark 2 (v4.1.0+): Config YAML sync, client_libs cleanup, and v4.0.0 -> v4.1.0 migration."""
    if cfg_init is None or not hasattr(cfg_init, "sync_and_set_config_kv"):
        return None

    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_cfg_")
    try:
        src_yaml = os.path.join(tmp_dir, "home_google_ads.yaml")
        with open(src_yaml, "w", encoding="utf-8") as f:
            f.write('developer_token: "bench_dev_token"\n')

        work_dir = os.path.join(tmp_dir, "workspace")
        cfg_dir = os.path.join(work_dir, "config")
        os.makedirs(cfg_dir, exist_ok=True)

        # Create 40 nested packages under client_libs to verify O(1) top-level check
        lib_dir = os.path.join(work_dir, "client_libs", "google-ads-python")
        for idx in range(40):
            sub = os.path.join(lib_dir, f"pkg_{idx}", "nested")
            os.makedirs(sub, exist_ok=True)
            with open(os.path.join(sub, "mod.py"), "w", encoding="utf-8") as f:
                f.write("# stub\n")

        def verify() -> Dict[str, Any]:
            with open(os.path.join(cfg_dir, "customer_id"), "w", encoding="utf-8") as f:
                f.write("8887776665\n")
            with open(os.path.join(cfg_dir, "api_version.txt"), "w", encoding="utf-8") as f:
                f.write("v25\n")
            dummy_yaml = os.path.join(lib_dir, "google-ads.yaml")
            with open(dummy_yaml, "w", encoding="utf-8") as f:
                f.write("dummy: true\n")

            orig_cwd = os.getcwd()
            try:
                os.chdir(work_dir)
                out_path = cfg_init.sync_and_set_config_kv(
                    key="login_customer_id",
                    value="8887776665",
                    source_yaml=src_yaml,
                    config_dir=cfg_dir,
                )
                assert os.path.isfile(out_path)
                assert not os.path.exists(dummy_yaml), "Dummy client_libs yaml not cleaned"
                cid = cfg_init.get_configured_customer_id(config_dir=cfg_dir)
                assert cid == "8887776665", f"Expected migrated CID 8887776665, got {cid}"
            finally:
                os.chdir(orig_cwd)
            return {"migrated_cid": cid, "dummy_cleaned": True}

        def step(_i: int) -> None:
            cfg_init.sync_and_set_config_kv(
                key="login_customer_id",
                value="8887776665",
                source_yaml=src_yaml,
                config_dir=cfg_dir,
            )

        return _measure_benchmark(
            name="config_sync_and_legacy_migration",
            description="Sync google-ads.yaml, clean client_libs dummy YAML, and migrate v4.0.0 config",
            iterations=50,
            max_total_ms=350.0,
            step_fn=step,
            verify_fn=verify,
            min_version="4.1.0",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_hook_interception() -> Optional[Dict[str, Any]]:
    """Benchmark 3 (v4.1.0+): PreToolUse mutation guard & command rewriting."""
    if cfg_init is None or not hasattr(cfg_init, "evaluate_mutation_guard"):
        return None

    ro_cmd = (
        "python3 skills/validate-gaql/scripts/validate_gaql.py "
        "--query 'SELECT campaign.id FROM campaign'"
    )
    dry_run_cmd = (
        "python3 skills/execute-mutation/scripts/run_mutation.py "
        "--script saved/code/mutate_budget.py --dry-run"
    )
    live_mutate_cmd = (
        "python3 -c \"client.get_service('CampaignBudgetService')"
        '.mutate_campaign_budgets(customer_id=\'123\', operations=[])"'
    )

    def verify() -> Dict[str, Any]:
        d_ro, _ = cfg_init.evaluate_mutation_guard(ro_cmd)
        d_dry, _ = cfg_init.evaluate_mutation_guard(dry_run_cmd)
        d_live, _ = cfg_init.evaluate_mutation_guard(live_mutate_cmd)
        assert d_ro == "allow", f"Expected allow for read-only command, got {d_ro}"
        assert d_dry == "allow", f"Expected allow for dry-run command, got {d_dry}"
        assert d_live == "deny", f"Expected deny for unverified live mutate, got {d_live}"
        return {
            "readonly_decision": d_ro,
            "dry_run_decision": d_dry,
            "unverified_mutate_decision": d_live,
        }

    def step(i: int) -> None:
        if i % 3 == 0:
            cfg_init.evaluate_mutation_guard(ro_cmd)
        elif i % 3 == 1:
            cfg_init.evaluate_mutation_guard(dry_run_cmd)
        else:
            cfg_init.evaluate_mutation_guard(live_mutate_cmd)

    return _measure_benchmark(
        name="hook_pre_tool_use_interception",
        description="Evaluate PreToolUse HITL mutation guard across read-only, dry-run, and live mutate commands",
        iterations=500,
        max_total_ms=120.0,
        step_fn=step,
        verify_fn=verify,
        min_version="4.1.0",
    )


def _bench_gaql_static_analysis() -> Dict[str, Any]:
    """Benchmark 4 (v4.0.0+): GAQL static analysis & dry-run validation (with SHA-256 caching in v4.1.0)."""
    mock_client = MagicMock()
    mock_service = MagicMock()
    mock_client.get_service.return_value = mock_service
    mock_service.search.return_value = []

    valid_q = (
        "SELECT campaign.id, campaign.name, metrics.clicks, segments.date "
        "FROM campaign WHERE campaign.status = 'ENABLED' "
        "AND segments.date DURING LAST_30_DAYS LIMIT 100"
    )
    invalid_or_q = (
        "SELECT campaign.id FROM campaign "
        "WHERE campaign.status = 'ENABLED' OR campaign.status = 'PAUSED'"
    )
    invalid_agg_q = "SELECT COUNT(campaign.id) FROM campaign"
    invalid_hour_v25_q = (
        "SELECT campaign.id, segments.hour FROM campaign "
        "WHERE segments.date DURING LAST_7_DAYS"
    )

    def verify() -> Dict[str, Any]:
        if hasattr(validate_gaql, "invalidate_gaql_cache"):
            validate_gaql.invalidate_gaql_cache()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            validate_gaql.validate_gaql("1234567890", "v25", valid_q, client=mock_client)

            for bad_q in (invalid_or_q, invalid_agg_q, invalid_hour_v25_q):
                exited = False
                try:
                    validate_gaql.validate_gaql("1234567890", "v25", bad_q, client=mock_client)
                except SystemExit as exc:
                    exited = exc.code != 0
                assert exited, f"Expected static GAQL failure for query: {bad_q}"
        return {
            "valid_accepted": True,
            "invalid_rejected": 3,
            "has_sha256_cache": hasattr(validate_gaql, "compute_gaql_cache_key"),
        }

    def step(_i: int) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            validate_gaql.validate_gaql("1234567890", "v25", valid_q, client=mock_client)

    return _measure_benchmark(
        name="gaql_static_analysis",
        description="Validate GAQL syntax, clauses, date segments, and dry-run response caching",
        iterations=200,
        max_total_ms=150.0,
        step_fn=step,
        verify_fn=verify,
        min_version="4.0.0",
    )


def _bench_protobuf_inspection() -> Dict[str, Any]:
    """Benchmark 5 (v4.0.0+): Protobuf type discovery & source inspection (uncached in v4.0.0; cached in v4.1.0)."""
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_proto_")
    orig_expanduser = inspect_object.os.path.expanduser
    orig_gettempdir = tempfile.gettempdir
    has_cache = hasattr(inspect_object, "_AVAILABLE_TYPES_CACHE")
    try:
        fake_lib_root = os.path.join(tmp_dir, "client_libs", "google-ads-python")
        v_dir = os.path.join(fake_lib_root, "google", "ads", "googleads", "v98")
        types_dir = os.path.join(v_dir, "services", "types")
        os.makedirs(types_dir, exist_ok=True)
        proto_file = os.path.join(types_dir, "campaign_service.py")
        with open(proto_file, "w", encoding="utf-8") as f:
            f.write(
                "class MutateCampaignsRequest(proto.Message):\n"
                "    customer_id: str = proto.Field(proto.STRING, number=1)\n"
                "    validate_only: bool = proto.Field(proto.BOOL, number=3)\n"
            )

        inspect_object.os.path.expanduser = lambda _p: fake_lib_root
        tempfile.gettempdir = lambda: tmp_dir
        if has_cache:
            inspect_object._AVAILABLE_TYPES_CACHE.clear()

        def verify() -> Dict[str, Any]:
            types_cold = inspect_object.get_available_types("v98")
            assert "MutateCampaignsRequest" in types_cold
            disk_cache_verified = False

            if has_cache:
                cache_file = os.path.join(tmp_dir, "gads_assistant_types_v98.json")
                assert os.path.isfile(cache_file), "Expected on-disk proto cache file"
                inspect_object._AVAILABLE_TYPES_CACHE.clear()
                orig_glob = inspect_object.glob.glob
                try:
                    def forbid_glob(*_a: Any, **_kw: Any) -> Any:
                        raise AssertionError("glob.glob called despite warm disk cache")

                    inspect_object.glob.glob = forbid_glob
                    types_disk = inspect_object.get_available_types("v98")
                    assert types_disk == types_cold
                    disk_cache_verified = True
                finally:
                    inspect_object.glob.glob = orig_glob

            with contextlib.redirect_stdout(io.StringIO()):
                ok = inspect_object.inspect_from_source(
                    proto_file, "MutateCampaignsRequest"
                )
            assert ok is True
            return {
                "discovered_types": len(types_cold),
                "disk_cache_verified": disk_cache_verified,
            }

        def step(_i: int) -> None:
            inspect_object.get_available_types("v98")

        return _measure_benchmark(
            name="protobuf_type_discovery_and_inspection",
            description="Discover and inspect Protobuf definitions (recursive glob in v4.0.0; memory+disk cache in v4.1.0)",
            iterations=200,
            max_total_ms=60.0,
            step_fn=step,
            verify_fn=verify,
            min_version="4.0.0",
        )
    finally:
        inspect_object.os.path.expanduser = orig_expanduser  # type: ignore[assignment]
        tempfile.gettempdir = orig_gettempdir
        if has_cache:
            inspect_object._AVAILABLE_TYPES_CACHE.clear()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_client_libs_parallel_sync() -> Dict[str, Any]:
    """Benchmark 6 (v4.0.0+): GitHub release metadata check across 5 client libraries (sequential in v4.0.0; parallel in v4.1.0)."""
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_sync_")
    orig_fetch = sync_client_libs.fetch_github_latest_release
    orig_detect = sync_client_libs.detect_installed_version
    try:
        for repo_name in sync_client_libs.KNOWN_REPOS:
            os.makedirs(os.path.join(tmp_dir, repo_name), exist_ok=True)

        def simulated_network_fetch(_slug: str) -> Tuple[str, str]:
            time.sleep(0.025)
            return ("v25.0.0", "https://example.com/release.tar.gz")

        sync_client_libs.fetch_github_latest_release = simulated_network_fetch
        sync_client_libs.detect_installed_version = lambda _e, _p: "25.0.0"

        def verify() -> Dict[str, Any]:
            t0 = time.perf_counter()
            res = sync_client_libs.process_client_libs(
                client_libs_dir=tmp_dir,
                check_only=True,
                include_assistant=False,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            names = [r["codebase"] for r in res]
            assert names == sorted(sync_client_libs.KNOWN_REPOS.keys())
            assert all(r["status"] == "UP_TO_DATE" for r in res)
            return {
                "libraries_checked": len(res),
                "single_run_ms": round(elapsed_ms, 2),
                "sequential_equivalent_ms": 125.0,
            }

        def step(_i: int) -> None:
            sync_client_libs.process_client_libs(
                client_libs_dir=tmp_dir,
                check_only=True,
                include_assistant=False,
            )

        return _measure_benchmark(
            name="client_libs_parallel_release_sync",
            description="Check 5 client libraries against GitHub releases (sequential in v4.0.0; ThreadPoolExecutor in v4.1.0)",
            iterations=5,
            max_total_ms=400.0,
            step_fn=step,
            verify_fn=verify,
            min_version="4.0.0",
        )
    finally:
        sync_client_libs.fetch_github_latest_release = orig_fetch
        sync_client_libs.detect_installed_version = orig_detect
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_conversion_csv_validation() -> Dict[str, Any]:
    """Benchmark 7 (v4.0.0+): Offline conversion CSV schema, timestamp, and GCLID validation."""
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_csv_")
    try:
        csv_path = os.path.join(tmp_dir, "conversions.csv")
        rows = ["gclid,conversion_name,conversion_time,conversion_value,conversion_currency"]
        for i in range(100):
            rows.append(
                f"EAIaIQobChMI_benchmark_gclid_{i:04d},Lead,2026-08-19 12:00:00-04:00,49.99,USD"
            )
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")

        def verify() -> Dict[str, Any]:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                validate_conversion_upload.validate_conversion_csv(csv_path, "v25")
            return {"rows_per_batch": 100}

        def step(_i: int) -> None:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                validate_conversion_upload.validate_conversion_csv(csv_path, "v25")

        return _measure_benchmark(
            name="conversion_csv_validation",
            description="Validate 100-row offline conversion upload CSV (headers, ISO dates, GCLIDs)",
            iterations=50,
            max_total_ms=450.0,
            step_fn=step,
            verify_fn=verify,
            min_version="4.0.0",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_hitl_mutation_receipt_and_sha256() -> Optional[Dict[str, Any]]:
    """Benchmark 8 (v4.1.0+): HITL dry-run receipt signing, verification, and SHA-256 request normalization."""
    if run_mutation is None or not hasattr(run_mutation, "compute_mutate_request_sha256"):
        return None

    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_hitl_")
    orig_get_receipt_paths = run_mutation.get_receipt_paths
    try:
        script_path = os.path.join(tmp_dir, "mutate_budget.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("print('dry run mutation script')\n")
        receipt_path = os.path.join(tmp_dir, "last_dry_run.json")
        run_mutation.get_receipt_paths = lambda: [receipt_path]

        dry_payload = {
            "customer_id": "1234567890",
            "validate_only": True,
            "operations": [{"update": {"resource_name": "customers/1234567890/campaignBudgets/1", "amount_micros": 50000000}}],
        }
        live_payload = {
            "customer_id": "1234567890",
            "validate_only": False,
            "operations": [{"update": {"resource_name": "customers/1234567890/campaignBudgets/1", "amount_micros": 50000000}}],
        }
        tampered_payload = {
            "customer_id": "1234567890",
            "validate_only": False,
            "operations": [{"update": {"resource_name": "customers/1234567890/campaignBudgets/1", "amount_micros": 99000000}}],
        }

        def verify() -> Dict[str, Any]:
            h_dry = run_mutation.compute_mutate_request_sha256(
                "CampaignBudgetService", "mutate_campaign_budgets", dry_payload
            )
            h_live = run_mutation.compute_mutate_request_sha256(
                "CampaignBudgetService", "mutate_campaign_budgets", live_payload
            )
            h_tampered = run_mutation.compute_mutate_request_sha256(
                "CampaignBudgetService", "mutate_campaign_budgets", tampered_payload
            )
            assert h_dry == h_live, "Canonical SHA256 must match across validate_only=True/False"
            assert h_dry != h_tampered, "Tampered payload must produce a different SHA256"

            run_mutation.write_dry_run_receipt(
                customer_id="1234567890",
                operation_summary="Update CampaignBudget 1",
                before_state="$10.00/day",
                after_state="$50.00/day",
                consequences=["Budget cap increases by +$40.00/day"],
                reversibility="REVERSIBLE",
                script_path=script_path,
                rpc_calls=[
                    {
                        "service": "CampaignBudgetService",
                        "method": "mutate_campaign_budgets",
                        "request_payload": dry_payload,
                        "request_sha256": h_dry,
                    }
                ],
            )
            ok, msg, data = run_mutation.load_and_verify_receipt(
                script_path=script_path,
            )
            assert ok, f"Receipt verification failed: {msg}"
            assert data.get("request_sha256") == h_dry
            return {"canonical_sha256_verified": True, "tamper_detected": True}

        def step(_i: int) -> None:
            h = run_mutation.compute_mutate_request_sha256(
                "CampaignBudgetService", "mutate_campaign_budgets", dry_payload
            )
            run_mutation.write_dry_run_receipt(
                customer_id="1234567890",
                operation_summary="Update CampaignBudget 1",
                before_state="$10.00/day",
                after_state="$50.00/day",
                consequences=["Budget cap increases by +$40.00/day"],
                reversibility="REVERSIBLE",
                script_path=script_path,
                rpc_calls=[
                    {
                        "service": "CampaignBudgetService",
                        "method": "mutate_campaign_budgets",
                        "request_payload": dry_payload,
                        "request_sha256": h,
                    }
                ],
            )
            run_mutation.load_and_verify_receipt(
                script_path=script_path,
            )

        return _measure_benchmark(
            name="hitl_mutation_receipt_and_sha256_normalization",
            description="Compute canonical Protobuf SHA-256, write signed dry-run receipt, and verify integrity",
            iterations=100,
            max_total_ms=450.0,
            step_fn=step,
            verify_fn=verify,
            min_version="4.1.0",
        )
    finally:
        run_mutation.get_receipt_paths = orig_get_receipt_paths
        shutil.rmtree(tmp_dir, ignore_errors=True)


def run_all_benchmarks() -> Dict[str, Any]:
    """Executes all applicable functional & performance benchmarks and returns a structured report."""
    suite_start = time.perf_counter()
    raw_benchmarks = [
        _bench_version_resolution(),
        _bench_config_sync_and_migration(),
        _bench_hook_interception(),
        _bench_gaql_static_analysis(),
        _bench_protobuf_inspection(),
        _bench_client_libs_parallel_sync(),
        _bench_conversion_csv_validation(),
        _bench_hitl_mutation_receipt_and_sha256(),
    ]
    benchmarks = [b for b in raw_benchmarks if b is not None]
    suite_total_ms = round((time.perf_counter() - suite_start) * 1000.0, 2)

    all_functional_passed = all(b["functional_passed"] for b in benchmarks)
    all_performance_passed = all(b["performance_passed"] for b in benchmarks)

    resolved_version = (
        cfg_init.get_version()
        if cfg_init is not None and hasattr(cfg_init, "get_version")
        else server.get_plugin_version()
    )

    return {
        "version": resolved_version,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "suite_total_ms": suite_total_ms,
        "all_functional_passed": all_functional_passed,
        "all_performance_passed": all_performance_passed,
        "benchmarks": {b["name"]: b for b in benchmarks},
    }


def compare_reports(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
    max_regression_pct: float = 50.0,
) -> Dict[str, Any]:
    """Compares a current benchmark report against a saved baseline report.

    Flags a regression if:
      1. Any benchmark's `functional_passed` changed from True -> False, OR
      2. A benchmark's `performance_passed` is False, OR
      3. `total_ms` increased by more than `max_regression_pct` AND exceeds a 5ms noise floor.
    """
    comparisons: List[Dict[str, Any]] = []
    functional_regressions: List[str] = []
    performance_regressions: List[str] = []

    curr_benches = current.get("benchmarks", {})
    base_benches = baseline.get("benchmarks", {})

    for name, curr_b in curr_benches.items():
        base_b = base_benches.get(name)
        curr_ms = float(curr_b["total_ms"])
        func_ok = bool(curr_b["functional_passed"])
        perf_ok = bool(curr_b["performance_passed"])

        if not func_ok:
            functional_regressions.append(name)

        if base_b:
            base_ms = float(base_b.get("total_ms", 0.0))
            delta_ms = round(curr_ms - base_ms, 3)
            pct_change = (
                round(((curr_ms - base_ms) / base_ms) * 100.0, 1)
                if base_ms > 0
                else 0.0
            )
            speedup_factor = round(base_ms / curr_ms, 2) if curr_ms > 0 else 1.0
            # Only flag percentage regression if absolute delta > 5ms to avoid sub-millisecond jitter
            regressed = (not perf_ok) or (
                delta_ms > 5.0 and pct_change > max_regression_pct
            )
            in_baseline = True
        else:
            base_ms = 0.0
            delta_ms = 0.0
            pct_change = 0.0
            speedup_factor = 1.0
            regressed = not perf_ok
            in_baseline = False

        if regressed:
            performance_regressions.append(name)

        comparisons.append(
            {
                "name": name,
                "min_version": curr_b.get("min_version", "4.0.0"),
                "in_baseline": in_baseline,
                "functional_passed": func_ok,
                "performance_passed": perf_ok,
                "baseline_ms": round(base_ms, 3),
                "current_ms": round(curr_ms, 3),
                "max_total_ms": curr_b["max_total_ms"],
                "delta_ms": delta_ms,
                "pct_change": pct_change,
                "speedup_factor": speedup_factor,
                "regressed": regressed,
            }
        )

    return {
        "baseline_version": baseline.get("version", "unknown"),
        "current_version": current.get("version", "unknown"),
        "max_regression_pct": max_regression_pct,
        "passed": len(functional_regressions) == 0 and len(performance_regressions) == 0,
        "functional_regressions": functional_regressions,
        "performance_regressions": performance_regressions,
        "comparisons": comparisons,
    }


def format_report_table(
    current: Dict[str, Any],
    comparison: Optional[Dict[str, Any]] = None,
) -> str:
    """Formats benchmark results (and optional baseline comparison) as a readable table."""
    lines: List[str] = []
    lines.append("=" * 108)
    title = f"GOOGLE ADS API DEVELOPER ASSISTANT — BENCHMARK SUITE (v{current['version']})"
    if comparison:
        title += f" vs Baseline (v{comparison['baseline_version']})"
    lines.append(title)
    lines.append("=" * 108)

    if comparison:
        header = (
            f"{'Benchmark':<42} | {'Func':<6} | {'Base (ms)':>10} | "
            f"{'Curr (ms)':>10} | {'Budget':>9} | {'Delta':>9} | {'Speedup':>8} | {'Status':<8}"
        )
        lines.append(header)
        lines.append("-" * 108)
        for c in comparison["comparisons"]:
            func_str = "PASS" if c["functional_passed"] else "FAIL"
            status_str = "REGRESS" if c["regressed"] or not c["functional_passed"] else "PASS"
            if c.get("in_baseline", True):
                base_str = f"{c['baseline_ms']:>10.2f}"
                sign = "+" if c["pct_change"] > 0 else ""
                delta_str = f"{sign}{c['pct_change']:.1f}%"
                speedup_str = f"{c['speedup_factor']:.2f}x"
            else:
                base_str = f"{'N/A (v4.1)':>10}"
                delta_str = f"{'NEW':>9}"
                speedup_str = f"{'N/A':>8}"
            lines.append(
                f"{c['name']:<42} | {func_str:<6} | {base_str} | "
                f"{c['current_ms']:>10.2f} | {c['max_total_ms']:>7.1f}ms | {delta_str:>9} | "
                f"{speedup_str:>8} | {status_str:<8}"
            )
    else:
        header = (
            f"{'Benchmark':<44} | {'Func':<6} | {'Iters':>6} | "
            f"{'Total (ms)':>10} | {'p50 (ms)':>9} | {'p95 (ms)':>9} | {'Budget':>9} | {'Status':<6}"
        )
        lines.append(header)
        lines.append("-" * 108)
        for b in current["benchmarks"].values():
            func_str = "PASS" if b["functional_passed"] else "FAIL"
            status_str = "PASS" if (b["functional_passed"] and b["performance_passed"]) else "FAIL"
            lines.append(
                f"{b['name']:<44} | {func_str:<6} | {b['iterations']:>6} | "
                f"{b['total_ms']:>10.2f} | {b['p50_ms']:>9.4f} | {b['p95_ms']:>9.4f} | "
                f"{b['max_total_ms']:>7.1f}ms | {status_str:<6}"
            )

    lines.append("=" * 108)
    overall_ok = (
        comparison["passed"]
        if comparison is not None
        else (current["all_functional_passed"] and current["all_performance_passed"])
    )
    verdict = "PASSED (No functional or performance regressions)" if overall_ok else "FAILED (Regressions detected)"
    lines.append(f"Total Suite Time: {current['suite_total_ms']:.2f} ms | Verdict: {verdict}")
    lines.append("=" * 108)
    return "\n".join(lines)


def run_against_git_ref(git_ref: str) -> Dict[str, Any]:
    """Exports `git_ref` to a temporary directory and runs this benchmark suite against it."""
    tmp_wt = tempfile.mkdtemp(prefix="gads_bench_gitref_")
    try:
        subprocess.run(
            ["git", "worktree", "add", "--detach", tmp_wt, git_ref],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        # Copy current benchmark runner into the worktree so identical benchmarks execute
        wt_tests = os.path.join(tmp_wt, "tests")
        os.makedirs(wt_tests, exist_ok=True)
        wt_script = os.path.join(wt_tests, "_run_bench_ref.py")
        shutil.copy2(os.path.abspath(__file__), wt_script)

        proc = subprocess.run(
            [sys.executable, wt_script, "--json"],
            cwd=tmp_wt,
            check=False,
            capture_output=True,
            text=True,
        )
        if not proc.stdout.strip():
            raise RuntimeError(
                f"Benchmark failed on git ref {git_ref} (exit {proc.returncode}): {proc.stderr}"
            )
        payload = json.loads(proc.stdout)
        return payload.get("current", payload)
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", tmp_wt],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        shutil.rmtree(tmp_wt, ignore_errors=True)


# ==============================================================================
# Pytest Integration Tests (discovered when running `pytest tests/benchmark_suite.py`)
# ==============================================================================


def test_benchmark_suite_functional_and_performance_budgets() -> None:
    """Runs the full cross-version benchmark suite and verifies all functional and latency budgets."""
    report = run_all_benchmarks()
    assert report["all_functional_passed"], (
        f"Functional regression in benchmark suite: {json.dumps(report['benchmarks'], indent=2)}"
    )
    assert report["all_performance_passed"], (
        f"Performance budget exceeded in benchmark suite:\n{format_report_table(report)}"
    )


def test_benchmark_suite_baseline_comparison_and_regression_detection() -> None:
    """Verifies baseline comparison against saved v4.0.0 and v4.1.0 baselines and synthetic regressions."""
    current = run_all_benchmarks()

    # 1. Compare against saved v4.0.0 baseline if present
    v400_path = os.path.join(DEFAULT_BASELINE_DIR, "baseline_v4.0.0.json")
    if os.path.isfile(v400_path):
        with open(v400_path, "r", encoding="utf-8") as f:
            v400_base = json.load(f)
        # Ensure v4.0.0 baseline only contains benchmarks that existed in v4.0.0
        for b_name, b_data in v400_base.get("benchmarks", {}).items():
            assert b_data.get("min_version", "4.0.0") == "4.0.0", (
                f"v4.0.0 baseline contains v4.1.0+ benchmark: {b_name}"
            )
        comp_400 = compare_reports(current, v400_base, max_regression_pct=100.0)
        assert comp_400["passed"], (
            f"Regression detected against v4.0.0 baseline:\n{format_report_table(current, comp_400)}"
        )

    # 2. Verify that compare_reports catches both functional and latency regressions
    synthetic_slow = json.loads(json.dumps(current))
    synthetic_slow["benchmarks"]["version_resolution_in_process"]["total_ms"] = (
        current["benchmarks"]["version_resolution_in_process"]["total_ms"] + 50.0
    )
    comp_regressed = compare_reports(synthetic_slow, current, max_regression_pct=25.0)
    assert not comp_regressed["passed"]
    assert "version_resolution_in_process" in comp_regressed["performance_regressions"]

    synthetic_broken = json.loads(json.dumps(current))
    synthetic_broken["benchmarks"]["gaql_static_analysis"]["functional_passed"] = False
    comp_func_broken = compare_reports(synthetic_broken, current, max_regression_pct=50.0)
    assert not comp_func_broken["passed"]
    assert "gaql_static_analysis" in comp_func_broken["functional_regressions"]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cross-Version Performance & Functionality Benchmark Suite"
    )
    parser.add_argument(
        "--save-baseline",
        metavar="PATH",
        help="Write the current benchmark report as a JSON baseline to PATH.",
    )
    parser.add_argument(
        "--compare-baseline",
        metavar="PATH",
        help="Compare current benchmark run against a saved JSON baseline file.",
    )
    parser.add_argument(
        "--compare-git-ref",
        metavar="REF",
        help="Compare current workspace against another git ref (tag, branch, or commit).",
    )
    parser.add_argument(
        "--save-git-ref-baseline",
        nargs=2,
        metavar=("REF", "PATH"),
        help="Run benchmark suite against git REF and save its report to PATH.",
    )
    parser.add_argument(
        "--max-regression-pct",
        type=float,
        default=50.0,
        help="Maximum allowed latency increase percentage before flagging a regression (default: 50%%).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output benchmark report as JSON.",
    )
    args = parser.parse_args()

    if args.save_git_ref_baseline:
        ref_name, ref_out = args.save_git_ref_baseline
        ref_report = run_against_git_ref(ref_name)
        out_path = os.path.abspath(ref_out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ref_report, f, indent=2)
        if not args.json:
            print(f"Saved git ref '{ref_name}' benchmark baseline to {out_path}")

    current_report = run_all_benchmarks()

    if args.save_baseline:
        out_path = os.path.abspath(args.save_baseline)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(current_report, f, indent=2)
        if not args.json:
            print(f"Saved benchmark baseline to {out_path}")

    baseline_report: Optional[Dict[str, Any]] = None
    if args.compare_git_ref:
        baseline_report = run_against_git_ref(args.compare_git_ref)
    elif args.compare_baseline:
        with open(os.path.abspath(args.compare_baseline), "r", encoding="utf-8") as f:
            baseline_report = json.load(f)
    else:
        default_v400 = os.path.join(DEFAULT_BASELINE_DIR, "baseline_v4.0.0.json")
        if os.path.isfile(default_v400):
            with open(default_v400, "r", encoding="utf-8") as f:
                baseline_report = json.load(f)

    comparison: Optional[Dict[str, Any]] = None
    if baseline_report is not None:
        comparison = compare_reports(
            current_report,
            baseline_report,
            max_regression_pct=args.max_regression_pct,
        )

    if args.json:
        payload: Dict[str, Any] = {"current": current_report}
        if comparison is not None:
            payload["comparison"] = comparison
        print(json.dumps(payload, indent=2))
    else:
        print(format_report_table(current_report, comparison))

    passed = (
        comparison["passed"]
        if comparison is not None
        else (
            current_report["all_functional_passed"]
            and current_report["all_performance_passed"]
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
