# Test Coverage Guide (`tests/run_coverage.py`)

This document explains how to run the line-coverage tool for the Google Ads API Developer Assistant, how to interpret every section and column of the output, and what the **`Miss`** column and **`-> MISSED`** line lists indicate.

---

## 1. Running Coverage from the Command Line

Coverage is integrated into both `pytest` (via [`tests/conftest.py`](./conftest.py)) and the standalone [`tests/run_coverage.py`](./run_coverage.py) CLI script.

### Option A: Using `pytest`

```bash
# Instant report from cached coverage data + assert all modules & categories >= 80% (~0.8s)
pytest tests/run_coverage.py

# Include exact missed line numbers for each module
pytest tests/run_coverage.py --show-missed

# Run pytest with live coverage collection in fast mode (~35s)
pytest --coverage --fast

# Run full pytest suite (including all 120 financial limit parametrized cases) with live coverage
pytest --coverage
```

### Option B: Using `python3 tests/run_coverage.py`

```bash
# Instant report from the most recent coverage run (< 0.2s)
python3 tests/run_coverage.py --report-only

# Instant report with missed line numbers
python3 tests/run_coverage.py --report-only --show-missed

# Fast re-collection (~35s: runs pytest and merges cached subprocess coverage)
python3 tests/run_coverage.py --fast

# Full collection (runs all pytest cases + bash tests/test_plugin_scripts.sh subprocesses)
python3 tests/run_coverage.py

# Machine-readable JSON output
python3 tests/run_coverage.py --report-only --json
```

---

## 2. Execution Progress Messages

When running a full coverage collection (`python3 tests/run_coverage.py`), the runner executes three sequential phases and prints progress notices so you know the process is still active after `pytest` finishes printing its dot progress bar:

1. **Step 1/3 — In-Process `pytest` Suite**:
   ```text
   [coverage] Step 1/3: Running pytest suite under line-coverage instrumentation — please wait...
   ........................................................................ [ 49%]
   ........................................................................ [ 99%]
   .                                                                        [100%]
   [coverage] Pytest phase complete — process is still working on subprocess & statement coverage analysis, please wait...
   299 passed in 34.01s
   ```
2. **Step 2/3 — CLI Integration Subprocess Suite**:
   ```text
   [coverage] Step 2/3: Running CLI integration subprocess suite (tests/test_plugin_scripts.sh) — this step may take a while, process is still working, please wait...
   ```
   *(Skipped when `--fast` or `--report-only` is used.)*
3. **Step 3/3 — Statement Analysis & Report Generation**:
   ```text
   [coverage] Step 3/3: Saving coverage data and analyzing executable statements — process is still working, please wait...
   [coverage] Building coverage report across 21 modules — process is still working, please wait...
   ```

---

## 3. Understanding the Coverage Report Tables

The report prints two tables:

1. **Module Coverage Table**: Line coverage for each individual Python script under `plugins/google-ads-api-developer-assistant/` and the root `set_financial_limits.py` wrapper.
2. **Category Coverage Table**: Aggregated line coverage grouped by component category (`config`, `sidecars/google-ads-a2a-service`, each skill under `skills/<skill-name>`, and `root`).

### Column Definitions

| Column | Meaning | Formula / Source |
| :--- | :--- | :--- |
| **`Module` / `Category`** | Relative path of the Python module (or component category name) | Tracked `.py` files (excluding empty `__init__.py` files) |
| **`Stmts`** | Total number of **executable Python statements** (lines) in the file or category | Determined via Python's `trace._find_executable_linenos()` (excludes comments, blank lines, and docstrings) |
| **`InProc`** | Number of executable lines hit **in-process** inside the `pytest` runner | Tracked via `sys.monitoring` (`PEP 669`) inside the `pytest` process |
| **`InProc%`** | Percentage of executable lines hit in-process | $\frac{\text{InProc}}{\text{Stmts}} \times 100\%$ |
| **`Combined`** | Total executable lines hit across **both** in-process `pytest` tests **and** child CLI subprocesses | Union of `InProc` lines and subprocess line hits (`cov_*.json`) |
| **`Miss`** | Number of executable lines **not executed** by any test (in-process or subprocess) | $\text{Stmts} - \text{Combined}$ |
| **`Comb%`** | Final combined line coverage percentage | $\frac{\text{Combined}}{\text{Stmts}} \times 100\% = \left(1 - \frac{\text{Miss}}{\text{Stmts}}\right) \times 100\%$ |

### Why Both `InProc` and `Combined` Are Reported

Many tests in [`tests/test_components.py`](./test_components.py), [`tests/test_hitl_mutation_guard.py`](./test_hitl_mutation_guard.py), [`tests/test_python_315.py`](./test_python_315.py), and [`tests/test_plugin_scripts.sh`](./test_plugin_scripts.sh) invoke the plugin scripts as real CLI subprocesses (`subprocess.run([sys.executable, ...])`) to verify end-to-end command-line behavior, exit codes, and `sitecustomize.py` / PreToolUse hooks:

- **`InProc`** only counts lines executed when a module is imported directly into the `pytest` process. For example, thin CLI wrapper scripts like `config/set_financial_limits.py` are tested exclusively via CLI subprocesses, so their `InProc%` is `0.0%` while their `Comb%` is `97.7%`.
- **`Combined`** merges in-process hits with subprocess hits captured via an injected `sitecustomize.py` hook (`sys.monitoring`), providing the true end-to-end coverage (`Comb%`).

---

## 4. What `Miss` and `-> MISSED` Indicate

### What `Miss` Means

