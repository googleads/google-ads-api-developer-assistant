# ChangeLog

## 4.1.0

- **User Documentation & `README.md` Table of Contents:**
  - Added a clickable `Table of Contents` index at the top of `README.md` with anchor links to all 42 sections and subsections.
  - Applied ASD-STE100 Simplified Technical English across user documentation (`README.md`, `plugins/google-ads-api-developer-assistant/README.md`, `README_BEFORE_INSTALLATION.md`, `FAQ.md`, `plugins/google-ads-api-developer-assistant/migration.md`, and `tests/README_coverage.md`).
- **Guardrail, Hook, Config & Sidecar Security Hardening (`config/`, `run_mutation.py`, `server.py`, `hooks.json`, `mcp_config.json`):**
  - Removed relative `config/config_init.py` path resolution from `hooks.json`, added `PreToolUse` file-write tool matchers (`write_to_file`, `replace_file_content`, `multi_replace_file_content`, `Write`, `Edit`, and `MultiEdit`) to protect `last_dry_run.json`, `mutation_audit.jsonl`, `assistant_config`, `financial_limits`, `google-ads.yaml`, and `hooks.json`, and updated `_is_hooks_json_disabled()` and `_set_hooks_json_enabled()` to support top-level `"config-init"`.
  - Updated `evaluate_mutation_guard()` and `_verify_dry_run_receipt_for_hook()` in `config/config_init.py` to allow `--dry-run` on all 5 built-in mutation scripts, check chained shell commands, `.sh` scripts, and `python -m` modules, block direct REST `:mutate` calls (`curl` and `wget`), reject future or invalid receipt timestamps and inline `python -c` receipt replay, gate `--record-only` and `--set-execute-mutates true` with `force_ask`, and fail closed on invalid `PreToolUse` JSON.
  - Updated `sync_and_set_config_kv()` and legacy config parsers (`.rb`, `.ini`, `.properties`, and `.config`) in `config/config_init.py` to strip comments, escape YAML values, write `0600` files, keep existing `login_customer_id` values, strip deprecated legacy keys, deduplicate first-prompt parity checks per session, and keep git-tracked `config/assistant_config` clean.
  - Updated `config/sitecustomize.py` to support `os.PathLike`, limit path redirection to read modes, and intercept `io.open`, `pathlib.Path.open`, and `os.path.isfile`.
  - Updated `run_mutation.py` to serialize `proto-plus` enums by name (`use_integers_for_enums=False`), block `Operation(remove=...)` keyword arguments and `OfflineUserDataJobService` / Link / YouTube RPCs, strip `response_content_type` during canonical request hashing, block 0-RPC `--dry-run` runs on `validate_only`-capable mutation scripts, enforce empty `expected_request_hashes` on live `--execute` runs, check `script_args`, and redact sensitive OAuth and service-account keys.
  - Updated `set_financial_limits.py` and `run_mutation.py` to reject `NaN`, `inf`, and negative amounts, keep exact 64-bit integer precision above $2^{53}$, and cache parsed limits by content SHA-256.
  - Added an MCP JSON-RPC 2.0 Stdio mode (`server.py --mcp` in `mcp_config.json`), `ANTIGRAVITY_SIDECAR_WEB_PORT` support, Bearer token authentication, `Host` / `Origin` / `Content-Type` / 1 MiB body checks, `_strict_bool()`, `ruff` and `ast.parse` code verification, live `inspect_object` and `troubleshoot_conversions` delegation, `run_script=True` subprocess execution in `EXECUTE_MUTATION`, and live `REMOVED` / financial-limit / audit checks in `sidecars/google-ads-a2a-service/server.py`.
