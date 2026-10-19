# ChangeLog

## 4.1.0

- **System Site-Directory Version Parity & Interactive Upgrade Protocol:**
  - Added system site-directory package inspection (`detect_system_package_version`, `check_system_package_parity`, `upgrade_system_package`) to `skills/sync-client-libs/scripts/sync_client_libs.py` to detect `google-ads` in Python system site-packages (`site.getsitepackages()` and `importlib.metadata.version('google-ads')`).
  - Added automatic version parity checking against latest upstream GitHub/PyPI releases in `process_client_libs` with structured metadata (`system_version`, `system_site_dirs`, `system_version_matches`) in CLI and JSON outputs (`--json`).
  - Added prominent CLI alert reporting in `print_table` when the system site-directory version does not match the upstream release.
  - Implemented `--upgrade_system` CLI flag in `sync_client_libs.py` to upgrade the system package via `pip` upon confirmation.
  - Updated agent behavioral rules in `rules/google_ads_rules.md` (Section 1.0 item 2, Section 1.2, and Section 4.1), skill instructions in `skills/sync-client-libs/SKILL.md`, and Claude Code slash command in `commands/sync-client-libs.md` mandating that whenever a new version of the python client library or `google-ads` is discovered, the assistant must check the system site-directory, alert the user to any mismatch, prompt the user for confirmation to upgrade, and update it upon confirmation.
  - Added unit test suite in `tests/test_components.py` covering system package detection, parity validation, pip upgrade execution, and alert rendering (expanding total passed tests to 129).
- **Runnable Code Storage Mandate (`saved/` Sub-Directory):**
  - Mandated that whenever asked to save code that can be run later, it MUST strictly be saved in the current working directory in a sub-directory called `saved` (e.g., `./saved/` or `./saved/code/`).
  - Updated `rules/google_ads_rules.md` (Hard Constraints Section 1.2, Project Structure Section 2.1, and Code Generation Protocol Section 3.2).
  - Integrated the mandate into the `PreInvocation` hook prompt injection in `config/config_init.py` (`handle_hook`).
- **Python Runtime Support & Baseline Modernization (Python >= 3.11):**
  - Removed support for Python 3.10 across the project and bumped the minimum required Python runtime to Python >= 3.11 (`requires-python = ">=3.11"` in `pyproject.toml`).
  - Updated package classifiers in `pyproject.toml` and set Ruff linting target version to `target-version = "py311"`.
  - Updated GitHub Actions CI test matrix (`.github/workflows/ci.yml`) to run across Python 3.11 through 3.15, dropping Python 3.10 on both Linux and Windows runners.
  - Updated host environment runtime checks in `install.sh` and `install.ps1` to require Python >= 3.11.
  - Updated documentation across `README.md`, `plugins/google-ads-api-developer-assistant/README.md`, and `FAQ.md` to document the minimum Python >= 3.11 requirement.
- **Global Plugin Availability, Direct Customer ID Pre-Seeding & Config Path Resolution:**
  - Added `--cid` / `--customer-id` flag to `install.sh` (`./install.sh agy --cid <id>`) and `-CustomerId` / `-Cid` to `install.ps1` (`.\install.ps1 -Type agy -Cid <id>`) to directly pre-seed default `customer_id` into `assistant_config` at install time.
  - Updated documentation across `README.md`, `FAQ.md`, and `skills/execute-mutation/SKILL.md` to document the plugin source path `plugins/google-ads-api-developer-assistant/config/config_init.py` and global plugin path `~/.gemini/config/plugins/...` for post-install CLI configuration.
  - Added `--link` / `--symlink` support to `install.sh` (`./install.sh agy --link`) and `-Link` support to `install.ps1` (`.\install.ps1 -Type agy -Link`) to symlink `~/.gemini/config/plugins/google-ads-api-developer-assistant` directly to `plugins/google-ads-api-developer-assistant` in the repository, and updated `update.sh` and `update.ps1` to detect and preserve symlinked plugin directories.
  - Updated `handle_hook()` in `config/config_init.py` to export `GOOGLE_ADS_ASSISTANT_DIR` and automatically rewrite relative `skills/<skill>/(scripts|references)/<file>` paths to the active plugin root when commands are invoked from workspaces outside the repository.
  - Updated skill definitions (`skills/*/SKILL.md`) and Claude Code slash commands (`commands/*.md`) to resolve script paths via `${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}` so skill scripts are globally executable from any working directory.