The **`Miss`** column is the exact count of executable statement lines (`Stmts`) in a module or category that were **never reached** during the test run:

$$\text{Miss} = \text{Stmts} - \text{Combined}$$

When you run with `--show-missed`:

```bash
python3 tests/run_coverage.py --report-only --show-missed
```

each module is followed by a `-> MISSED (N): [...]` line listing the exact **1-indexed line numbers** in that source file that were not executed, for example:

```text
skills/ext-version/scripts/get_extension_version.py            27      23    85.2%        24      3    88.9%
    -> MISSED (3): [44, 45, 46]
```

This means out of `27` executable lines in `get_extension_version.py`, `24` were executed (`88.9%`) and `3` lines (lines `44`, `45`, and `46`) were not executed.

### Why Specific Lines Are Missed

The remaining ~15.5% of missed lines across the repository fall into six defensive or environment-specific categories:

1. **Python `< 3.11` `tomllib` Import Fallbacks**
   - On Python 3.11+ (including Python 3.15), `import tomllib` succeeds in the `try:` block at import time. The `except ImportError:` fallback branches that load `tomli` or set `tomllib = None` (e.g., in `config/config_init.py`, `create_pmax_webpage_filter.py`, `get_recent_gclids.py`, and `troubleshoot_conversions.py`) are only reachable on Python 3.10 or older.

2. **Defensive Filesystem & Permission Exception Handlers (`except OSError:`)**
   - File creation, atomic renames, cache cleanups, and `os.chmod(..., 0o600)` calls are wrapped in `try ... except OSError: pass` guards so the assistant does not crash on read-only mounts, Windows filesystems, or concurrent process writes.

3. **Secondary-Language Build File Regexes & Archive Recovery (`sync_client_libs.py`)**
   - `sync_client_libs.py` includes fallback parsers for non-Python client library build manifests (`composer.json`, `build.gradle`, `.gemspec`, `Common.props`) and defensive error recovery for corrupted tarballs or network disconnects.

4. **Interactive Terminal Retry Loops (`sys.stdin.isatty()`)**
   - Interactive CLI wizard sub-menus (such as multi-step category/service/field browsing in `set_financial_limits.py` or interactive API version prompts when no configuration exists) include `KeyboardInterrupt` / `EOFError` and retry branches designed for human terminal sessions.

5. **Deep Static AST & Protobuf Descriptor Fallbacks (`run_mutation.py`)**
   - `run_mutation.py` contains multi-layered static AST visitors and runtime Protobuf reflection guards for unusual third-party script patterns (e.g., dynamic attribute lookups, nested `FieldMask` expressions, or unparseable syntax).

6. **`if __name__ == "__main__":` Guards in In-Process-Tested Scripts**
   - When a script's `main()` function is tested directly in-process via `pytest` rather than spawning a separate OS process, the 1–3 lines inside the `if __name__ == "__main__":` block at the bottom of the file are not entered.

---

## 5. What Missed Lines Mean for the Tests

1. **`Miss > 0` Is Not a Test Failure**
   - A non-zero `Miss` count does **not** mean a test failed or that a bug was found. It simply means those specific lines of source code were not executed during the test run.
   - The coverage assertion in [`test_coverage_above_80_percent`](./run_coverage.py) verifies that every individual module and every category meets or exceeds the **80.0% coverage requirement** (currently **84.5% overall**).

2. **Why 100% Coverage Is Not Expected in a Single Environment**
   - A single test run executes on one Python version (e.g., Python 3.15) and one operating system (e.g., Linux). Mutually exclusive compatibility branches (such as `except ImportError:` for Python `< 3.11` or Windows-specific path/permission branches) **cannot** run in the same process unless artificially mocked.
   - Likewise, defensive OS error handlers (`except OSError: pass` around `os.chmod`, `os.remove`, or temp-file writes) only execute when the underlying filesystem fails (e.g., disk full, read-only mount, or permission denied).

3. **Core Logic vs. Defensive Guardrails**
   - **Covered (`84.5%`)**: All primary functional paths — including all 120 `financial_limits` service/field combinations, the 4-Step HITL mutation guard (`run_mutation.py`, `config_init.py`, `sitecustomize.py`), account/campaign/ad-group/ad creation, A2A sidecar endpoints, GAQL validation, conversion troubleshooting, and client library syncing — are exercised by unit and integration tests.
   - **Missed (`15.5%`)**: Last-resort defensive fallbacks, OS exception handlers, interactive TTY retry loops, and secondary-language manifest regexes.

4. **How to Use `Miss` When Adding New Code**
   - **Actionable gap**: If you add a new feature and `--show-missed` shows a contiguous block of 10+ missed lines inside your new function, that indicates a functional branch (e.g., an untested CLI flag or API payload type) that should have a unit test added.
   - **Benign defensive line**: Isolated 1–3 line ranges in `--show-missed` (such as `except OSError:` or `if __name__ == "__main__":`) are normal defensive guards and do not require artificial mocking.

---

## 6. How Coverage Data Is Stored

Coverage artifacts are stored under `.pytest_cache/coverage/`:

- `.pytest_cache/coverage/cov_data/inproc_hits.json`: Line hits recorded in-process during `pytest`.
- `.pytest_cache/coverage/cov_data/cov_<pid>_<uuid>.json`: Line hits recorded by child Python subprocesses via `sys.monitoring`.
- `.pytest_cache/coverage/cov_hook/sitecustomize.py`: Temporary `sys.monitoring` hook automatically prepended to `PYTHONPATH` during coverage collection runs (and chained to `config/sitecustomize.py` when present).