- **Mutation, PMax, MCC, Diagnostic & Sync Script Fixes (`skills/*/scripts/`):**
  - Updated `create_campaign.py` to use atomic `GoogleAdsService.mutate` when creating a budget and campaign together, deterministic default names across `create_*.py`, `yyyy-MM-dd HH:mm:ss` campaign timestamps, channel-specific bidding and network settings, `REMOVED` status rejection, RSA count/length/`path1` validation in `create_ad.py`, and standalone live financial-limit checks.
  - Updated `create_pmax_webpage_filter.py` to create a flat root `UNIT_EXCLUDED` filter with `listing_source = WEBPAGE`, `v26` default, and `--dry-run`, `--execute`, and `--json` flags.
  - Updated `get_cids_under_mcc.py` to select `descriptive_name` and `status`, guard non-TTY `stdin`, and save CSV files when combined with `--json`.
  - Fixed date-segment comparison operators (`=`, `>=`, `<=`), string-literal masking, `GoogleAdsFieldService` metadata routing, customer-scoped atomic disk caches, and selective `invalidate_gaql_cache()` in `validate_gaql.py`.
  - Fixed `Enum` wrapper lookup, `FieldDescriptor` type mapping, dotted nested-type resolution (`Campaign.NetworkSettings`), AST-based `inspect_from_source()`, installed `google.ads.googleads` package fallback when `client_libs/` is absent, `--name` CLI aliasing, and UID-scoped `0600` temp caches in `inspect_object.py`.
  - Added UTF-8 BOM support, full timestamp and timezone checks, `conversion_time > click_time` validation, value and currency checks, and 64-hex SHA-256 PII checks in `validate_conversion_upload.py`; surfaced query and alert errors, excluded `pending_event_count` from `fail_rate`, and scoped `merge_previous_findings()` by `customer_id` in `troubleshoot_conversions.py`; added `YYYY-MM-DD` date validation in `get_recent_gclids.py`.
  - Fixed `check_assistant_repo()` git root lookup (`git rev-parse --show-toplevel`), Tar Slip archive checks (`_safe_extract_tar()` and `filter="data"`), HTTPS URL and git tag validation, PHP/Ruby/Java archive version detection, `LIBRARY_ALIASES` (`--library python`), UID-scoped `0600` temp caches, and pre-release ordering in `sync_client_libs.py`.
- **Installer, Lifecycle, Prompt Consistency & CI Updates (`install.*`, `update.*`, `plugin.*`, `.github/workflows/ci.yml`):**
  - Updated `install.sh`, `install.ps1`, `update.sh`, and `update.ps1` to back up and restore user `config/`, `saved/`, and `client_libs/` directories, merge non-zero user financial limits, refresh `claude plugin update`, normalize `"python3"` in installed Windows JSON manifests when `python3.exe` is absent, and align `.sh` and `.ps1` CLI flags.
  - Added 1-to-1 skill-matching command files (`commands/get-cids-under-mcc.md` and `commands/pmax-listing-filter.md`), aligned prompt flags and templates across `skills/*/SKILL.md` and `commands/*.md`, ignored legacy credential files in `.gitignore`, updated `tests/mutate_test_harness.py` to use `PAUSED` updates instead of `remove` operations, added `tests/test_security_and_consistency_regressions.py`, and enabled `macos-latest`, coverage, plugin script, and quick benchmark checks in `.github/workflows/ci.yml`.
  - Updated the `Install dependencies` step in `.github/workflows/ci.yml` to retry with `--ignore-requires-python` (and show a workflow warning) only when no `google-ads` release on PyPI supports the runner's Python version. All `google-ads` releases through `35.0.0` declare `Requires-Python <3.15`, so the Python 3.15 jobs could not install `google-ads`.
