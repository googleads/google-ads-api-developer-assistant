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

"""Command-line line-coverage runner and reporter for the Google Ads API Developer Assistant.

Measures both in-process (`pytest`) and subprocess (`sys.monitoring` via `sitecustomize.py`)
line execution across all plugin Python modules and prints per-module and per-category
coverage tables.

Usage:
    # Full coverage run (pytest + CLI integration scripts):
    python3 tests/run_coverage.py

    # Fast coverage run (~35s, reuses cached subprocess coverage and skips redundant
    # 119-item parametrized loop):
    python3 tests/run_coverage.py --fast

    # Instant report from the most recent coverage run (<0.2s):
    python3 tests/run_coverage.py --report-only

    # Include missed line numbers for each module:
    python3 tests/run_coverage.py --report-only --show-missed
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import trace
from typing import Any
import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
CACHE_ROOT = REPO_ROOT / ".pytest_cache" / "coverage"
COV_HOOK_DIR = CACHE_ROOT / "cov_hook"
COV_DATA_DIR = CACHE_ROOT / "cov_data"


def get_target_files() -> list[Path]:
    """Returns all tracked Python source files in the plugin and root."""
    files = sorted(
        [
            *PLUGIN_ROOT.glob("config/*.py"),
            *PLUGIN_ROOT.glob("skills/*/scripts/*.py"),
            *PLUGIN_ROOT.glob("sidecars/*/*.py"),
            REPO_ROOT / "set_financial_limits.py",
        ]
    )
    return [p for p in files if p.name != "__init__.py"]


def _write_subprocess_coverage_hooks(target_paths_list: list[str]) -> None:
    """Writes usercustomize.py and chained sitecustomize.py for subprocess coverage."""
    if COV_HOOK_DIR.exists():
        shutil.rmtree(COV_HOOK_DIR)
    COV_HOOK_DIR.mkdir(parents=True, exist_ok=True)
    COV_DATA_DIR.mkdir(parents=True, exist_ok=True)

    usercustomize_code = f"""import atexit
import json
import os
from pathlib import Path
import sys
import uuid

TARGET_PATHS = set({target_paths_list!r})
COV_DATA_DIR = Path({str(COV_DATA_DIR)!r})
_hits = {{p: set() for p in TARGET_PATHS}}
_cache = {{}}

try:
    TOOL_ID = 4
    sys.monitoring.use_tool_id(TOOL_ID, "subproc_cov")

    def _on_line(code, line_number):
        raw = code.co_filename
        resolved = _cache.get(raw, False)
        if resolved is False:
            try:
                p = str(Path(raw).resolve())
            except OSError:
                p = None
            resolved = p if p in TARGET_PATHS else None
            _cache[raw] = resolved
        if resolved is not None:
            _hits[resolved].add(line_number)
        return sys.monitoring.DISABLE

    sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.LINE, _on_line)
    sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.LINE)

    @atexit.register
    def _dump():
        non_empty = {{k: list(v) for k, v in _hits.items() if v}}
        if non_empty:
            out_file = COV_DATA_DIR / f"cov_{{os.getpid()}}_{{uuid.uuid4().hex[:8]}}.json"
            try:
                out_file.write_text(json.dumps(non_empty), encoding="utf-8")
            except OSError:
                pass
except Exception:
    pass
