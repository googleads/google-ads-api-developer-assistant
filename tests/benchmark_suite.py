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
Google Ads API Developer Assistant, and compares results between any two
user-specified versions (Git refs, saved JSON baselines, or the current
working tree) without assuming any fallback or hardcoding any versions.

Usage:
  # Compare any two versions (Git tags, branches, commits, baseline files, or 'workspace')
  python3 tests/benchmark_suite.py <base_version> <target_version>
  python3 tests/benchmark_suite.py --compare <base_version> <target_version>
  python3 tests/benchmark_suite.py --base-version <base_version> --target-version <target_version>

  # Save a version baseline (from current workspace or a specific Git ref)
  python3 tests/benchmark_suite.py --save-baseline <output_json_path>
  python3 tests/benchmark_suite.py --save-git-ref-baseline <git_ref> <output_json_path>

  # Run benchmarks on the current working tree only (without comparison)
  python3 tests/benchmark_suite.py --run-current
"""

import argparse
import contextlib
from datetime import datetime, timezone
import glob
import importlib.metadata
import io
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
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

try:
    import inspect_object  # type: ignore[import-not-found]
except ImportError:
    inspect_object = None  # type: ignore[assignment]

try:
    import server  # type: ignore[import-not-found]
except ImportError:
    server = None  # type: ignore[assignment]

try:
    import sync_client_libs  # type: ignore[import-not-found]
except ImportError:
    sync_client_libs = None  # type: ignore[assignment]

try:
    import validate_conversion_upload  # type: ignore[import-not-found]
except ImportError:
    validate_conversion_upload = None  # type: ignore[assignment]

try:
    import validate_gaql  # type: ignore[import-not-found]
except ImportError:
    validate_gaql = None  # type: ignore[assignment]

DEFAULT_BASELINE_DIR = os.path.join(REPO_ROOT, "tests", "benchmarks")
WORKSPACE_SPECIFIERS = frozenset({"workspace", "current", "worktree", "."})


_CACHED_ACTIVE_API_VERSION: Optional[str] = None
_CACHED_INSTALLED_LIB_VERSION: Optional[str] = None


def _resolve_active_api_version() -> str:
    """Dynamically resolves the active Google Ads API version without hardcoded fallbacks."""
    global _CACHED_ACTIVE_API_VERSION
    if _CACHED_ACTIVE_API_VERSION is not None:
        return _CACHED_ACTIVE_API_VERSION

    if cfg_init is not None:
        if hasattr(cfg_init, "get_configured_api_version"):
            configured = cfg_init.get_configured_api_version()
            if configured:
                _CACHED_ACTIVE_API_VERSION = (
                    configured if configured.startswith("v") else f"v{configured}"
                )
                return _CACHED_ACTIVE_API_VERSION
        if hasattr(cfg_init, "detect_latest_api_version"):
            detected = cfg_init.detect_latest_api_version()
            if detected:
                _CACHED_ACTIVE_API_VERSION = (
                    detected if detected.startswith("v") else f"v{detected}"
                )
                return _CACHED_ACTIVE_API_VERSION

    if server is not None and hasattr(server, "get_effective_api_version"):
        try:
            eff = server.get_effective_api_version({})
            if eff:
                _CACHED_ACTIVE_API_VERSION = (
                    eff if eff.startswith("v") else f"v{eff}"
                )
                return _CACHED_ACTIVE_API_VERSION
        except Exception:
            pass

    discovered_versions: List[int] = []
    candidate_roots = [
        os.path.join(
            REPO_ROOT,
            "client_libs",
            "google-ads-python",
            "google",
            "ads",
            "googleads",
        ),
        os.path.join(
            PLUGIN_ROOT,
            "client_libs",
            "google-ads-python",
            "google",
            "ads",
            "googleads",
        ),
    ]
    try:
        import google.ads.googleads as _gads_pkg  # type: ignore[import-untyped]

        for p in getattr(_gads_pkg, "__path__", []):
            candidate_roots.append(p)
    except Exception:
        pass

    for root in candidate_roots:
        if os.path.isdir(root):
            for entry in os.listdir(root):
                m = re.match(r"^v(\d+)$", entry)
                if m and os.path.isdir(os.path.join(root, entry)):
                    discovered_versions.append(int(m.group(1)))

    if discovered_versions:
        _CACHED_ACTIVE_API_VERSION = f"v{max(discovered_versions)}"
        return _CACHED_ACTIVE_API_VERSION

    raise RuntimeError(
        "Unable to resolve active Google Ads API version from configuration or installed client libraries."
    )


def _resolve_installed_library_version() -> str:
    """Dynamically resolves the installed google-ads library version without hardcoding."""
    global _CACHED_INSTALLED_LIB_VERSION
    if _CACHED_INSTALLED_LIB_VERSION is not None:
        return _CACHED_INSTALLED_LIB_VERSION

    try:
        _CACHED_INSTALLED_LIB_VERSION = importlib.metadata.version("google-ads").lstrip(
            "v"
        )
        return _CACHED_INSTALLED_LIB_VERSION
    except Exception:
        pass

    if sync_client_libs is not None and hasattr(
        sync_client_libs, "detect_installed_version"
    ):
        for base_dir in (
            os.path.join(REPO_ROOT, "client_libs", "google-ads-python"),
            os.path.join(PLUGIN_ROOT, "client_libs", "google-ads-python"),
        ):
            if os.path.isdir(base_dir):
                ver = sync_client_libs.detect_installed_version(
                    "google-ads-python", base_dir
                )
                if ver and ver not in ("Unknown", "Not Found"):
                    _CACHED_INSTALLED_LIB_VERSION = ver.lstrip("v")
                    return _CACHED_INSTALLED_LIB_VERSION

    raise RuntimeError("Unable to determine installed google-ads package version.")


def _resolve_manifest_plugin_version() -> str:
    """Reads the plugin version directly from the manifest without hardcoding."""
    for candidate in (
        os.path.join(PLUGIN_ROOT, "plugin.json"),
        os.path.join(PLUGIN_ROOT, "plugin.json.disabled"),
        os.path.join(REPO_ROOT, ".gemini", "agent.json"),
        os.path.join(REPO_ROOT, "plugin.json"),
    ):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ver = str(data.get("version", "")).strip()
                if ver:
                    return ver
            except Exception:
                continue
    if cfg_init is not None and hasattr(cfg_init, "get_version"):
        ver = cfg_init.get_version()
        if ver and ver not in ("Unknown", "Version not found"):
            return ver
    if server is not None and hasattr(server, "get_plugin_version"):
        ver = server.get_plugin_version()
        if ver and ver not in ("Unknown", "Version not found"):
            return ver
    raise RuntimeError("Unable to resolve plugin version from manifest.")


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


def _bench_version_resolution() -> Optional[Dict[str, Any]]:
    """Benchmark 1: Plugin version resolution from manifest."""
    if server is None and cfg_init is None:
        return None

    expected_manifest_version = _resolve_manifest_plugin_version()

    def verify() -> Dict[str, Any]:
        resolved: Optional[str] = None
        if server is not None and hasattr(server, "get_plugin_version"):
            if hasattr(server, "_CACHED_PLUGIN_VERSION"):
                server._CACHED_PLUGIN_VERSION = None
            v_srv = server.get_plugin_version()
            assert v_srv == expected_manifest_version, (
                f"Expected plugin version {expected_manifest_version}, got {v_srv}"
            )
            resolved = v_srv
        if cfg_init is not None and hasattr(cfg_init, "get_version"):
            if hasattr(cfg_init, "_CACHED_VERSION"):
                cfg_init._CACHED_VERSION = None
            v_cfg = cfg_init.get_version()
            assert v_cfg == expected_manifest_version, (
                f"Expected config_init version {expected_manifest_version}, got {v_cfg}"
            )
            resolved = v_cfg
        assert resolved is not None
        return {"resolved_version": resolved}

    def step(_i: int) -> None:
        if cfg_init is not None and hasattr(cfg_init, "get_version"):
            cfg_init.get_version()
        if server is not None and hasattr(server, "get_plugin_version"):
            server.get_plugin_version()

    return _measure_benchmark(
        name="version_resolution_in_process",
        description="Resolve plugin version from manifest across server and config_init",
        iterations=1000,
        max_total_ms=50.0,
        step_fn=step,
        verify_fn=verify,
    )


def _bench_config_sync_and_migration() -> Optional[Dict[str, Any]]:
    """Benchmark 2: Config YAML sync, client_libs cleanup, and legacy config migration."""
    if cfg_init is None or not hasattr(cfg_init, "sync_and_set_config_kv"):
        return None

    active_api_version = _resolve_active_api_version()
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_cfg_")
    try:
        src_yaml = os.path.join(tmp_dir, "home_google_ads.yaml")
        with open(src_yaml, "w", encoding="utf-8") as f:
            f.write('client_id: "bench_client_id"\n')

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
            with open(
                os.path.join(cfg_dir, "api_version.txt"), "w", encoding="utf-8"
            ) as f:
                f.write(f"{active_api_version}\n")
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
                assert not os.path.exists(dummy_yaml), (
                    "Dummy client_libs yaml not cleaned"
                )
                cid = cfg_init.get_configured_customer_id(config_dir=cfg_dir)
                assert cid == "8887776665", (
                    f"Expected migrated CID 8887776665, got {cid}"
                )
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
            description="Sync google-ads.yaml, clean client_libs dummy YAML, and migrate legacy config files",
            iterations=50,
            max_total_ms=350.0,
            step_fn=step,
            verify_fn=verify,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_hook_interception() -> Optional[Dict[str, Any]]:
    """Benchmark 3: PreToolUse mutation guard & command evaluation."""
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

    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_hook_")
    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_dir)

        def verify() -> Dict[str, Any]:
            d_ro, _ = cfg_init.evaluate_mutation_guard(ro_cmd)
            d_dry, _ = cfg_init.evaluate_mutation_guard(dry_run_cmd)
            d_live, _ = cfg_init.evaluate_mutation_guard(live_mutate_cmd)
            assert d_ro == "allow", (
                f"Expected allow for read-only command, got {d_ro}"
            )
            assert d_dry == "allow", (
                f"Expected allow for dry-run command, got {d_dry}"
            )
            assert d_live == "deny", (
                f"Expected deny for unverified live mutate, got {d_live}"
            )
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
            max_total_ms=250.0,
            step_fn=step,
            verify_fn=verify,
        )
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_gaql_static_analysis() -> Optional[Dict[str, Any]]:
    """Benchmark 4: GAQL static analysis & dry-run validation."""
    if validate_gaql is None or not hasattr(validate_gaql, "validate_gaql"):
        return None

    active_api_version = _resolve_active_api_version()
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
    invalid_hour_date_q = (
        "SELECT campaign.id, segments.hour FROM campaign "
        "WHERE segments.date DURING LAST_7_DAYS"
    )

    def verify() -> Dict[str, Any]:
        if hasattr(validate_gaql, "invalidate_gaql_cache"):
            validate_gaql.invalidate_gaql_cache()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            validate_gaql.validate_gaql(
                "1234567890", active_api_version, valid_q, client=mock_client
            )

            for bad_q in (invalid_or_q, invalid_agg_q, invalid_hour_date_q):
                exited = False
                try:
                    validate_gaql.validate_gaql(
                        "1234567890", active_api_version, bad_q, client=mock_client
                    )
                except SystemExit as exc:
                    exited = exc.code != 0
                assert exited, f"Expected static GAQL failure for query: {bad_q}"
        return {
            "api_version": active_api_version,
            "valid_accepted": True,
            "invalid_rejected": 3,
            "has_sha256_cache": hasattr(validate_gaql, "compute_gaql_cache_key"),
        }

    def step(_i: int) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            validate_gaql.validate_gaql(
                "1234567890", active_api_version, valid_q, client=mock_client
            )

    return _measure_benchmark(
        name="gaql_static_analysis",
        description="Validate GAQL syntax, clauses, date segments, and dry-run response caching",
        iterations=200,
        max_total_ms=150.0,
        step_fn=step,
        verify_fn=verify,
    )


def _bench_protobuf_inspection() -> Optional[Dict[str, Any]]:
    """Benchmark 5: Protobuf type discovery & source inspection."""
    if inspect_object is None or not hasattr(inspect_object, "get_available_types"):
        return None

    active_api_version = _resolve_active_api_version()
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_proto_")
    orig_expanduser = inspect_object.os.path.expanduser
    orig_gettempdir = tempfile.gettempdir
    has_cache = hasattr(inspect_object, "_AVAILABLE_TYPES_CACHE")
    try:
        fake_lib_root = os.path.join(tmp_dir, "client_libs", "google-ads-python")
        v_dir = os.path.join(
            fake_lib_root, "google", "ads", "googleads", active_api_version
        )
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
            types_cold = inspect_object.get_available_types(active_api_version)
            assert "MutateCampaignsRequest" in types_cold
            disk_cache_verified = False

            if has_cache:
                cache_file = os.path.join(
                    tmp_dir, f"gads_assistant_types_{active_api_version}.json"
                )
                assert os.path.isfile(cache_file), "Expected on-disk proto cache file"
                inspect_object._AVAILABLE_TYPES_CACHE.clear()
                orig_glob = inspect_object.glob.glob
                try:

                    def forbid_glob(*_a: Any, **_kw: Any) -> Any:
                        raise AssertionError(
                            "glob.glob called despite warm disk cache"
                        )

                    inspect_object.glob.glob = forbid_glob
                    types_disk = inspect_object.get_available_types(active_api_version)
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
                "api_version": active_api_version,
                "discovered_types": len(types_cold),
                "disk_cache_verified": disk_cache_verified,
            }

        def step(_i: int) -> None:
            inspect_object.get_available_types(active_api_version)

        return _measure_benchmark(
            name="protobuf_type_discovery_and_inspection",
            description="Discover and inspect Protobuf definitions from source and cache",
            iterations=200,
            max_total_ms=60.0,
            step_fn=step,
            verify_fn=verify,
        )
    finally:
        inspect_object.os.path.expanduser = orig_expanduser  # type: ignore[assignment]
        tempfile.gettempdir = orig_gettempdir
        if has_cache:
            inspect_object._AVAILABLE_TYPES_CACHE.clear()
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_client_libs_parallel_sync() -> Optional[Dict[str, Any]]:
    """Benchmark 6: GitHub release metadata check across client libraries."""
    if sync_client_libs is None or not hasattr(
        sync_client_libs, "process_client_libs"
    ):
        return None

    lib_version = _resolve_installed_library_version()
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_sync_")
    orig_fetch = sync_client_libs.fetch_github_latest_release
    orig_detect = sync_client_libs.detect_installed_version
    orig_sys_ver = getattr(sync_client_libs, "detect_system_package_version", None)
    orig_pypi_ver = getattr(sync_client_libs, "fetch_latest_pypi_python_version", None)
    try:
        for repo_name in sync_client_libs.KNOWN_REPOS:
            os.makedirs(os.path.join(tmp_dir, repo_name), exist_ok=True)

        def simulated_network_fetch(_slug: str) -> Tuple[str, str]:
            time.sleep(0.025)
            return (f"v{lib_version}", "https://example.com/release.tar.gz")

        sync_client_libs.fetch_github_latest_release = simulated_network_fetch
        sync_client_libs.detect_installed_version = lambda _e, _p: lib_version
        if orig_sys_ver is not None:
            sync_client_libs.detect_system_package_version = (
                lambda _pkg="google-ads": (lib_version, [])
            )
        if orig_pypi_ver is not None:
            sync_client_libs.fetch_latest_pypi_python_version = (
                lambda _pkg="google-ads", **_kw: lib_version
            )

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
            description="Check client libraries against GitHub releases",
            iterations=5,
            max_total_ms=400.0,
            step_fn=step,
            verify_fn=verify,
        )
    finally:
        sync_client_libs.fetch_github_latest_release = orig_fetch
        sync_client_libs.detect_installed_version = orig_detect
        if orig_sys_ver is not None:
            sync_client_libs.detect_system_package_version = orig_sys_ver
        if orig_pypi_ver is not None:
            sync_client_libs.fetch_latest_pypi_python_version = orig_pypi_ver
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_conversion_csv_validation() -> Optional[Dict[str, Any]]:
    """Benchmark 7: Offline conversion CSV schema, timestamp, and GCLID validation."""
    if validate_conversion_upload is None or not hasattr(
        validate_conversion_upload, "validate_conversion_csv"
    ):
        return None

    active_api_version = _resolve_active_api_version()
    tmp_dir = tempfile.mkdtemp(prefix="gads_bench_csv_")
    try:
        csv_path = os.path.join(tmp_dir, "conversions.csv")
        rows = [
            "gclid,conversion_name,conversion_time,conversion_value,conversion_currency"
        ]
        for i in range(100):
            rows.append(
                f"EAIaIQobChMI_benchmark_gclid_{i:04d},Lead,2026-08-19 12:00:00-04:00,49.99,USD"
            )
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")

        def verify() -> Dict[str, Any]:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                validate_conversion_upload.validate_conversion_csv(
                    csv_path, active_api_version
                )
            return {"rows_per_batch": 100, "api_version": active_api_version}

        def step(_i: int) -> None:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
                io.StringIO()
            ):
                validate_conversion_upload.validate_conversion_csv(
                    csv_path, active_api_version
                )

        return _measure_benchmark(
            name="conversion_csv_validation",
            description="Validate 100-row offline conversion upload CSV (headers, ISO dates, GCLIDs)",
            iterations=50,
            max_total_ms=450.0,
            step_fn=step,
            verify_fn=verify,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _bench_hitl_mutation_receipt_and_sha256() -> Optional[Dict[str, Any]]:
    """Benchmark 8: HITL dry-run receipt signing, verification, and SHA-256 request normalization."""
    if run_mutation is None or not hasattr(
        run_mutation, "compute_mutate_request_sha256"
    ):
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
            "operations": [
                {
                    "update": {
                        "resource_name": "customers/1234567890/campaignBudgets/1",
                        "amount_micros": 50000000,
                    }
                }
            ],
        }
        live_payload = {
            "customer_id": "1234567890",
            "validate_only": False,
            "operations": [
                {
                    "update": {
                        "resource_name": "customers/1234567890/campaignBudgets/1",
                        "amount_micros": 50000000,
                    }
                }
            ],
        }
        tampered_payload = {
            "customer_id": "1234567890",
            "validate_only": False,
            "operations": [
                {
                    "update": {
                        "resource_name": "customers/1234567890/campaignBudgets/1",
                        "amount_micros": 99000000,
                    }
                }
            ],
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
            assert h_dry == h_live, (
                "Canonical SHA256 must match across validate_only=True/False"
            )
            assert h_dry != h_tampered, (
                "Tampered payload must produce a different SHA256"
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

    resolved_version = _resolve_manifest_plugin_version()

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
    """Compares a target benchmark report against a baseline benchmark report.

    Flags a regression if:
      1. Any benchmark's `functional_passed` is False, OR
      2. A benchmark's `performance_passed` is False, OR
      3. `total_ms` increased by more than `max_regression_pct` AND exceeds a 5ms noise floor.
    """
    comparisons: List[Dict[str, Any]] = []
    functional_regressions: List[str] = []
    performance_regressions: List[str] = []

    curr_benches = current.get("benchmarks", {})
    base_benches = baseline.get("benchmarks", {})

    all_names: List[str] = list(curr_benches.keys())
    for b_name in base_benches:
        if b_name not in curr_benches:
            all_names.append(b_name)

    for name in all_names:
        curr_b = curr_benches.get(name)
        base_b = base_benches.get(name)

        if curr_b is None and base_b is not None:
            comparisons.append(
                {
                    "name": name,
                    "in_baseline": True,
                    "in_target": False,
                    "functional_passed": True,
                    "performance_passed": True,
                    "baseline_ms": round(float(base_b.get("total_ms", 0.0)), 3),
                    "current_ms": 0.0,
                    "max_total_ms": float(base_b.get("max_total_ms", 0.0)),
                    "delta_ms": 0.0,
                    "pct_change": 0.0,
                    "speedup_factor": 1.0,
                    "regressed": False,
                }
            )
            continue

        assert curr_b is not None
        curr_ms = float(curr_b["total_ms"])
        func_ok = bool(curr_b["functional_passed"])
        perf_ok = bool(curr_b["performance_passed"])

        if not func_ok:
            functional_regressions.append(name)

        if base_b is not None:
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
                "in_baseline": in_baseline,
                "in_target": True,
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
        "passed": len(functional_regressions) == 0
        and len(performance_regressions) == 0,
        "functional_regressions": functional_regressions,
        "performance_regressions": performance_regressions,
        "comparisons": comparisons,
    }


def format_report_table(
    current: Dict[str, Any],
    comparison: Optional[Dict[str, Any]] = None,
) -> str:
    """Formats benchmark results (and optional two-version comparison) as a readable table."""
    lines: List[str] = []
    lines.append("=" * 108)
    curr_ver_label = str(current.get("version", "unknown"))
    if not curr_ver_label.startswith("v"):
        curr_ver_label = f"v{curr_ver_label}"
    title = (
        f"GOOGLE ADS API DEVELOPER ASSISTANT — BENCHMARK SUITE ({curr_ver_label})"
    )
    if comparison:
        base_ver_label = str(comparison.get("baseline_version", "unknown"))
        if not base_ver_label.startswith("v"):
            base_ver_label = f"v{base_ver_label}"
        title += f" vs Baseline ({base_ver_label})"
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
            status_str = (
                "REGRESS" if c["regressed"] or not c["functional_passed"] else "PASS"
            )
            if not c.get("in_target", True):
                base_str = f"{c['baseline_ms']:>10.2f}"
                curr_str = f"{'N/A':>10}"
                delta_str = f"{'REMOVED':>9}"
                speedup_str = f"{'N/A':>8}"
            elif c.get("in_baseline", True):
                base_str = f"{c['baseline_ms']:>10.2f}"
                curr_str = f"{c['current_ms']:>10.2f}"
                sign = "+" if c["pct_change"] > 0 else ""
                delta_str = f"{sign}{c['pct_change']:.1f}%"
                speedup_str = f"{c['speedup_factor']:.2f}x"
            else:
                base_str = f"{'N/A':>10}"
                curr_str = f"{c['current_ms']:>10.2f}"
                delta_str = f"{'NEW':>9}"
                speedup_str = f"{'N/A':>8}"
            lines.append(
                f"{c['name']:<42} | {func_str:<6} | {base_str} | "
                f"{curr_str} | {c['max_total_ms']:>7.1f}ms | {delta_str:>9} | "
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
            status_str = (
                "PASS"
                if (b["functional_passed"] and b["performance_passed"])
                else "FAIL"
            )
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
    verdict = (
        "PASSED (No functional or performance regressions)"
        if overall_ok
        else "FAILED (Regressions detected)"
    )
    lines.append(
        f"Total Suite Time: {current['suite_total_ms']:.2f} ms | Verdict: {verdict}"
    )
    lines.append("=" * 108)
    return "\n".join(lines)


def _resolve_git_ref_name(spec: str) -> Optional[str]:
    """Checks if `spec` (or `v{spec}`) resolves to a valid Git commit in REPO_ROOT."""
    candidates = [spec]
    if not spec.startswith("v"):
        candidates.append(f"v{spec}")
    for candidate in candidates:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return candidate
    return None


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
        wt_tests = os.path.join(tmp_wt, "tests")
        os.makedirs(wt_tests, exist_ok=True)
        wt_script = os.path.join(wt_tests, "_run_bench_ref.py")
        shutil.copy2(os.path.abspath(__file__), wt_script)

        proc = subprocess.run(
            [sys.executable, wt_script, "--run-current", "--json"],
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
        report = payload.get("current", payload)
        if not report.get("version") or report.get("version") == "unknown":
            report["version"] = git_ref
        return report
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", tmp_wt],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        shutil.rmtree(tmp_wt, ignore_errors=True)


def resolve_version_report(version_spec: str) -> Dict[str, Any]:
    """Resolves a user-supplied version specifier into a benchmark report without any fallback.

    A version specifier can be:
      1. A path to an existing baseline JSON file.
      2. A workspace keyword ('workspace', 'current', 'worktree', '.') to benchmark the working tree.
      3. A saved baseline identifier in `tests/benchmarks/` (`baseline_<spec>.json` or `baseline_v<spec>.json`).
      4. A Git ref (tag, branch, or commit SHA) in the repository.

    Raises:
      ValueError: If `version_spec` is empty or cannot be resolved to a file, workspace, or Git ref.
    """
    spec = (version_spec or "").strip()
    if not spec:
        raise ValueError("Version specifier must not be empty.")

    # 1. Explicit JSON file path
    if os.path.isfile(spec):
        with open(os.path.abspath(spec), "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Explicit current working tree specifier
    if spec.lower() in WORKSPACE_SPECIFIERS:
        return run_all_benchmarks()

    # 3. Saved baseline file in DEFAULT_BASELINE_DIR matching the version specifier
    normalized = spec[1:] if spec.startswith("v") else spec
    candidate_baseline_files = [
        os.path.join(DEFAULT_BASELINE_DIR, f"baseline_{spec}.json"),
        os.path.join(DEFAULT_BASELINE_DIR, f"baseline_v{normalized}.json"),
        os.path.join(DEFAULT_BASELINE_DIR, f"baseline_{normalized}.json"),
    ]
    for candidate_path in candidate_baseline_files:
        if os.path.isfile(candidate_path):
            with open(candidate_path, "r", encoding="utf-8") as f:
                return json.load(f)

    # 4. Valid Git ref (tag, branch, or commit)
    resolved_ref = _resolve_git_ref_name(spec)
    if resolved_ref is not None:
        return run_against_git_ref(resolved_ref)

    raise ValueError(
        f"Unable to resolve version specifier '{version_spec}': not a valid baseline JSON file, "
        f"saved baseline in {DEFAULT_BASELINE_DIR}, Git ref (tag/branch/commit), or 'workspace'."
    )


# ==============================================================================
# Pytest Integration Tests (discovered when running `pytest tests/benchmark_suite.py`)
# ==============================================================================


def test_benchmark_suite_functional_and_performance_budgets() -> None:
    """Runs the benchmark suite on the current workspace and verifies all functional and latency budgets."""
    report = run_all_benchmarks()
    assert report["all_functional_passed"], (
        f"Functional regression in benchmark suite: {json.dumps(report['benchmarks'], indent=2)}"
    )
    assert report["all_performance_passed"], (
        f"Performance budget exceeded in benchmark suite:\n{format_report_table(report)}"
    )


def test_benchmark_suite_two_version_comparison_and_no_fallback() -> None:
    """Verifies explicit two-version comparison, regression detection, and rejection of missing version args."""
    current = resolve_version_report("workspace")

    # 1. Verify no-fallback enforcement when invoked with no arguments
    try:
        main([])
        raise AssertionError("Expected SystemExit when no versions are specified")
    except SystemExit as exc:
        assert exc.code != 0

    # 2. Compare discovered baseline files if at least two exist, or compare against workspace
    baseline_files = sorted(
        glob.glob(os.path.join(DEFAULT_BASELINE_DIR, "baseline_*.json"))
    )
    if len(baseline_files) >= 2:
        base_rep = resolve_version_report(baseline_files[0])
        target_rep = resolve_version_report(baseline_files[-1])
        comp = compare_reports(target_rep, base_rep, max_regression_pct=100.0)
        assert comp["passed"], (
            f"Regression detected between {baseline_files[0]} and {baseline_files[-1]}:\n"
            f"{format_report_table(target_rep, comp)}"
        )
    elif len(baseline_files) == 1:
        base_rep = resolve_version_report(baseline_files[0])
        comp = compare_reports(current, base_rep, max_regression_pct=100.0)
        assert comp["passed"], (
            f"Regression detected against {baseline_files[0]}:\n"
            f"{format_report_table(current, comp)}"
        )

    # 3. Verify that compare_reports catches both functional and latency regressions
    synthetic_slow = json.loads(json.dumps(current))
    first_bench_name = next(iter(current["benchmarks"]))
    synthetic_slow["benchmarks"][first_bench_name]["total_ms"] = (
        current["benchmarks"][first_bench_name]["total_ms"] + 50.0
    )
    comp_regressed = compare_reports(synthetic_slow, current, max_regression_pct=25.0)
    assert not comp_regressed["passed"]
    assert first_bench_name in comp_regressed["performance_regressions"]

    synthetic_broken = json.loads(json.dumps(current))
    synthetic_broken["benchmarks"][first_bench_name]["functional_passed"] = False
    comp_func_broken = compare_reports(
        synthetic_broken, current, max_regression_pct=50.0
    )
    assert not comp_func_broken["passed"]
    assert first_bench_name in comp_func_broken["functional_regressions"]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cross-Version Performance & Functionality Benchmark Suite. "
            "Specify two versions to compare (Git refs, baseline JSON paths, saved version names, or 'workspace')."
        )
    )
    parser.add_argument(
        "versions",
        nargs="*",
        metavar="VERSION",
        help="Two versions to compare: <base_version> <target_version>.",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("BASE_VERSION", "TARGET_VERSION"),
        help="Compare BASE_VERSION against TARGET_VERSION (Git refs, baseline JSON paths, or 'workspace').",
    )
    parser.add_argument(
        "--base-version",
        "--compare-baseline",
        "--compare-git-ref",
        dest="base_version",
        metavar="BASE_VERSION",
        help="Base version (Git ref, baseline JSON path, or 'workspace') to compare from.",
    )
    parser.add_argument(
        "--target-version",
        dest="target_version",
        metavar="TARGET_VERSION",
        help="Target version (Git ref, baseline JSON path, or 'workspace') to compare against BASE_VERSION.",
    )
    parser.add_argument(
        "--run-current",
        action="store_true",
        help="Run benchmarks on the current working tree only without comparing two versions.",
    )
    parser.add_argument(
        "--save-baseline",
        metavar="PATH",
        help="Write the current working tree benchmark report as a JSON baseline to PATH.",
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
    args = parser.parse_args(argv)

    if args.save_git_ref_baseline:
        ref_name, ref_out = args.save_git_ref_baseline
        ref_report = run_against_git_ref(ref_name)
        out_path = os.path.abspath(ref_out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ref_report, f, indent=2)
        if not args.json:
            print(f"Saved git ref '{ref_name}' benchmark baseline to {out_path}")
        if (
            not args.save_baseline
            and not args.run_current
            and not args.compare
            and not args.versions
            and not args.base_version
            and not args.target_version
        ):
            return 0

    if args.save_baseline:
        current_report = run_all_benchmarks()
        out_path = os.path.abspath(args.save_baseline)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(current_report, f, indent=2)
        if not args.json:
            print(f"Saved benchmark baseline to {out_path}")
        if (
            not args.run_current
            and not args.compare
            and not args.versions
            and not args.base_version
            and not args.target_version
        ):
            return 0

    # Resolve the two versions to compare (no fallback is assumed)
    base_spec: Optional[str] = None
    target_spec: Optional[str] = None

    if args.compare:
        if args.versions or args.base_version or args.target_version:
            parser.error(
                "Do not combine --compare with positional versions or --base-version/--target-version."
            )
        base_spec, target_spec = args.compare[0], args.compare[1]
    elif args.base_version or args.target_version:
        if args.versions:
            parser.error(
                "Do not combine --base-version/--target-version with positional version arguments."
            )
        if not (args.base_version and args.target_version):
            parser.error(
                "Both --base-version and --target-version must be specified; no version fallback is assumed."
            )
        base_spec, target_spec = args.base_version, args.target_version
    elif args.versions:
        if len(args.versions) != 2:
            parser.error(
                f"Expected exactly 2 versions to compare (<base_version> <target_version>), got {len(args.versions)}."
            )
        base_spec, target_spec = args.versions[0], args.versions[1]
    elif not args.run_current:
        parser.error(
            "You must specify the two versions to compare (e.g., `python3 tests/benchmark_suite.py <base_version> <target_version>` "
            "or `--compare <base_version> <target_version>`), or pass `--run-current`. No default version fallback is assumed."
        )

    if base_spec is not None and target_spec is not None:
        try:
            baseline_report = resolve_version_report(base_spec)
            target_report = resolve_version_report(target_spec)
        except ValueError as exc:
            parser.error(str(exc))

        comparison = compare_reports(
            target_report,
            baseline_report,
            max_regression_pct=args.max_regression_pct,
        )

        if args.json:
            payload: Dict[str, Any] = {
                "baseline": baseline_report,
                "current": target_report,
                "comparison": comparison,
            }
            print(json.dumps(payload, indent=2))
        else:
            print(format_report_table(target_report, comparison))

        return 0 if comparison["passed"] else 1

    # Single-tree execution when --run-current is explicitly passed
    current_report = run_all_benchmarks()
    if args.json:
        print(json.dumps({"current": current_report}, indent=2))
    else:
        print(format_report_table(current_report, None))

    passed = (
        current_report["all_functional_passed"]
        and current_report["all_performance_passed"]
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