- **Strict `create` / `update` Mutation Policy & Delete (`remove`) Block (`execute-mutation` & `config/config_init.py`):**
  - Allows only **`create`** and **`update`** mutations across all execution, hook, sidecar, and verification layers. Blocks all delete (**`remove`**) operations.
  - Added `check_prohibited_deletion_mutation()` and `_extract_payload_deletion_violations()` in `skills/execute-mutation/scripts/run_mutation.py` to check Protobuf, dict, and string payloads (`remove`, `remove_all`, `status = REMOVED`, and `proposal_type = REMOVE`), removal RPC methods (`remove_*` and `delete_*`, added to `_MUTATION_METHOD_PREFIXES`), target Python script source code, `operation_summary`, and `after_state`.
  - Blocked delete operations before any RPC in `_wrap_service_for_audit()`, `write_dry_run_receipt()`, `load_and_verify_receipt()`, and `main()` (`--dry-run` and `--execute`) in `run_mutation.py`. Writes `BLOCKED_PROHIBITED_DELETION` to `saved/logs/mutation_audit.jsonl` and recommends `status = PAUSED` with an `update` operation.
  - Updated `MUTATION_CALL_PATTERN`, `_check_prohibited_deletion_for_hook()`, `_verify_dry_run_receipt_for_hook()`, and `evaluate_mutation_guard()` in `config/config_init.py` to block delete mutations at the `PreToolUse` hook across `run_mutation.py --dry-run`, `run_mutation.py --execute`, direct script execution, and `python3 -c` calls (even when `validate_only=True` is set).
  - Updated `handle_prepare_mutation()` and `handle_execute_mutation()` in `sidecars/google-ads-a2a-service/server.py` to return `"status": "HITL_BLOCKED"` and write `BLOCKED_PROHIBITED_DELETION`.
  - Updated `rules/google_ads_rules.md`, `skills/execute-mutation/SKILL.md`, `commands/execute-mutation.md`, `plugins/google-ads-api-developer-assistant/README.md`, and `README.md`. Added multi-layer tests (`test_only_allow_create_or_update_and_prohibit_deletion_across_all_layers`) in `tests/test_hitl_mutation_guard.py`.
- **Account, Campaign, Ad Group, and Ad Creation Scripts & A2A Intents (`execute-mutation`):**
  - Added `create_account.py` (`CustomerService.CreateCustomerClient`), `create_campaign.py` (atomic `GoogleAdsService.Mutate` for budget + campaign, or `CampaignService.MutateCampaigns`), `create_ad_group.py` (`AdGroupService.MutateAdGroups`), and `create_ad.py` (`AdGroupAdService.MutateAdGroupAds` for Responsive Search Ads) in `skills/execute-mutation/scripts/`. All scripts use the 4-Step HITL verification protocol, `validate_only=True` dry-run receipts, and `config/financial_limits` upper-limit checks.
  - Added `CREATE_ACCOUNT`, `CREATE_CAMPAIGN`, `CREATE_AD_GROUP`, and `CREATE_AD` intents to the A2A sidecar (`sidecars/google-ads-a2a-service/server.py`) with `_check_live_execution_gate` checks.
  - Updated `skills/execute-mutation/SKILL.md`, `commands/execute-mutation.md`, and `README.md` with CLI and A2A usage examples.
- **Line & Category Coverage Runner (`tests/run_coverage.py`, `tests/conftest.py`, `tests/README_coverage.md`) & >80% Coverage Across All Categories:**
  - Added `tests/run_coverage.py` and `tests/conftest.py` (`pytest --coverage`, `pytest --coverage-report`, `pytest --show-missed`, `pytest --fast`, and `pytest tests/run_coverage.py`) to collect in-process and subprocess line coverage with `sys.monitoring` on Python 3.12+ (and `sys.settrace` / `threading.settrace` fallback on Python 3.11) and print module and category coverage tables.
  - Added `tests/README_coverage.md` to explain coverage CLI flags, progress messages, table columns, and `Miss` / `-> MISSED` line numbers.
  - Added unit and regression tests in `tests/test_components.py`, `tests/test_python_315.py`, and `tests/test_security_and_consistency_regressions.py` so every module and category exceeds 80% coverage (82.7% total across 13,586 statements, 320 passed tests).