"""
    (COV_HOOK_DIR / "usercustomize.py").write_text(usercustomize_code, encoding="utf-8")
    (COV_HOOK_DIR / "sitecustomize.py").write_text(
        usercustomize_code
        + "\n# Chain to next sitecustomize on sys.path if present\n"
        + "import importlib.util\n"
        + "for _p in sys.path:\n"
        + "    if _p != "
        + repr(str(COV_HOOK_DIR))
        + ":\n"
        + "        _cand = os.path.join(_p, 'sitecustomize.py')\n"
        + "        if os.path.isfile(_cand):\n"
        + "            _spec = importlib.util.spec_from_file_location('_chained_sitecustomize', _cand)\n"
        + "            if _spec and _spec.loader:\n"
        + "                _m = importlib.util.module_from_spec(_spec)\n"
        + "                _spec.loader.exec_module(_m)\n"
        + "            break\n",
        encoding="utf-8",
    )


def run_coverage_collection(fast_mode: bool = True, clean: bool = False) -> int:
    """Runs pytest (and bash script tests when not in fast mode) under sys.monitoring."""
    target_files = get_target_files()
    target_paths_list = [str(p.resolve()) for p in target_files]
    inproc_hits: dict[str, set[int]] = {p: set() for p in target_paths_list}

    if clean and COV_DATA_DIR.exists():
        shutil.rmtree(COV_DATA_DIR)

    _write_subprocess_coverage_hooks(target_paths_list)

    existing_pp = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = (
        f"{COV_HOOK_DIR}:{existing_pp}" if existing_pp else str(COV_HOOK_DIR)
    )
    os.environ["PYTHONNOUSERSITE"] = "0"

    tool_id = sys.monitoring.COVERAGE_ID
    sys.monitoring.use_tool_id(tool_id, "pytest_coverage")
    inproc_cache: dict[str, str | None] = {}

    def on_line(code: Any, line_number: int) -> Any:
        raw = code.co_filename
        resolved = inproc_cache.get(raw, False)
        if resolved is False:
            try:
                p = str(Path(raw).resolve())
            except OSError:
                p = None
            resolved = p if p in inproc_hits else None
            inproc_cache[raw] = resolved
        if resolved is not None:
            inproc_hits[resolved].add(line_number)
        return sys.monitoring.DISABLE

    sys.monitoring.register_callback(tool_id, sys.monitoring.events.LINE, on_line)
    sys.monitoring.set_events(tool_id, sys.monitoring.events.LINE)

    pytest_args = ["-q", "--ignore=tests/run_coverage.py"]
    if fast_mode:
        pytest_args.extend(
            [
                "-k",
                "not test_each_financial_limit_value_enforcement or CampaignBudgetService.amount_micros",
            ]
        )
    total_steps = 2 if fast_mode else 3
    print(
        f"[coverage] Step 1/{total_steps}: Running pytest suite under line-coverage instrumentation — please wait...",
        flush=True,
    )
    os.environ["GADS_RUNNING_FROM_RUN_COVERAGE"] = "1"
    try:
        exit_code = int(pytest.main(pytest_args))
    finally:
        os.environ.pop("GADS_RUNNING_FROM_RUN_COVERAGE", None)

    sys.monitoring.set_events(tool_id, 0)
    sys.monitoring.free_tool_id(tool_id)

    if not fast_mode:
        print(
            f"\n[coverage] Step 2/{total_steps}: Running CLI integration subprocess suite (tests/test_plugin_scripts.sh) "
            "— this step may take a while, process is still working, please wait...",
            flush=True,
        )
        env = os.environ.copy()
        env["PATH"] = f"{Path(sys.executable).parent}:{env.get('PATH', '')}"
        subprocess.run(
            ["bash", str(REPO_ROOT / "tests" / "test_plugin_scripts.sh")],
            cwd=str(REPO_ROOT),
            env=env,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    final_step = 2 if fast_mode else 3
    print(
        f"\n[coverage] Step {final_step}/{total_steps}: Saving coverage data and analyzing executable statements "
        "— process is still working, please wait...",
        flush=True,
    )
    inproc_file = COV_DATA_DIR / "inproc_hits.json"
    merged_inproc: dict[str, set[int]] = {
        k: set(v) for k, v in inproc_hits.items() if v
    }
    if inproc_file.is_file():
        try:
            old_data = json.loads(inproc_file.read_text(encoding="utf-8"))
            for k, v in old_data.items():
                merged_inproc.setdefault(k, set()).update(v)
        except Exception:
            pass
    if merged_inproc:
        inproc_file.write_text(
            json.dumps({k: sorted(v) for k, v in merged_inproc.items() if v}),
            encoding="utf-8",
        )
    return exit_code


def compute_and_print_report(
    show_missed: bool = False,
    json_output: bool = False,
    print_tables: bool = True,
) -> dict[str, Any]:
    """Loads saved coverage data and prints module and category coverage tables."""
    target_files = get_target_files()
    if print_tables and not json_output:
        print(
            f"[coverage] Building coverage report across {len(target_files)} modules — process is still working, please wait...",
            flush=True,
        )
    target_paths_list = [str(p.resolve()) for p in target_files]
    inproc_hits: dict[str, set[int]] = {p: set() for p in target_paths_list}
    combined_hits: dict[str, set[int]] = {p: set() for p in target_paths_list}

    inproc_file = COV_DATA_DIR / "inproc_hits.json"
    if inproc_file.is_file():
        try:
            data = json.loads(inproc_file.read_text(encoding="utf-8"))
            for k, v in data.items():
                if k in inproc_hits:
                    inproc_hits[k].update(v)
                    combined_hits[k].update(v)
        except Exception:
            pass

    for jf in COV_DATA_DIR.glob("cov_*.json"):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            for k, v in data.items():
                if k in combined_hits:
                    combined_hits[k].update(v)
        except Exception:
            pass

    modules_report: list[dict[str, Any]] = []
    category_stats: dict[str, list[int]] = {}
    total_stmts = 0
    total_inproc = 0
    total_comb = 0

    for p in target_files:
        abs_p = str(p.resolve())
        try:
            rel_p = str(p.relative_to(PLUGIN_ROOT))
            parts = rel_p.split("/")
            if parts[0] in ("skills", "sidecars") and len(parts) >= 2:
                cat = f"{parts[0]}/{parts[1]}"
            else:
                cat = parts[0]
        except ValueError:
            rel_p = str(p.relative_to(REPO_ROOT)) + " (root)"
            cat = "root"

        exec_lines = trace._find_executable_linenos(abs_p)
        executable_set = {k for k in exec_lines.keys() if isinstance(k, int) and k > 0}
        inproc_set = inproc_hits[abs_p] & executable_set
        comb_set = combined_hits[abs_p] & executable_set

        stmts = len(executable_set)
        ip_hits = len(inproc_set)
        cb_hits = len(comb_set)
        cb_miss = stmts - cb_hits
        ip_pct = (ip_hits / stmts * 100.0) if stmts > 0 else 100.0
        cb_pct = (cb_hits / stmts * 100.0) if stmts > 0 else 100.0
        missed_lines = sorted(executable_set - comb_set)

        total_stmts += stmts
        total_inproc += ip_hits
        total_comb += cb_hits
        if cat not in category_stats:
            category_stats[cat] = [0, 0, 0]
        category_stats[cat][0] += stmts
        category_stats[cat][1] += ip_hits
        category_stats[cat][2] += cb_hits

        modules_report.append(
            {
                "module": rel_p,
                "category": cat,
                "statements": stmts,
                "inproc_covered": ip_hits,
                "inproc_percent": round(ip_pct, 1),
                "combined_covered": cb_hits,
                "missed": cb_miss,
                "combined_percent": round(cb_pct, 1),
                "missed_lines": missed_lines,
            }
        )

    categories_report: list[dict[str, Any]] = []
    for cat, (c_stmts, c_ip, c_cb) in sorted(category_stats.items()):
        c_miss = c_stmts - c_cb
        c_ip_pct = (c_ip / c_stmts * 100.0) if c_stmts > 0 else 100.0
        c_cb_pct = (c_cb / c_stmts * 100.0) if c_stmts > 0 else 100.0
        categories_report.append(
            {
                "category": cat,
                "statements": c_stmts,
                "inproc_covered": c_ip,
                "inproc_percent": round(c_ip_pct, 1),
                "combined_covered": c_cb,
                "missed": c_miss,
                "combined_percent": round(c_cb_pct, 1),
            }
        )

    total_miss = total_stmts - total_comb
    total_ip_pct = (total_inproc / total_stmts * 100.0) if total_stmts > 0 else 100.0
    total_cb_pct = (total_comb / total_stmts * 100.0) if total_stmts > 0 else 100.0

    summary = {
        "modules": modules_report,
        "categories": categories_report,
        "total": {
            "statements": total_stmts,
            "inproc_covered": total_inproc,
            "inproc_percent": round(total_ip_pct, 1),
            "combined_covered": total_comb,
            "missed": total_miss,
            "combined_percent": round(total_cb_pct, 1),
        },
    }

    if json_output:
        print(json.dumps(summary, indent=2))
        return summary

    if not print_tables:
        return summary

    print("\n" + "=" * 112)
    print(
        f"{'Module':<58} {'Stmts':>6} {'InProc':>7} {'InProc%':>8} {'Combined':>9} {'Miss':>6} {'Comb%':>8}"
    )
    print("-" * 112)
    for m in modules_report:
        print(
            f"{m['module']:<58} {m['statements']:>6} {m['inproc_covered']:>7} "
            f"{m['inproc_percent']:>7.1f}% {m['combined_covered']:>9} {m['missed']:>6} "
            f"{m['combined_percent']:>7.1f}%"
        )
        if show_missed and m["missed_lines"]:
            print(f"    -> MISSED ({len(m['missed_lines'])}): {m['missed_lines']}")

    print("-" * 112)
    print(
        f"{'TOTAL':<58} {total_stmts:>6} {total_inproc:>7} {total_ip_pct:>7.1f}% "
        f"{total_comb:>9} {total_miss:>6} {total_cb_pct:>7.1f}%"
    )
    print("=" * 112)

    print("\n" + "=" * 112)
    print(
        f"{'Category':<58} {'Stmts':>6} {'InProc':>7} {'InProc%':>8} {'Combined':>9} {'Miss':>6} {'Comb%':>8}"
    )
    print("-" * 112)
    for c in categories_report:
        print(
            f"{c['category']:<58} {c['statements']:>6} {c['inproc_covered']:>7} "
            f"{c['inproc_percent']:>7.1f}% {c['combined_covered']:>9} {c['missed']:>6} "
            f"{c['combined_percent']:>7.1f}%"
        )
    print("-" * 112)
    print(
        f"{'TOTAL':<58} {total_stmts:>6} {total_inproc:>7} {total_ip_pct:>7.1f}% "
        f"{total_comb:>9} {total_miss:>6} {total_cb_pct:>7.1f}%"
    )
    print("=" * 112)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run and print line coverage across all plugin modules and categories."
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip redundant 119-item parametrized loop and reuse cached subprocess coverage (~35s).",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print the coverage report immediately from cached coverage data without re-running tests.",
    )
    parser.add_argument(
        "--show-missed",
        action="store_true",
        help="Display missed line numbers under each module.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the coverage report as JSON.",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    if not args.report_only:
        exit_code = run_coverage_collection(fast_mode=args.fast)
    elif not COV_DATA_DIR.exists() or not any(COV_DATA_DIR.glob("*.json")):
        print(
            "No cached coverage data found in .pytest_cache/coverage/cov_data; running --fast collection first...",
            file=sys.stderr,
        )
        exit_code = run_coverage_collection(fast_mode=True)

    compute_and_print_report(show_missed=args.show_missed, json_output=args.json)
    return exit_code


def test_coverage_above_80_percent() -> None:
    """Pytest entry point (`pytest tests/run_coverage.py`) that verifies >=80% coverage."""
    if not COV_DATA_DIR.exists() or not (COV_DATA_DIR / "inproc_hits.json").is_file():
        pytest.skip(
            "No cached coverage data found; run `pytest --coverage --fast` or `python3 tests/run_coverage.py`."
        )
    summary = compute_and_print_report(show_missed=False, json_output=False, print_tables=False)
    for cat_entry in summary["categories"]:
        assert cat_entry["combined_percent"] >= 80.0, (
            f"Category {cat_entry['category']} coverage {cat_entry['combined_percent']}% is below 80.0%"
        )
    for mod_entry in summary["modules"]:
        assert mod_entry["combined_percent"] >= 80.0, (
            f"Module {mod_entry['module']} coverage {mod_entry['combined_percent']}% is below 80.0%"
        )


if __name__ == "__main__":
    sys.exit(main())