- **Unified TOML Assistant Configuration (`config/assistant_config`):**
  - Consolidated `config/api_version.txt`, `config/customer_id`, and `config/execute_mutates` into a single TOML configuration file `config/assistant_config` containing `api_version`, `customer_id`, and `execute_mutates` (defaulting to `execute_mutates = false`).
  - Added TOML configuration helpers in `config/config_init.py` (`parse_assistant_config`, `format_assistant_config`, `read_assistant_config`, `write_assistant_config`, `get_configured_customer_id`, `get_configured_api_version`, `is_execute_mutates_enabled`, and `sync_api_version`) with workspace-first precedence (`./config/assistant_config` overriding the plugin's `config/assistant_config`) and automatic fallback migration from legacy single-value files.
  - Updated `get_latest_api_version.py` (`update_assistant_config_api_version`) and `sync_client_libs.py` (`update_api_version_cache_if_needed`) to automatically update `api_version` in `config/assistant_config` across workspace and plugin config directories while preserving `customer_id` and `execute_mutates`.
  - Updated `install.sh`, `install.ps1`, `update.sh`, and `update.ps1` to seed, back up, and restore `config/assistant_config` across installations and updates.
- **4-Step HITL Mutation & Consequence Verification Protocol (`execute-mutation`):**
  - Replaced the blanket `NO MUTATE` / `READ-ONLY` hard prohibition in `rules/google_ads_rules.md` (Section 1.2 & Section 4.3) with the mandatory **4-Step HITL Mutation & Consequence Verification Protocol**: (1) GAQL Before-State & blast-radius lookup, (2) live `validate_only=True` dry-run with a SHA-256 signed verification receipt (`saved/data/last_dry_run.json`), (3) structured Consequence & Impact Disclosure to the user with explicit confirmation, and (4) `PreToolUse` hook-gated live execution (`--execute` with `ResponseContentType.MUTABLE_RESOURCE`).
  - Added user-configurable `execute_mutates` master switch (`execute_mutates = false` by default in `config/assistant_config`) enforced across `evaluate_mutation_guard()` (`PreToolUse` hook), `run_mutation.py` (`--execute`), and the A2A sidecar (`handle_execute_mutation`), while always permitting `--dry-run` (`validate_only=True`) validations.
  - Added the `execute-mutation` skill (`skills/execute-mutation/SKILL.md`) defining the Google Ads Consequence Matrix across Budgets & Bidding, Status Changes (`PAUSED` / `ENABLED`), Destructive `REMOVE` Operations, Targeting & Exclusions, and Conversion Actions & Goals, alongside a standard `--dry-run` / `--execute` Python mutation script template.
  - Implemented `skills/execute-mutation/scripts/run_mutation.py` (`write_dry_run_receipt`, `load_and_verify_receipt`, `format_verification_card`, `mark_receipt_executed`) to run `validate_only=True` dry-runs, generate SHA-256 tamper-evident receipts (`saved/data/last_dry_run.json`), bind serialized protobuf RPC request payloads (`request_sha256` / `request_sha256_list` via gRPC client interceptor), render the **Mutation & Consequence Verification Card**, and enforce one-time receipt replay protection on live execution.
  - Added append-only JSONL mutation audit logging (`saved/logs/mutation_audit.jsonl`, `append_mutation_audit_log`) recording `DRY_RUN_PASSED`, `DRY_RUN_FAILED`, `SUCCESS`, `FAILED`, `BLOCKED_MUTATES_DISABLED`, and `BLOCKED_SHA256_MISMATCH` lifecycle events.
- **Deterministic `PreToolUse` Mutation Guard (`config/config_init.py`):**
  - Added `evaluate_mutation_guard()` and `_verify_dry_run_receipt_for_hook()` to `handle_hook()` in `config/config_init.py`:
    - Automatically allows read-only queries (`search`, `search_stream`, diagnostic/validation skill scripts) and `validate_only=True` / `--dry-run` executions (`"decision": "allow"`).
    - Hard-blocks (`"decision": "deny"` / `"permissionDecision": "deny"`) any live `.mutate*()`, `.apply_recommendation()`, conversion upload, or batch job execution when `execute_mutates = false` in `config/assistant_config`, or when lacking a fresh ($\le 30\text{ min}$) `DRY_RUN_PASSED` receipt in `saved/data/last_dry_run.json`, missing consequence disclosures, or exhibiting a script or protobuf RPC payload SHA-256 mismatch.
    - Hardened direct script and inline code inspection (`evaluate_mutation_guard`) to prevent CLI `--dry-run` flag spoofing when the script itself lacks `validate_only=True` or sets `validate_only=False`, and extended command inspection to catch direct `./script.py` executable invocations (without a `python` prefix).
    - Forces an interactive CLI confirmation prompt (`"decision": "force_ask"` in `agy` and `"permissionDecision": "ask"` in `Claude Code CLI`) displaying the full Consequence Summary (`Customer ID`, `Operation`, `Before -> After` state delta, `Reversibility`, and `Consequences`) when a verified live mutation executes.
  - Updated `PreInvocation` ephemeral prompt injection in `config/config_init.py` to surface the active `execute_mutates` state from `config/assistant_config` and enforce the 4-step HITL mutation requirement on every turn.
- **A2A Sidecar, Documentation & Testing:**
  - Added `PREPARE_MUTATION` and `EXECUTE_MUTATION` intent handlers (`handle_prepare_mutation`, `handle_execute_mutation` with `destructive_hint: True`) in `sidecars/google-ads-a2a-service/server.py`, enforcing `is_execute_mutates_enabled()` gating and recording `DRY_RUN_PASSED`, `BLOCKED_MUTATES_DISABLED`, and `SUCCESS` entries in `saved/logs/mutation_audit.jsonl`.
  - Added the **How Mutates Work** and `config/assistant_config` documentation sections to `README.md` and `plugins/google-ads-api-developer-assistant/README.md`, and updated `README_BEFORE_INSTALLATION.md` and `FAQ.md`.
  - Added and expanded unit and integration test suites in `tests/test_hitl_mutation_guard.py`, `tests/test_components.py`, `tests/test_validate_gaql_cache.py`, and `tests/test_plugin_scripts.sh` covering `config/assistant_config` parsing/precedence, `execute_mutates` gating, direct script `--dry-run` spoofing prevention, `./script.py` executable interception, sidecar mutation audit logging, symlinked plugin installation (`--link`), global skill script execution outside the repository, read-only/dry-run allowance, unverified live mutation denial, verified receipt `"force_ask"` prompting, script & protobuf RPC payload SHA-256 tamper detection, and audit trail logging.
- **Configuration Management & Session Initialization (`config_init.py`):**
  - Implemented `config/config_init.py` with automated multi-format configuration parsing (`parse_ruby_config`, `parse_ini_config`, `parse_properties_config`, `write_yaml_config`) to support fallback credentials from PHP, Ruby, and Java setups.
  - Added automatic extension version discovery (`get_version`) and idempotent `copy_and_append_version()` to append or update `ads_assistant: {version}` without duplicating lines across restarts.
  - Added `sync_and_set_config_kv()` and `get_config_file_path()` to reconstruct `config/google-ads.yaml` from `~/google-ads.yaml` (or fallbacks) at session start, enforce POSIX `0600` permissions with cross-platform error handling, and bind `GOOGLE_ADS_CONFIGURATION_FILE_PATH`.
  - Added CLI `main()` entry point supporting `--key`, `--value`, `--config-dir`, and `--source-yaml` flags with automatic test customer ID discovery from `config/assistant_config`.
  - Added plugin lifecycle hook definitions (`hooks.json`) configuring `PreInvocation` and `PreToolUse` hooks (supporting `run_command`, `Bash`, and `bash` tools) to inject ephemeral configuration notices and rewrite commands before execution.
  - Added command interception in `handle_hook()` to automatically rewrite references from `~/google-ads.yaml`, `os.path.expanduser('~/google-ads.yaml')`, and user home directory paths to `config/google-ads.yaml`, rewrite `GoogleAdsClient.load_from_storage()` calls to pass `path="config/google-ads.yaml"`, resolve relative `skills/` script paths to the global plugin directory, and prepend `export GOOGLE_ADS_CONFIGURATION_FILE_PATH=...` and `export GOOGLE_ADS_ASSISTANT_DIR=...`.
  - Added automatic cleanup of dummy upstream `google-ads.yaml` files inside `client_libs/` in `sync_and_set_config_kv()`, `install.sh`, `update.sh`, `install.ps1`, and `update.ps1` to prevent multiple configuration file discovery and isolate `GOOGLE_ADS_CONFIGURATION_FILE_PATH` strictly to `config/google-ads.yaml`.
- **Client Configuration & Home Directory Isolation:**
  - Enforced strict isolation requirement that all Python client initializations, skill scripts, and generated code must load configuration from `config/google-ads.yaml` and NEVER default to or reference the user's home directory (`~/google-ads.yaml`).
  - Added `_get_config_path()` helper across all skill scripts (`validate_gaql.py`, `inspect_object.py`, `create_pmax_webpage_filter.py`, `troubleshoot_conversions.py`, `get_recent_gclids.py`, `get_cids_under_mcc.py`) to pass `path=cfg_path` to `GoogleAdsClient.load_from_storage`, prioritizing plugin configuration and preventing fallbacks to default arguments.
  - Updated `server.py` generated code template to output `GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version="{api_version}")`.
  - Added per-request configuration synchronization in `server.py` `do_POST` when A2A tasks arrive.
  - Added mandatory Protocol 1.0 step 3 and Rule 2.2 to `rules/google_ads_rules.md` requiring `config/google-ads.yaml` usage and forbidding inspection of `os.path.expanduser('~/google-ads.yaml')`.
- **Diagnostic Collector Hardening & Isolation:**
  - Added bounded buffer reads (64KB) and nested history stripping in `troubleshoot_conversions.py` (`merge_previous_findings`) to prevent exponential memory allocation and file growth across consecutive diagnostic runs, and added configurable `output_dir` support.
  - Added isolated test fixtures with `tmp_path` in `tests/test_components.py`.
- **Performance Optimizations:**
  - Replaced recursive `glob.glob("**/google-ads.yaml", recursive=True)` traversal across `client_libs/` in `config/config_init.py` (`sync_and_set_config_kv`) with direct $O(1)$ top-level `os.scandir()` checks, eliminating tens of thousands of filesystem `stat`/`readdir` syscalls on every `PreInvocation` and `PreToolUse` hook invocation.
  - Replaced out-of-process `subprocess.run` execution of `get_extension_version.py` in `config/config_init.py` (`get_version`) with direct in-process `plugin.json` parsing and module-level caching (`_CACHED_VERSION`), and added in-memory version caching (`_CACHED_PLUGIN_VERSION`) in `sidecars/google-ads-a2a-service/server.py` (`get_plugin_version`).
  - Pre-compiled all hot-path regular expressions at module level in `config/config_init.py` (`evaluate_mutation_guard`, `handle_hook`) and `skills/inspect-object/scripts/inspect_object.py`.
  - Added two-tier (in-memory `_AVAILABLE_TYPES_CACHE` and on-disk `tempfile.gettempdir()/gads_assistant_types_<version>.json`) caching keyed by directory modification time (`mtime`) in `skills/inspect-object/scripts/inspect_object.py` (`get_available_types`) to avoid re-scanning and regex-parsing ~450 Python protobuf definition files on repeated inspections.
  - Added two-tier (in-memory `_GAQL_MEMORY_CACHE` and on-disk `saved/data/gaql_validation_cache.json`) GAQL validation response caching keyed by `SHA-256(query + api_version)` in `skills/validate-gaql/scripts/validate_gaql.py` (`compute_gaql_cache_key`, `get_cached_validation`, `set_cached_validation`, `invalidate_gaql_cache`) with configurable TTL (`--cache-ttl`) and cache control flags (`--no-cache`, `--clear-cache`, `--cache-path`).
  - Parallelized upstream GitHub release checks (`fetch_github_latest_release`) across multiple client libraries in `skills/sync-client-libs/scripts/sync_client_libs.py` (`process_client_libs`) using `concurrent.futures.ThreadPoolExecutor`.
- **Cross-Version Performance & Functionality Benchmark Suite (`tests/benchmark_suite.py`):**
  - Added `tests/benchmark_suite.py` and `TestPerformanceRegressions` (`tests/test_components.py`) with saved baselines (`tests/benchmarks/baseline_v4.0.0.json` captured from git tag `v4.0.0`, and `tests/benchmarks/baseline_v4.1.0.json`) and live git worktree comparison (`--compare-git-ref v4.0.0`):
    - `version_resolution_in_process` (1,000 iters): `119.87 ms` in `v4.0.0` $\rightarrow$ `0.57 ms` in `v4.1.0` (**211.41x speedup**).
    - `gaql_static_analysis` (200 iters): `42.79 ms` in `v4.0.0` $\rightarrow$ `4.68 ms` in `v4.1.0` (**9.15x speedup** with SHA-256 validation caching).
    - `protobuf_type_discovery_and_inspection` (200 iters): `99.53 ms` in `v4.0.0` $\rightarrow$ `10.30 ms` in `v4.1.0` (**9.66x speedup** with memory + disk caching).
    - `client_libs_parallel_release_sync` (5 iters, 5 repos @ 25ms RTT): `632.77 ms` in `v4.0.0` $\rightarrow$ `145.02 ms` in `v4.1.0` (**4.36x speedup** via `ThreadPoolExecutor`).
    - `conversion_csv_validation` (50 iters, 100 rows/batch): `101.16 ms` in `v4.0.0` $\rightarrow$ `91.35 ms` in `v4.1.0` (**1.11x speedup**).
    - New `v4.1.0` subsystem benchmarks: `config_sync_and_legacy_migration` (`99.31 ms` / 50 iters), `hook_pre_tool_use_interception` (`49.63 ms` / 500 iters), and `hitl_mutation_receipt_and_sha256_normalization` (`82.47 ms` / 100 iters).

## 4.0.0

- **Plugin Architecture & Migration:**
  - Migrated from legacy project-based structure (`.agents/skills`, `api_examples/`, `update_project_context.py`, `AGENTS.md`) to a unified multi-platform plugin architecture under `plugins/google-ads-api-developer-assistant/`.
  - Configured repository with `.claude-plugin/marketplace.json` for native Claude Code marketplace discovery and installation (`claude plugin marketplace add` / `claude plugin install`).
  - Implemented dual-contract governance (`rules/google_ads_rules.md`) across both Antigravity and Claude Code agent environments.
  - Added mandatory `DEFAULT TO PYTHON FOR EXECUTION` hard constraint directive in `rules/google_ads_rules.md` requiring the assistant to always use Python for executing code and running tasks across the project unless explicitly requested otherwise by the user.
- **Lifecycle & Maintenance Scripts:**
  - Updated install scripts (`install.sh`, `install.ps1`) and update scripts (`update.sh`, `update.ps1`) to require a target platform argument (`agy` or `claude`).
  - Added host environment verification in install scripts for Python >= 3.10 and host CLI availability (Antigravity CLI or Claude Code CLI).
  - Ensured Python client library (`google-ads-python`) is cloned by default alongside optional library flags (`--php`, `--ruby`, `--java`, `--dotnet`, `--all`).
  - Enhanced update scripts with resilient `git pull` handling (warning on client library pull failures without aborting) and dynamic plugin asset discovery/syncing.
  - Implemented robust `config/customer_id` and `config/customer_id.txt` backup and restoration across git operations using isolated temporary directories with guaranteed trap cleanup.
  - Replaced standalone uninstall scripts with native platform uninstallation mechanisms (`/plugin uninstall` in Claude Code, plugin directory deletion in Antigravity).
- **Synchronization & Versioning:**
  - Implemented automated client library discovery and sync tool (`sync_client_libs.py`) and Claude Code slash command (`/sync-client-libs`).
  - Added support for verifying and syncing the assistant repository itself (`google-ads-api-developer-assistant`) against upstream GitHub releases.
  - Added Protocol 1.0 "Validate Before Act & Interactive Sync" directive to agent rules: checks for upstream releases at startup in check-only mode and prompts the user before upgrading.
  - Implemented 5-tier dynamic API version resolution hierarchy in `get_latest_api_version.py` and A2A sidecar (`server.py`).
- **Version Parity & Verification:**
  - Added `check_version_parity()` in `inspect_object.py` across plugin locations to compare the installed environment package (`google-ads`) against local `client_libs/google-ads-python` source metadata (`pyproject.toml` / `ChangeLog`) and output an explicit warning banner on version discrepancies.
  - Added mandatory `CLIENT LIBS & RUNTIME VERSION MISMATCH WARNING` hard constraint directive to `rules/google_ads_rules.md` requiring agents to explicitly warn users of potential schema or descriptor differences when installed packages differ from cloned client libraries.
  - Mandated checking installed `google-ads` version against the latest upstream release in `rules/google_ads_rules.md`.
  - Updated `inspect-object` skill documentation (`SKILL.md`) to document the version parity checking requirement and field discrepancy handling.
- **Skills & Slash Commands:**
  - Added 10 native Claude Code slash commands under `commands/`: `/validate-gaql`, `/inspect-object`, `/troubleshoot-conversions`, `/get-cids`, `/pmax-filter`, `/explain`, `/assistant-tutorial`, `/step-by-step`, `/sync-client-libs`, and `/ext-version`.
  - Added CLI parameter support (`--query` / `-q`) to `validate_gaql.py` with automatic stdin fallback and prioritized static analysis before API client initialization.
  - Added static GAQL lint checks in `validate_gaql.py` and A2A sidecar (`server.py`) flagging deprecated `segments.hour` in favor of `segments.hour_of_day` for Google Ads API v23+.
  - Added case-insensitive matching, normalized lookups, fuzzy suggestions (`difflib`), and source definition parsing fallback (`inspect_from_source`) to `inspect_object.py`.
  - Added structured `--json` output flags to `troubleshoot_conversions.py`, `get_cids_under_mcc.py`, and `sync_client_libs.py`.
- **Sidecar & Microservices:**
  - Configured `mcp_config.json` and background A2A HTTP sidecar (`server.py`) on port 8900 for Agent-to-Agent task delegation (`GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`).
- **Testing & Tooling:**
  - Added top-level `requirements.txt` and `pyproject.toml` specifying `google-ads`, `ruff`, and `pytest`.
  - Added GitHub Actions CI workflow (`.github/workflows/ci.yml`) with Linux (Ubuntu) and Windows test matrices across Python 3.10 through 3.14 running linting, unit tests, and lifecycle validation scripts.
  - Added dedicated unit test suite in `tests/test_components.py` with mocked `GoogleAdsClient` and network fixtures.
- **Documentation:**
  - Updated documentation across `README.md` (including "Stay in sync" section), `plugins/google-ads-api-developer-assistant/README.md`, `FAQ.md`, `README_BEFORE_INSTALLATION.md`, and `migration.md`.

## 3.0.0

- Fixed a breaking bug in `install.ps1` and `tests/test_install.ps1` where legacy `settings.json` references caused the Windows installation to crash.
- Changed the assistant's role description in `AGENTS.md` to "Expert Developer for the Google Ads API".
- Added a rule to `AGENTS.md` requiring report-type queries to print retrieved results to stdout in a structured table format.
- Migrate from `gemini-cli` to `antigravity`.
- Moved GAQL validation to a skill.
- Added skill to fetch all child accounts under an MCC.
- Added rule to `AGENTS.md` to always check Devsite first for current version.
- Added rule to `AGENTS.md` to prevent using SQL aggregate functions in GAQL queries.
- Converted `explain` command to a skill.
- Converted `step_by_step` command to a skill.
- Replaced `conversions_support_package` with `troubleshoot_conversions` skill.
- Relocated conversion troubleshooting and upload summary scripts and tests into `troubleshoot_conversions` skill directory.
- Added `troubleshoot_conversions` skill with `EVAL.txtpb` evaluation definitions and `TEST.md` test documentation.
- Added datetime stamps to all log messages.
- Log file is now written to `.agents/` directory and is not reset on each run.
- Made structure of directory and files Antigravity compliant.
- Added required `api_version` argument to `get_cids_under_mcc`, `validate_gaql`, and `troubleshoot_conversions` skills.
- Added static query checks to `validate_gaql` for date segments, `click_view`, and `change_status`.
- Added new `inspect_object` skill for dynamically looking up Protobuf messages and Enums.
- Added new `pmax_listing_filter` skill for creating Performance Max webpage URL exclusions.
- Added `validate_conversion_upload` helper script to `troubleshoot_conversions` skill to pre-validate upload file formatting.
- Streamlined `AGENTS.md` and de-duplicated `conversions/AGENTS.md` to use new programmatic skills.
- Resolved `Namespace AttributeError` bug in `api_examples/conversion_reports.py` by adding the `limit` argument.
- Renamed skill simply to `explain`.
- Drastically reduced the size of `conversions/AGENTS.md` by migrating most of the functionality to a skill.
- Created cache file for current API version with TTL of 19 hours.
- `.venv` is not deleted at the end of the session. Its Python version is checked on startup and if a newer version is available a new `.venv` is created.

## 2.3.0

- Added `context_dir` argument to update scripts to add additional directories (e.g., your codebase).
- When the assistant executes Python code it is in a virtual environment that has the Google Ads API Client Libraries installed.
- At init check the current version of the extension against the latest on GitHub. Display a message if an update is available.
- Silenced extraneous startup messages.
- Changed name of startup hook to `configure_environment.py`.
- Changed name of cleanup hook to `cleanup_environment.py`.
- Removed placeholders from `GEMINI.md`.
- Optimized code to retrieve disapproved ads.
- Silenced automated `pip install` screen output telemetry noise.
- Attached diagnostic dynamic path traces logs auditing isolation `SessionStart` traversals.
- Documented Rule 4.5 Workspace Isolation Compliance enforcing explicit binary pointers.
- Zero tolerance rule to prevent `OR` operator in GAQL.
- Zero tolerance rule to prevent `FROM` operator in metadata queries.
- Fix formatting in `README.md`.

## 2.2.0

- `api_examples`: `api_version` is a required argument with no default value.
- Modified `/explain` to make output more structured.
- Added license to all files.
- Fixed bug in `configure_environment.py` hook script and added modifying policy files.
- Surgical update rules.
- Rule to prohibit dummy credentials.
- Rule for Asset Group URL Filtering.

## 2.1.0

- Updated Workflow: API Versioning & Pre-Task Validation.
- Added anti-pattern to Configuration Protocol.
- Modified `explain` command to return structured explanations.

## 2.0.1

- Added unit tests for `configure_environment.py` hook script.
- Added unit tests for `cleanup_config.py` hook script.
- Verified project tests pass by isolating from `client_libs` collection errors.
- Fixed linting errors in new test files.

## 2.0.0

- Hierarchical context file for conversions troubleshooting.
- Added Conversion Troubleshooting & Diagnostics functionality (`api_examples/collect_conversions_troubleshooting_data.py`).
- Updated examples to use Google Ads API v23.
- Updated `README.md`.
- Changed directory structure to use a single sub-directory for all saved data.
- Added unit test coverage for new diagnostic tools and examples.
- Reformatted `GEMINI.md` for better clarity on conversion types and autonomous diagnostic prompts.
- `install-deps` option to `install.sh` and `install.ps1`.
- `skills/ext_version` to get the extension version.
- `gemini-extension.json` to register extensions with `https://geminicli.com/extensions/`.
- Documentation resource for public protos.
- Hooks for start and end of a session.
- Mandatory GAQL validation rules to `GEMINI.md`.
- Dynamic gRPC interceptor for Python calls within extension.
- Python is installed by default with `install.sh` and `install.ps1`.
- Updated update process to allow for adding additional client libraries.
- Changed name of setup files to `install` and provided an uninstall procedure.
- Added additional rules for GAQL edge cases to `GEMINI.md`.
- Added command `conversions_support_data`.

## 1.5.0

- Added rigorous GAQL validation rules to `GEMINI.md`.

## 1.4.2

- Updated tests for `setup.sh` and `update.sh`.

## 1.4.1

- Fixed minor bugs in tests for `api_examples`.
- Added test `api_examples/tests/test_get_conversion_upload_summary.py`.

## 1.4.0

- Modified `ChangeLog` so changes are listed in reverse chronological order.
- Added `step_by_step` custom command.

## 1.3.0

- Added `explain` command.
- Placed client libraries in a sub-directory of the project directory.
- Updated setup and update scripts.
- Added constraint to `GEMINI.md` to never modify files in `api_examples`.

## 1.2.0

- Updated `README.md` for clarity.
- Modified `setup.sh` to work with Linux and macOS.
- Modified `update.sh` to work with Linux and macOS.
- Added PowerShell scripts for Windows.
- Removed extension installation to manifest since it regularly hangs.
- Modified logic in setup and update scripts.
- Added tests for setup and update scripts.

## 1.1.0

- Added support for PHP, Ruby, Java, and C#.
- Find latest version of the API and prompt user whether to use this version.
- Modified `setup.sh` to clone copies of the client libraries.

## 1.0.0

- Release of version 1.0.