- **Financial Transaction Upper Limits by `Service.field` (`config/financial_limits` & `set_financial_limits.py`):**
  - Added `config/financial_limits` and `set_financial_limits.py` (`skills/execute-mutation/scripts/set_financial_limits.py`, `config/set_financial_limits.py`, and `./set_financial_limits.py`) to set financial transaction upper limits with `<Service>.<field>` keys across all 20 Google Ads API services that have mutable financial fields (118 `Service.field` entries and 2 global fallbacks: `all_micros_transactions` and `all_currency_unit_transactions`).
  - Checked all `Service.field` entries against Google Ads API v26 Protobuf request descriptors and removed all immutable, output-only, and invalid fields.
  - Set the default for every entry in `config/financial_limits` to `0` (for `int64` fields) or `0.0` (for `double`/`float` fields) so financial fields cannot be changed by default. Set a value `> 0` in the API numeric unit (`micros`, `currency_units`, `decimal_ratio`, or `micros_proportion`) to allow changes up to that upper limit.
  - Enforced `Service.field` upper limits in `check_financial_transaction_limits`, `_wrap_service_for_audit`, `write_dry_run_receipt`, and `load_and_verify_receipt` (`run_mutation.py`), `evaluate_mutation_guard` (`config/config_init.py`), and `PREPARE_MUTATION` / `EXECUTE_MUTATION` (`sidecars/google-ads-a2a-service/server.py`). Writes `BLOCKED_FINANCIAL_LIMIT_EXCEEDED` to `saved/logs/mutation_audit.jsonl` when a command changes a `0`-valued field or exceeds an upper limit.
  - Added parametrized unit tests in `tests/test_hitl_mutation_guard.py` (`_ALL_FINANCIAL_LIMIT_TEST_CASES`, `test_all_financial_limits_have_explicit_test_cases_and_v26_mutability`, and `test_each_financial_limit_value_enforcement`) for every entry in `config/financial_limits`.
- **Standalone Mutate & Write Test Harness (`tests/mutate_test_harness.py`) & Benchmark Updates:**
  - Added `tests/mutate_test_harness.py` (`--list`, `--category`, `--case`, `--json`, and `--verbose`) with 27 end-to-end test cases across 8 categories.
  - Updated `tests/benchmark_suite.py` to require two explicit version arguments (`--version-a` and `--version-b`) without fallback versions, and simplified OAuth credential parsing in `config/config_init.py` (`_extract_yaml_credentials`).
  - Updated `install.sh` and `install.ps1` to copy `update.sh`, `update.ps1`, `plugin.sh`, `plugin.ps1`, and `config/financial_limits` into the installed plugin directory.
- **Plugin Enable/Disable Option & Status Scripts (`plugin.sh` / `plugin.ps1`):**
  - Added `enabled = true|false` support in `config/assistant_config` (and the `GOOGLE_ADS_ASSISTANT_ENABLED` environment variable) with `parse_plugin_enabled_value()`, `is_plugin_enabled()`, `set_plugin_enabled()`, `get_plugin_status()`, and `format_plugin_status_text()` in `config/config_init.py`.
  - Updated `handle_hook()` in `config/config_init.py` to exit immediately when the plugin is off (`{}` for `PreInvocation` and `{"decision": "allow"}` for `PreToolUse`).
  - Added manifest and hook toggling (`_toggle_installed_plugin_manifests`, `_set_hooks_json_enabled`) for installed plugin directories (`~/.gemini/config/plugins/google-ads-api-developer-assistant` and `~/.claude/plugins/google-ads-assistant-local`).
  - Added `plugin.sh` (Linux/macOS) and `plugin.ps1` (Windows PowerShell) with `enable`, `disable`, `status`, `test`, and `is-enabled` commands, plus `--enable`, `--disable`, and `--status` flags in `config/config_init.py`, `install.sh`, `update.sh`, `install.ps1`, and `update.ps1`.
