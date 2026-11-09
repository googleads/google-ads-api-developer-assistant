# Test Coverage Guide (`tests/run_coverage.py`)

This guide explains how to run the line-coverage tool for the Google Ads API Developer Assistant. It also explains each column in the output and what **`Miss`** and **`-> MISSED`** mean.

---

## 1. Run Coverage from the Command Line

You can run coverage through `pytest` (using [`tests/conftest.py`](./conftest.py)) or with the [`tests/run_coverage.py`](./run_coverage.py) script.

### Option A: Use `pytest`

```bash
# Show the report from cached coverage data and check that all modules and categories are >= 80% (~0.8s)
pytest tests/run_coverage.py

# Show the missed line numbers for each module
pytest tests/run_coverage.py --show-missed

# Run pytest and collect live coverage in fast mode (~35s)
pytest --coverage --fast

# Run the full pytest suite (including all 120 financial limit cases) with live coverage
pytest --coverage
```

### Option B: Use `python3 tests/run_coverage.py`

```bash
# Show the report from the latest coverage run (< 0.2s)
python3 tests/run_coverage.py --report-only

# Show the report with missed line numbers
python3 tests/run_coverage.py --report-only --show-missed

# Collect coverage in fast mode (~35s: runs pytest and merges cached subprocess coverage)
python3 tests/run_coverage.py --fast

# Collect full coverage (runs all pytest cases and bash tests/test_plugin_scripts.sh subprocesses)
python3 tests/run_coverage.py

# Print JSON output
python3 tests/run_coverage.py --report-only --json
```

---

## 2. Progress Messages During Execution

When you run a full coverage check (`python3 tests/run_coverage.py`), the script runs three steps in order. It prints progress messages so you know the process is still running after `pytest` finishes:

1. **Step 1/3 — In-Process `pytest` Suite**:
   ```text
   [coverage] Step 1/3: Running pytest suite under line-coverage instrumentation — please wait...
   ........................................................................ [ 49%]
   ........................................................................ [ 99%]
   .                                                                        [100%]
   [coverage] Pytest phase complete — process is still working on subprocess & statement coverage analysis, please wait...
   300 passed in 34.01s
   ```
2. **Step 2/3 — CLI Subprocess Suite**:
   ```text
   [coverage] Step 2/3: Running CLI integration subprocess suite (tests/test_plugin_scripts.sh) — this step may take a while, process is still working, please wait...
   ```
   *(The script skips this step when you pass `--fast` or `--report-only`.)*
3. **Step 3/3 — Statement Analysis & Report Generation**:
   ```text
   [coverage] Step 3/3: Saving coverage data and analyzing executable statements — process is still working, please wait...
   [coverage] Building coverage report across 21 modules — process is still working, please wait...
   ```

---

## 3. Read the Coverage Report Tables

The report shows two tables:

1. **Module Coverage Table**: Shows line coverage for each Python script under `plugins/google-ads-api-developer-assistant/` and the root `set_financial_limits.py` script.
2. **Category Coverage Table**: Shows combined line coverage for each component group (`config`, `sidecars/google-ads-a2a-service`, each skill under `skills/<skill-name>`, and `root`).

### Column Definitions

| Column | Meaning | Formula / Source |
| :--- | :--- | :--- |
| **`Module` / `Category`** | Relative path of the Python module (or component category name) | Tracked `.py` files (excludes empty `__init__.py` files) |
| **`Stmts`** | Total number of **executable Python statements** (lines) in the file or category | Found with Python's `trace._find_executable_linenos()` (excludes comments, blank lines, and docstrings) |
| **`InProc`** | Number of executable lines that ran **in-process** inside `pytest` | Tracked with `sys.monitoring` (`PEP 669`) inside the `pytest` process |
| **`InProc%`** | Percentage of executable lines that ran in-process | $\frac{\text{InProc}}{\text{Stmts}} \times 100\%$ |
| **`Combined`** | Total executable lines that ran across **both** in-process `pytest` tests **and** child CLI subprocesses | Union of `InProc` lines and subprocess line hits (`cov_*.json`) |
| **`Miss`** | Number of executable lines that **did not run** in any test (in-process or subprocess) | $\text{Stmts} - \text{Combined}$ |
| **`Comb%`** | Final combined line coverage percentage | $\frac{\text{Combined}}{\text{Stmts}} \times 100\% = \left(1 - \frac{\text{Miss}}{\text{Stmts}}\right) \times 100\%$ |

### Why the Report Shows Both `InProc` and `Combined`

Many tests in [`tests/test_components.py`](./test_components.py), [`tests/test_hitl_mutation_guard.py`](./test_hitl_mutation_guard.py), [`tests/test_python_315.py`](./test_python_315.py), and [`tests/test_plugin_scripts.sh`](./test_plugin_scripts.sh) start the plugin scripts as child CLI processes (`subprocess.run([sys.executable, ...])`). This method tests command-line arguments, exit codes, and `sitecustomize.py` or `PreToolUse` hooks:

