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

"""Pytest hooks for built-in line coverage collection and reporting (`pytest --coverage`)."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import sys
from typing import Any
import pytest

_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import run_coverage  # noqa: E402


_INPROC_HITS: dict[str, set[int]] = {}
_STOP_INPROC: Callable[[], None] | None = None
_COVERAGE_ACTIVE = False


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("coverage", "Plugin line and category coverage reporting")
    group.addoption(
        "--coverage",
        action="store_true",
        default=False,
        help="Collect in-process + subprocess line coverage and print the module/category report.",
    )
    group.addoption(
        "--coverage-report",
        action="store_true",
        default=False,
        help="Print the per-module and per-category coverage report at the end of the pytest run.",
    )
    group.addoption(
        "--show-missed",
        action="store_true",
        default=False,
        help="Include missed line numbers for each module in the coverage report.",
    )
    group.addoption(
        "--fast",
        action="store_true",
        default=False,
        help="Skip 119 redundant parametrized iterations of test_each_financial_limit_value_enforcement.",
    )
    group.addoption(
        "--no-clean",
        action="store_true",
        default=False,
        help="Preserve prior coverage hit files for incremental union across runs.",
    )


def pytest_configure(config: pytest.Config) -> None:
    global _COVERAGE_ACTIVE, _INPROC_HITS, _STOP_INPROC
    if not config.getoption("--coverage"):
        return

    if not config.getoption("--no-clean") and run_coverage.COV_DATA_DIR.exists():
        import shutil

        shutil.rmtree(run_coverage.COV_DATA_DIR)

    target_files = run_coverage.get_target_files()
    target_paths_list = [str(p.resolve()) for p in target_files]
    _INPROC_HITS = {p: set() for p in target_paths_list}

    run_coverage._write_subprocess_coverage_hooks(target_paths_list)

    existing_pp = os.environ.get("PYTHONPATH", "")
    hook_dir_str = str(run_coverage.COV_HOOK_DIR)
    if hook_dir_str not in existing_pp.split(os.pathsep):
        os.environ["PYTHONPATH"] = (
            f"{hook_dir_str}{os.pathsep}{existing_pp}" if existing_pp else hook_dir_str
        )
    os.environ["PYTHONNOUSERSITE"] = "0"

    _STOP_INPROC = run_coverage.start_inproc_coverage(
        _INPROC_HITS, tool_name="pytest_conftest_coverage"
    )
    _COVERAGE_ACTIVE = _STOP_INPROC is not None


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not config.getoption("--fast"):
        return
    kept: list[pytest.Item] = []
    deselected: list[pytest.Item] = []
    for item in items:
        if (
            "test_each_financial_limit_value_enforcement" in item.nodeid
            and "CampaignBudgetService.amount_micros" not in item.nodeid
        ):
            deselected.append(item)
        else:
            kept.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _COVERAGE_ACTIVE, _STOP_INPROC
    if _COVERAGE_ACTIVE:
        print(
            "\n[coverage] Saving and merging in-process coverage data — process is still working, please wait...",
            flush=True,
        )
        if _STOP_INPROC is not None:
            _STOP_INPROC()
            _STOP_INPROC = None
        _COVERAGE_ACTIVE = False

        run_coverage.COV_DATA_DIR.mkdir(parents=True, exist_ok=True)
        inproc_file = run_coverage.COV_DATA_DIR / "inproc_hits.json"
        merged_inproc: dict[str, set[int]] = {
            k: set(v) for k, v in _INPROC_HITS.items() if v
        }
        if inproc_file.is_file():
            try:
                old_data = json.loads(inproc_file.read_text(encoding="utf-8"))
                for k, v in old_data.items():
                    merged_inproc.setdefault(k, set()).update(v)
            except Exception:
                pass
        inproc_file.write_text(
            json.dumps({k: sorted(v) for k, v in merged_inproc.items() if v}),
            encoding="utf-8",
        )


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    if os.environ.get("GADS_RUNNING_FROM_RUN_COVERAGE") == "1":
        terminalreporter.write_line(
            "\n[coverage] Pytest phase complete — process is still working on subprocess & statement coverage analysis, please wait..."
        )
        return
    args_str = " ".join(str(a) for a in config.args)
    if (
        config.getoption("--coverage")
        or config.getoption("--coverage-report")
        or "run_coverage.py" in args_str
    ):
        run_coverage.compute_and_print_report(
            show_missed=bool(config.getoption("--show-missed")),
            json_output=False,
        )