- **System Site-Directory & Client Library Version Parity Protocol:**
  - Added `fetch_latest_pypi_python_version` (queries `https://pypi.org/pypi/google-ads/json`) in `config/config_init.py` and `skills/sync-client-libs/scripts/sync_client_libs.py`.
  - Added `determine_api_version()`, `format_parity_table_markdown()`, and `format_parity_table_text()` in `config/config_init.py` to check `google-ads` in `site-packages` against `pypi.org`, check `google-ads-python` in `client_libs/` against GitHub, and select the active Google Ads API version.
  - Configured `PreInvocation` in `hooks.json` to run the version parity check on the first prompt of a session and show the 3-component table at the top of the first response.
  - Added `detect_system_package_version`, `check_system_package_parity`, `upgrade_system_package`, and `--upgrade_system` to `skills/sync-client-libs/scripts/sync_client_libs.py`.
  - Updated `rules/google_ads_rules.md`, `skills/sync-client-libs/SKILL.md`, `commands/sync-client-libs.md`, and `tests/test_components.py`.
- **Runnable Code Storage Rule (`saved/` Sub-Directory):**
  - Required all saved executable scripts to be written in the `saved` subdirectory of the current working directory (`./saved/` or `./saved/code/`).
  - Updated `rules/google_ads_rules.md` and `config/config_init.py` (`handle_hook`).
- **Python Runtime Requirement (Python >= 3.11):**
  - Dropped Python 3.10 support and set `requires-python = ">=3.11"` and `target-version = "py311"` in `pyproject.toml`.
  - Updated `.github/workflows/ci.yml` to test Python 3.11 through 3.15 on Linux, macOS, and Windows.
  - Updated `install.sh`, `install.ps1`, `README.md`, `plugins/google-ads-api-developer-assistant/README.md`, and `FAQ.md` to require Python >= 3.11.
- **Global Plugin Availability, Customer ID Flag & Path Resolution:**
  - Added `--cid` / `--customer-id` to `install.sh` and `-CustomerId` / `-Cid` to `install.ps1` to set `customer_id` in `assistant_config` during installation.
  - Enforced standalone plugin copies in `install.sh` and `install.ps1` (rejecting `--link` / `-Link`) and updated `update.sh` and `update.ps1` to migrate legacy symlinks to standalone copies.
  - Updated `handle_hook()` in `config/config_init.py`, `skills/*/SKILL.md`, and `commands/*.md` to resolve skill script paths through `GOOGLE_ADS_ASSISTANT_DIR` and `CLAUDE_PLUGIN_ROOT`.
- **Unified TOML Assistant Configuration (`config/assistant_config`):**
  - Combined `config/api_version.txt`, `config/customer_id`, and `config/execute_mutates` into `config/assistant_config` (with `api_version`, `customer_id`, and `execute_mutates = false`).
  - Added TOML read/write helpers in `config/config_init.py`, `get_latest_api_version.py`, `sync_client_libs.py`, `install.sh`, `install.ps1`, `update.sh`, and `update.ps1`.
- **4-Step HITL Mutation & Consequence Verification Protocol (`execute-mutation`):**
  - Replaced the `NO MUTATE` rule in `rules/google_ads_rules.md` with the 4-Step HITL Mutation Protocol: (1) GAQL before-state lookup, (2) `validate_only=True` dry-run with a SHA-256 receipt (`saved/data/last_dry_run.json`), (3) consequence disclosure and user confirmation, and (4) `PreToolUse` hook-gated live execution (`--execute` with `ResponseContentType.MUTABLE_RESOURCE`).
  - Added the `execute_mutates` switch (`execute_mutates = false` by default in `config/assistant_config`).
  - Added `skills/execute-mutation/SKILL.md` and `skills/execute-mutation/scripts/run_mutation.py` (`write_dry_run_receipt`, `load_and_verify_receipt`, `format_verification_card`, `mark_receipt_executed`, and `append_mutation_audit_log` for `saved/logs/mutation_audit.jsonl`).
- **`PreToolUse` Mutation Guard (`config/config_init.py`):**
  - Added `evaluate_mutation_guard()` and `_verify_dry_run_receipt_for_hook()` to `handle_hook()` in `config/config_init.py` to allow read-only and `--dry-run` calls, block unverified live mutations (`"decision": "deny"`), and prompt for confirmation (`"decision": "force_ask"` / `"permissionDecision": "ask"`) when a verified live mutation runs.