- **`InProc`** counts only the lines that run when `pytest` imports a module directly. For example, tests run the CLI wrapper `config/set_financial_limits.py` only as a child process. Because of this, its `InProc%` is `0.0%`, but its `Comb%` is `97.7%`.
- **`Combined`** merges in-process line hits with child process line hits from the injected `sitecustomize.py` hook (`sys.monitoring`). This column shows the true end-to-end coverage (`Comb%`).

---

## 4. What `Miss` and `-> MISSED` Mean

### What `Miss` Means

The **`Miss`** column shows the number of executable statement lines (`Stmts`) in a module or category that **did not run** during the test suite:

$$\text{Miss} = \text{Stmts} - \text{Combined}$$

Run the script with `--show-missed` to see the exact line numbers:

```bash
python3 tests/run_coverage.py --report-only --show-missed
```

The report prints a `-> MISSED (N): [...]` line below each module. This line lists the **1-indexed line numbers** that did not run:

```text
skills/ext-version/scripts/get_extension_version.py            27      23    85.2%        24      3    88.9%
    -> MISSED (3): [44, 45, 46]
```

In this example, `get_extension_version.py` has `27` executable lines. The tests ran `24` lines (`88.9%`) and did not run `3` lines (lines `44`, `45`, and `46`).

### Why Some Lines Do Not Run

The remaining ~15.5% of missed lines belong to six fallback or OS-specific categories:

1. **Python `< 3.11` `tomllib` Import Fallbacks**
   - On Python 3.11 and later, `import tomllib` succeeds in the `try:` block. The `except ImportError:` branches (for example, in `config/config_init.py`, `create_pmax_webpage_filter.py`, `get_recent_gclids.py`, and `troubleshoot_conversions.py`) run only on Python 3.10 or earlier.

2. **Filesystem and Permission Error Handlers (`except OSError:`)**
   - `try ... except OSError: pass` blocks wrap file writes, atomic renames, cache deletions, and `os.chmod(..., 0o600)` calls. These blocks prevent crashes on read-only disks, Windows filesystems, or concurrent writes.

3. **Build File Parsers and Archive Error Recovery (`sync_client_libs.py`)**
   - `sync_client_libs.py` contains fallback parsers for non-Python build files (`composer.json`, `build.gradle`, `.gemspec`, and `Common.props`) and error handlers for bad tarballs or network drops.

4. **Interactive Terminal Retry Loops (`sys.stdin.isatty()`)**
   - Interactive CLI menus (such as the menus in `set_financial_limits.py`) contain `KeyboardInterrupt` and `EOFError` handlers for manual terminal use.

5. **Static AST and Protobuf Descriptor Fallbacks (`run_mutation.py`)**
   - `run_mutation.py` includes fallback AST checks and Protobuf reflection guards for unusual script patterns.

6. **`if __name__ == "__main__":` Blocks in Imported Scripts**
   - When `pytest` calls `main()` directly in-process instead of starting a child OS process, the 1–3 lines inside `if __name__ == "__main__":` do not run.

---

## 5. How to Interpret Missed Lines

1. **`Miss > 0` Is Not a Test Failure**
   - A `Miss` value greater than zero does **not** mean that a test failed. It means only that those source lines did not run during the test suite.
   - The [`test_coverage_above_80_percent`](./run_coverage.py) test checks that every module and every category has at least **80.0% coverage** (currently **84.5% overall**).

2. **Why One Test Run Does Not Reach 100% Coverage**
   - A single test run uses one Python version and one operating system. Compatibility branches for other environments (such as `except ImportError:` or Windows-only permission branches) cannot run in the same process without mocks.
   - In the same way, `except OSError: pass` handlers run only when the operating system reports a disk or permission error.

3. **Core Logic vs. Fallback Guards**
   - **Covered (`84.5%`)**: Unit and integration tests run all main code paths. These paths include all 120 `financial_limits` service and field pairs, the 4-Step HITL mutation guard (`run_mutation.py`, `config_init.py`, and `sitecustomize.py`), the `create` and `update` mutation check and delete (`remove`) block, account/campaign/ad-group/ad creation scripts, A2A sidecar endpoints, GAQL validation, conversion troubleshooting, and client library sync.
   - **Missed (`15.5%`)**: Fallback guards, OS exception handlers, interactive terminal loops, and secondary build-file parsers.

4. **How to Use `Miss` When You Add Code**
   - **Add a test**: If you add a feature and `--show-missed` shows a block of 10 or more missed lines in your new function, write a unit test for that branch.
   - **No test needed**: Short 1–3 line ranges in `--show-missed` (such as `except OSError:` or `if __name__ == "__main__":`) are standard error guards and do not need extra mocks.

---

## 6. Where the Tool Stores Coverage Data

The coverage tool saves its files in `.pytest_cache/coverage/`:

- `.pytest_cache/coverage/cov_data/inproc_hits.json`: Line hits recorded in-process during `pytest`.
- `.pytest_cache/coverage/cov_data/cov_<pid>_<uuid>.json`: Line hits recorded by child Python processes through `sys.monitoring`.
- `.pytest_cache/coverage/cov_hook/sitecustomize.py`: Temporary `sys.monitoring` hook added to `PYTHONPATH` during coverage runs (and chained to `config/sitecustomize.py` when present).