- **A2A Sidecar, Documentation & Tests:**
  - Added `PREPARE_MUTATION` and `EXECUTE_MUTATION` handlers in `sidecars/google-ads-a2a-service/server.py`.
  - Updated `README.md`, `plugins/google-ads-api-developer-assistant/README.md`, `README_BEFORE_INSTALLATION.md`, and `FAQ.md`.
  - Added test suites in `tests/test_hitl_mutation_guard.py`, `tests/test_components.py`, `tests/test_validate_gaql_cache.py`, and `tests/test_plugin_scripts.sh`.
- **Configuration Management & Session Startup (`config_init.py`):**
  - Added `config/config_init.py` (`parse_ruby_config`, `parse_ini_config`, `parse_properties_config`, `write_yaml_config`, `sync_and_set_config_kv`, and `copy_and_append_version`) and `hooks.json` to sync credentials from `$HOME` into `config/google-ads.yaml` (`0600` permissions) and set `GOOGLE_ADS_CONFIGURATION_FILE_PATH`.
  - Updated all skill scripts and `server.py` to load credentials from `config/google-ads.yaml` instead of `~/google-ads.yaml`.
- **Diagnostic Collector Updates:**
  - Added 64KB buffer limits and nested history cleanup in `troubleshoot_conversions.py` (`merge_previous_findings`).
- **Performance Optimizations & Benchmark Suite (`tests/benchmark_suite.py`):**
  - Replaced recursive `glob.glob` in `config/config_init.py` with top-level `os.scandir()` checks.
  - Added in-process version caching (`_CACHED_VERSION`), pre-compiled regular expressions, two-tier Protobuf type caching (`inspect_object.py`), two-tier SHA-256 GAQL validation caching (`validate_gaql.py`), and parallel `ThreadPoolExecutor` release checks (`sync_client_libs.py`).
  - Added `tests/benchmark_suite.py` and `TestPerformanceRegressions` (`tests/test_components.py`) with baseline files in `tests/benchmarks/`.

## 4.0.0

- **Plugin Architecture & Migration:**
  - Moved from the legacy project layout (`.agents/skills`, `api_examples/`, `update_project_context.py`, `AGENTS.md`) to a multi-platform plugin layout under `plugins/google-ads-api-developer-assistant/`.
  - Added `.claude-plugin/marketplace.json` for Claude Code marketplace installation.
  - Added `rules/google_ads_rules.md` for Antigravity and Claude Code, including the rule to use Python by default for code execution.
- **Lifecycle & Maintenance Scripts:**
  - Updated `install.sh`, `install.ps1`, `update.sh`, and `update.ps1` to take a platform argument (`agy` or `claude`), check Python and CLI prerequisites, clone `google-ads-python` by default, and support `--php`, `--ruby`, `--java`, `--dotnet`, and `--all`.
  - Added backup and restore for `config/customer_id` and `config/customer_id.txt` during updates.
- **Sync & Versioning:**
  - Added `sync_client_libs.py` and `/sync-client-libs` to check and update client libraries and the assistant repository against GitHub releases.
  - Added 5-tier API version lookup in `get_latest_api_version.py` and `server.py`.
  - Added `check_version_parity()` in `inspect_object.py` to compare the installed `google-ads` package with `client_libs/google-ads-python`.
- **Skills, Slash Commands & Sidecar:**
  - Added 10 Claude Code slash commands under `commands/`.
  - Added `--query` / `-q` and `segments.hour` lint checks to `validate_gaql.py`.
  - Added case-insensitive matching, fuzzy suggestions (`difflib`), and `inspect_from_source` to `inspect_object.py`.
  - Added `--json` output flags to `troubleshoot_conversions.py`, `get_cids_under_mcc.py`, and `sync_client_libs.py`.
  - Added `mcp_config.json` and the A2A HTTP sidecar (`server.py`) on port 8900.
- **Tests & Documentation:**
  - Added `requirements.txt`, `pyproject.toml`, `.github/workflows/ci.yml`, and `tests/test_components.py`.
  - Updated `README.md`, `plugins/google-ads-api-developer-assistant/README.md`, `FAQ.md`, `README_BEFORE_INSTALLATION.md`, and `migration.md`.

## 3.0.0

- Fixed a bug in `install.ps1` and `tests/test_install.ps1` where old `settings.json` references caused Windows installation to fail.
- Changed the assistant role in `AGENTS.md` to "Expert Developer for the Google Ads API".
- Added a rule in `AGENTS.md` to print report query results as tables to `stdout`.
- Migrated from `gemini-cli` to `antigravity`.
- Moved GAQL validation to a skill and added a skill to list child accounts under an MCC.
- Added rules in `AGENTS.md` to check Devsite for the current API version and block SQL aggregate functions in GAQL queries.
- Converted `explain` and `step_by_step` commands into skills.
- Replaced `conversions_support_package` with the `troubleshoot_conversions` skill and added `validate_conversion_upload`.
- Added timestamps to log messages and kept `.agents/` log files and `.venv` across runs.
- Added the required `api_version` argument to `get_cids_under_mcc`, `validate_gaql`, and `troubleshoot_conversions`.
- Added static checks to `validate_gaql` for date segments, `click_view`, and `change_status`.
- Added the `inspect_object` and `pmax_listing_filter` skills.
- Fixed the `Namespace AttributeError` bug in `api_examples/conversion_reports.py`.
- Added a 19-hour cache file for the current API version.

## 2.3.0

- Added the `context_dir` argument to the update scripts.
- Configured Python code execution to run in a virtual environment with the Google Ads client libraries installed.
- Added a startup version check against GitHub releases.
- Renamed the startup and cleanup hooks to `configure_environment.py` and `cleanup_environment.py`.
- Removed placeholders from `GEMINI.md` and reduced startup log noise.
- Added rules to block the `OR` operator in GAQL and block the `FROM` clause in metadata queries.
- Fixed formatting in `README.md`.

## 2.2.0

- Required the `api_version` argument in `api_examples` with no default value.
- Updated `/explain` output formatting and added license headers to all files.
- Fixed `configure_environment.py` and added rules to block dummy credentials and configure Asset Group URL filtering.

## 2.1.0

- Updated the API versioning and pre-task validation workflow.
- Updated the `explain` command to return structured explanations.

## 2.0.1

- Added unit tests for `configure_environment.py` and `cleanup_config.py`.
- Isolated project tests from `client_libs` collection errors and fixed lint errors.

## 2.0.0

- Added conversion troubleshooting and diagnostics (`api_examples/collect_conversions_troubleshooting_data.py`).
- Updated examples to Google Ads API v23 and moved saved files into a single subdirectory.
- Added `install-deps` to `install.sh` and `install.ps1`, added `skills/ext_version`, and added `gemini-extension.json`.
- Added session start/end hooks, GAQL validation rules in `GEMINI.md`, and a gRPC interceptor for Python calls.
- Installed Python by default in `install.sh` and `install.ps1` and renamed setup scripts to `install`.

## 1.5.0

- Added GAQL validation rules to `GEMINI.md`.

## 1.4.2

- Updated tests for `setup.sh` and `update.sh`.

## 1.4.1

- Fixed bugs in `api_examples` tests and added `api_examples/tests/test_get_conversion_upload_summary.py`.

## 1.4.0

- Listed `ChangeLog` entries in reverse chronological order and added the `step_by_step` command.

## 1.3.0

- Added the `explain` command, placed client libraries in a project subdirectory, and blocked edits to `api_examples`.

## 1.2.0

- Updated `README.md`, `setup.sh`, and `update.sh` for Linux and macOS, and added PowerShell scripts for Windows.

## 1.1.0

- Added support for PHP, Ruby, Java, and C#, added latest API version lookup, and cloned client libraries in `setup.sh`.

## 1.0.0

- Released version 1.0.
