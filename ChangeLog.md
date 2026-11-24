# ChangeLog

## 4.1.0

- **Pre-Ship Security, Cross-CLI Parity, Efficiency & Resilience Hardening (`config/hook_guard.py`, `config/config_init.py`, `hooks.json`, `hooks/hooks.json`, `rules/AGENTS.md`, `sidecars/`, `skills/`, `plugin.*`, `install.*`, `update.*`):**
  - Added lightweight stdlib `config/hook_guard.py` as the `SessionStart`, `PreToolUse`, and `PostToolUseFailure` hook entrypoint for both Antigravity (`agy`) and Claude Code CLI, lazily loading `config/config_init.py` (with deferred stdlib imports) to keep benign shell, file, and MCP hooks under ~75 ms and Ads shell hooks under 150 ms.
  - Closed MCP `PreToolUse` interception gaps on both CLIs: updated `hooks/hooks.json` to match Claude Code bundled plugin MCP names (`mcp__(?:plugin_google-ads-api-developer-assistant_)?google-ads-api-assistant__*`), fixed `hook_guard.py` `_extract_mcp_call()` for `agy` eager plugin MCP names (`mcp_<plugin_id>_<server>_<tool>`), aligned `create_ad_group` as Tier 2 (matching `run_mutation.py` and `server.py`), and supported optional `script_path` on receipt-only `execute_mutation` (`run_script=False`).
  - Added `PreToolUse` credential-read guards (`read_file|view_file` in `agy`, `Read` in Claude Code) blocking direct reads of `google-ads.yaml`, `google_ads_php.ini`, `google_ads_config.rb`, `ads.properties`, and `.a2a_token`.
  - Expanded protected file-write guards (`_PROTECTED_ASK_FILES`) to include `sitecustomize.py`, `AGENTS.md`, `set_financial_limits.py`, `create_*.py`, `hook_guard.py`, `run_mutation.py`, `server.py`, `mcp_config.json`, `.mcp.json`, `sidecar.json`, and `plugin.json`, and resolved relative file/MCP paths against `workspace_cwd` before `os.path.realpath()` in both `hook_guard.py` and `config_init.py`.
  - Bound sidecar `create_account`, `create_campaign`, `create_ad_group`, and `create_ad` live executions to the dry-run receipt via canonical parameter SHA-256 (`create_params_sha256`), preventing parameter/budget/ATO bait-and-switch between dry-run and live execution; confined `prepare_mutation` and `execute_mutation` scripts to `saved/code/` and required real `validate_only=True` subprocess dry-runs before live `run_script=True`; added `reject_mutation` MCP tool and removed unused `generate_code` MCP exposure.
  - Closed shell/AST mutation guard bypasses in `config_init.py`: realpath-verified read-only and lifecycle script exemptions against trusted plugin/repo roots, blocked inline `GOOGLE_ADS_*` guard/audit/limit env overrides and programmatic Python self-elevation (`set_execute_mutates`, `write_financial_limits`, etc.), disabled `pytest`/`ruff` short-circuits on subshells or non-`tests/` targets, replaced flat AST analysis with sequential per-scope `validate_only=True` verification (rejecting `not C.execute`, `req` reassignment, cross-function scope leaks, and `getattr`/`exec`/`eval` dynamic dispatch), normalized shell quote/variable splitting, and added inspection for `http`/`xh`, `node`, `gawk -i inplace`, PHP, and Ruby mutation scripts.
  - Hardened `run_mutation.py` (`--_exec-target` single-use nonce token, `allow_abbrev=False`, atomic `EXECUTING` receipt claim/lock in `claim_receipt_for_execution()`, `O_NOFOLLOW` on audit log writes) and `sync_client_libs.py` (GitHub host allowlist, verified checkout checks, preserving `saved/` and `client_libs/` in `sync_directories()`, atomic `os.replace` writes preserving `allow_tier1_financial_mutates` and custom TOML keys).
  - Updated `sidecar.json` with narrow `sandbox.allowed_http_hosts` and `${PLUGIN_ROOT}/config/google-ads.yaml`, routed sandboxed `server.py` receipts/audit/GAQL cache to `ANTIGRAVITY_EXECUTABLE_DATA_DIR` / `PLUGIN_DATA`, capped `server.py` subprocess outputs at 16 KiB, added `--max-errors` (default 50) to `validate_conversion_upload.py`, added `--max-rows` to `get_cids_under_mcc.py`, wrote `0600` unique millisecond/UUID filenames in `troubleshoot_conversions.py`, and wired `customer_id` into `validate_gaql.py` cache calls.
  - Standardized always-on rules into concise `rules/AGENTS.md` (< 4 KB, deduplicated against `SessionStart` context), renamed generic skills to `google-ads-explain` and `google-ads-step-by-step` with negative trigger boundaries across all 11 skills, added `plugin.json` marketplace metadata (`category`, `logo`, `suggestedPrompts`), added `plugin.json`+`hooks.json`-gated CWD fallback in `hooks.json`, updated `_set_hooks_json_enabled()` to recognize `hook_guard.py` without injecting unsupported `"enabled"` keys into Claude `hooks/hooks.json`, updated `plugin.sh`/`plugin.ps1` `test` to probe `hook_guard.py` on `SessionStart` and `PreToolUse`, and stripped Claude-only files when installing/updating `agy` targets (`0` warnings in `jetski plugin validate`).
  - Removed internal Cloudtop path literals from `config_init.py`, reconciled broken/stale links and CLI-only documentation across `README.md`, `plugins/google-ads-api-developer-assistant/README.md`, `migration.md`, `skills/assistant-tutorial/SKILL.md`, and `commands/assistant-tutorial.md`, and added `tests/test_preship_audit_regressions.py`.
  - Eliminated all remaining hardcoded static Google Ads API version literals (such as `v23`/`v24`/`v25`/`v26`) across skill error messages, documentation (`README.md`, `FAQ.md`, `README_BEFORE_INSTALLATION.md`), and the entire test suite via a shared dynamic resolver (`tests/api_version_utils.py`), enforced by `test_no_static_api_versions_in_plugin_or_tests` in `tests/test_skill_version_resolution.py`.

- **HITL Guard Hook Fixes for Antigravity and Claude Code (`config/config_init.py`, `hooks.json`, `hooks/hooks.json`, `.mcp.json`, `.claude-plugin/plugin.json`, `server.py`, `install.*`, `update.*`):**
  - Fixed a bypass of the `run_mutation.py --reject` and `--dry-run` shortcuts. The guard now allows a shortcut only when a shell segment is exactly `python* .../skills/execute-mutation/scripts/run_mutation.py` with a real `--reject` or `--dry-run` argument. Commands with `#`, `$(`, backticks, `<(`, or newlines get the full check. Other chained segments (`&&`, `;`, `|`) still get the full check, and dry runs still get the deletion check.
  - Claude Code now uses the canonical exit-0 structured JSON contract (`hookSpecificOutput` with `permissionDecision` `allow`, `deny`, or `ask`), while the `hooks/hooks.json` shell wrapper exits with code 2 and stderr when Python or `hook_guard.py` is missing. When the guard has no objection, it sends no `permissionDecision`, so Claude Code permission rules still apply. Antigravity uses its native `decision` / `overwrite` JSON contract.
  - Added the Claude Code plugin files `hooks/hooks.json`, `.mcp.json`, and `.claude-plugin/plugin.json`, which use `${CLAUDE_PLUGIN_ROOT}`. The Claude Code hooks try `python3`, then `python`, then `py -3`, and exit with code 2 when Python or `config_init.py` is missing. The Antigravity `hooks.json` no longer looks for `config_init.py` relative to the current directory and blocks tool calls when it cannot find the script.
  - Shell and Python writes to `assistant_config`, `financial_limits`, `google-ads.yaml`, and `hooks.json` now need confirmation. Writes to `last_dry_run.json` and `mutation_audit.jsonl` are blocked.
  - `PostToolUseFailure` for `run_mutation.py --execute` now writes `EXECUTE_FAILED` with the error text and does not change the receipt. Only an explicit operator rejection writes `HUMAN_REJECTED`. This hook is registered for Claude Code only: Antigravity does not fire `PostToolUseFailure`, so it was removed from the Antigravity `hooks.json`.
  - Added `validate_api_version()` and `resolve_active_api_version()` to `config_init.py`. Values that are not `vNN` are rejected and never written to `config/assistant_config`. The config lookup now checks the explicit config directory, `CLAUDE_PLUGIN_ROOT`, and the current plugin before the Claude Code and Antigravity installs.
  - `allow_tier1_financial_mutates` now uses only the top-level TOML key. A bare `true` line no longer turns it on.
  - The `SessionStart` hook gives Claude Code the session context as `additionalContext` and writes `GOOGLE_ADS_ASSISTANT_DIR` and `GOOGLE_ADS_CONFIGURATION_FILE_PATH` to `CLAUDE_ENV_FILE`. Credential sync runs only for Ads-related commands, once per session.
  - The A2A sidecar now reclassifies receipts that have no policy tier (and blocks when it cannot), logs `RECEIPT_VERIFIED` for its verify-only path, records `approval_decision` separately from `status = SUCCESS`, and rejects only receipts for a `script_path` under `saved/code/`.
  - The install and update scripts show a warning when they find no API version, and ignore invalid `api_version` values.
  - The hook no longer rewrites command paths that already start with a variable, `~`, or `/` (for example `"$GADS_DIR/skills/..."` or `${CLAUDE_PLUGIN_ROOT}/skills/...`). Only bare relative `skills/...` and `config/...` paths are rewritten.
  - `run_mutation.py --execute` is blocked when the stored receipt records a customer ID mismatch between the payload and `--customer-id`.

- **Mutation Runner Fixes (`skills/execute-mutation/`):**
  - The Layer 4 gRPC interceptor now records failed RPCs as `FAILED` with the gRPC code and details, instead of `SUCCESS`. Layer 4 also covers `grpc.aio.secure_channel` and `grpc.aio.insecure_channel`.
  - Successful live mutations are logged as `status = SUCCESS` with `approval.decision = HUMAN_APPROVED`, so the CLI and the A2A sidecar use the same status values.
  - `--reject` now rejects only receipts in `DRY_RUN_PASSED` state that match the `--script` path or its SHA-256. It no longer overwrites `EXECUTED` receipts, and it exits with code 1 when nothing matched. `reject_dry_run_receipt()` returns `status` (`REJECTED` or `NO_PENDING_RECEIPT`) and `rejected_count`.
  - A customer ID mismatch between the payload and `--customer-id` now blocks the dry-run receipt (exit code 2, audit status `BLOCKED_CUSTOMER_ID_MISMATCH`) instead of only showing a warning.
  - Amount drift between the stated amount and the payload is now detected in both directions, per field.
  - `MultiPartyAuthReviewService.resolve_multi_party_auth_review` is classified as Tier 3 "Account Structure & Linking" and as an account-takeover escalation. Unclassified services show "unclassified service, review manually" instead of a `$0.00` spend delta.
  - `execute_mutates` and `allow_tier1_financial_mutates` use only the top-level TOML key when the file parses.
  - Email addresses are masked (`j***@domain.com`) in stored receipts and audit records, including `dry_run_rpc_calls` payloads. Masked payloads are flagged with `request_payload_masked` and verified against the `request_sha256` recorded before masking.
  - `create_account.py`, `create_ad.py`, `create_ad_group.py`, and `create_campaign.py` use `config_init.resolve_active_api_version()` and print a usage error (no traceback) for invalid versions.
  - `SKILL.md` documents the Tier 1 financial default, the `config_init.py --allow-tier1-financial-mutates true` opt-in (only with the user's explicit consent), that budget creation in `create_campaign.py` is Tier 1, and the decline step `run_mutation.py --reject --script ... --rejection-reason "..."`.

- **Skill Script Fixes (`skills/*/scripts/`, `skills/*/SKILL.md`, `commands/`, `rules/`):**
  - `inspect_object.py` no longer crashes with a traceback when the Google Ads SDK is not installed. It prints `ERROR: ... pass --api_version vN` instead.
  - `get_cids_under_mcc.py`, `create_pmax_webpage_filter.py`, `inspect_object.py`, `troubleshoot_conversions.py`, `get_recent_gclids.py`, and `validate_gaql.py` use the shared `config_init.resolve_active_api_version()` instead of separate copies.
  - `--api_version` is now optional in every skill script. When omitted, the active version is used (explicit argument, then `GOOGLE_ADS_API_VERSION`, then `api_version` in `config/assistant_config`, then the higher of local `client_libs` and the installed package).
  - `get_latest_api_version.py` has two new read-only modes. `--active` (alias `--no-update`) prints the version the scripts will use, and `--installed` prints the highest installed version. Running it without flags still detects the version and writes it.
  - `troubleshoot_conversions.py` masks GCLIDs (first and last 6 characters) in console output, reports, and JSON. Use `--show-gclids` to show full values.
  - `SKILL.md` and `commands/*.md` start each command block with a `GADS_DIR` line that resolves the plugin directory for both Antigravity and Claude Code (`CLAUDE_PLUGIN_ROOT`, `GOOGLE_ADS_ASSISTANT_DIR`, then the install directory).
  - Corrected the API version resolution order described in `assistant-tutorial/SKILL.md`.

- **Test Suite & CI Hardening (`tests/`, `.github/workflows/ci.yml`):**
  - `--validate-only` now skips every functional test that runs `run_mutation.py --execute`, so the scheduled CI job no longer makes live mutations.
  - The live CI job runs only on `workflow_dispatch` or `schedule` from `main` or `dev_next`, uses the `live-test-account` environment, and has `permissions: contents: read`. All GitHub Actions are pinned to commit SHAs.
  - The live CI job no longer uploads raw functional artifacts. It uploads only a pass/fail summary, kept for 3 days.
  - The audit logger now also redacts by value: refresh tokens (`1//`), access tokens (`ya29.`), client secrets (`GOCSPX-`), private keys, bearer tokens, and the test customer IDs.
  - Offline runs always use fake credentials and never read the developer's `google-ads.yaml`.
  - The Gemini API key is sent in the `x-goog-api-key` header instead of the URL.
  - Rejection tests for GAQL, conversion uploads, and financial limits check the specific error text and that no traceback appears.
  - Added regression suites `test_guard_hook_regressions.py`, `test_run_mutation_regressions.py`, and `test_skill_version_resolution.py`. Hook tests cover both Antigravity (`run_command`, `write_to_file`) and Claude Code (`Bash`, `Write`, `Edit`, `MultiEdit`) payloads.
  - Replaced hard-coded test counts with registry comparisons, made `--test-id` respect `--suite`, made `SK-SYNC-01` check that `client_libs` is unchanged, and added a mutated `SKILL.md` self-test to the offline eval suite.

- **Dynamic API Version Resolution Across Runtime, Installers & Test Harnesses (`config/`, `skills/*/scripts/`, `sidecars/`, `install.*`, `update.*`, `tests/`):**
  - Removed hardcoded `v26` defaults and fallbacks across `config/config_init.py` (`DEFAULT_API_VERSION`), `config/assistant_config`, `install.sh`, `install.ps1`, `update.sh`, `update.ps1`, `inspect_object.py`, `create_account.py`, `create_ad.py`, `create_ad_group.py`, `create_campaign.py`, `get_cids_under_mcc.py`, `create_pmax_webpage_filter.py`, `skills/execute-mutation/SKILL.md`, `skills/assistant-tutorial/SKILL.md`, and `sidecars/google-ads-a2a-service/server.py`, resolving the active Google Ads API version dynamically from caller/environment overrides, `config/assistant_config`, `client_libs/google-ads-python`, and installed `google.ads.googleads` packages.
  - Replaced version-number threshold branching in `troubleshoot_conversions.py` (`_uses_enablement_setting()`) with `ConversionTrackingSetting` Protobuf descriptor inspection, and updated `tests/mutate_test_harness.py`, `tests/hitl_audit_logger.py`, `tests/test_account_config.yaml`, `tests/hitl_policy_functional_suite.py`, `tests/test_hitl_functional_suite.py`, and `tests/test_hitl_mutation_guard.py` to discover and load the active SDK version dynamically.
  - Removed all remaining legacy sunset credential key references across `config/config_init.py`, `run_mutation.py`, and test suites, and added platform-independent `sync_client_libs.py` fallback and CLI exit-path coverage in `tests/test_components.py`.
- **Consistency, Efficiency & Resilience Improvements (`config/`, `skills/*/scripts/`, `sidecars/`, `install.*`, `update.*`):**
  - Escaped `%` as `%%` in `argparse` `help=` strings in `set_financial_limits.py` so `--help` succeeds on Python 3.14 and 3.15, added atomic `0600` writes with unchanged-content skips in `write_financial_limits()`, and registered all three `set_financial_limits.py` entrypoints in `tests/test_python_315.py`.
  - Fixed `_build_webpage_condition()` in `create_pmax_webpage_filter.py` to inspect `url_contains` and `operand` attributes on the `WebpageCondition` instance as well as its class across both `proto-plus` and raw Protobuf modes (`v23`–`v26`).
  - Added Google Ads API `v26` `ConversionTrackingSetting.enablement_setting` and `effective_enablement_setting` support (with automatic query fallback when `enhanced_conversions_for_leads_enabled` returns `UNRECOGNIZED_FIELD`) in `troubleshoot_conversions.py`.
  - Corrected GAQL hourly segment validation across `validate_gaql.py`, `sidecars/google-ads-a2a-service/server.py`, `rules/google_ads_rules.md`, `skills/validate-gaql/SKILL.md`, `skills/assistant-tutorial/SKILL.md`, `commands/validate-gaql.md`, and `README.md` so valid `segments.hour` is accepted and invalid `segments.hour_of_day` is rejected, and enforced `0600` permissions and symlink checks on `validate_gaql.py` disk caches.
  - Optimized `detect_latest_api_version()` in `config/config_init.py` and `get_latest_api_version.py` using `importlib.util.find_spec("google.ads.googleads")`, deferred `google.protobuf.json_format.MessageToDict` imports in `run_mutation.py`, short-circuited `PreToolUse` file-write checks before full configuration sync, and cached dynamic skill module loads by `(path, mtime_ns)` in `sidecars/google-ads-a2a-service/server.py`.
  - Added `v26` non-`mutate_*` write RPCs (`create_account_link`, `start_identity_verification`, `enable_p_max_brand_guidelines`, `resolve_multi_party_auth_review`, and `regenerate_shareable_link_id`), direct REST custom write verb blocking, unified financial service/method/payload sets, atomic `0600` JSON writes for `last_dry_run.json` and `hooks.json`, `GOOGLE_ADS_MUTATION_RECEIPT_PATH` per-session `pytest` receipt and audit-log isolation (`tests/conftest.py`), and `~/google-ads.yaml` path rejection across `config/config_init.py`, `config/sitecustomize.py`, `run_mutation.py`, and skill scripts.
  - Updated `config/sitecustomize.py` to stay idempotent on module reload and chain downstream `sitecustomize.py` modules on `sys.path`.
  - Aligned `sidecars/google-ads-a2a-service/server.py` with `validate_gaql.py` (`click_view` `DURING TODAY|YESTERDAY` and `change_status` `>=`/`<=` bounds), `inspect_object.py` (AST `MapField`, nested message separation, and `Enum` wrapper resolution), installed `google.ads.googleads` version discovery, and socket disconnect handling (`BrokenPipeError`, `ConnectionResetError`, and `TimeoutError`).
  - Added Python 3.15 `--ignore-requires-python` retry in `sync_client_libs.py` (`upgrade_system_package()`), `-c core.longpaths=true` git options in `sync_client_libs.py` and `install.sh`, custom TOML key preservation in `sync_client_libs.py` and `get_latest_api_version.py`, and inline `"python3 -c ..."` `hooks.json` command normalization on Windows in `install.ps1` and `update.ps1`.
- **Google Python Style Guide Compliance (`skills/*/scripts/*.py` & `set_financial_limits.py`):**
  - Updated all 16 skill scripts under `plugins/google-ads-api-developer-assistant/skills/*/scripts/` (`create_account.py`, `create_ad.py`, `create_ad_group.py`, `create_campaign.py`, `run_mutation.py`, `set_financial_limits.py`, `get_extension_version.py`, `get_latest_api_version.py`, `get_cids_under_mcc.py`, `inspect_object.py`, `create_pmax_webpage_filter.py`, `sync_client_libs.py`, `get_recent_gclids.py`, `troubleshoot_conversions.py`, `validate_conversion_upload.py`, and `validate_gaql.py`) and both `set_financial_limits.py` wrappers (`config/set_financial_limits.py` and `./set_financial_limits.py`) to follow the Google Python Style Guide while preserving 4-space indentation and `ruff` checks.
  - Standardized alphabetically sorted module-only imports (`collections.abc`, `pathlib`, `typing`, `urllib.error`, `urllib.parse`, and `urllib.request`), 80-column line limits, and Google-style module, class, and function docstrings.
  - Replaced broad `except Exception:` handlers with explicit module-level exception tuple constants, replaced implicit sequence truthiness checks with explicit emptiness checks (`if not items:`), and replaced multi-line ternary expressions with explicit `if`/`else` blocks.
- **User Documentation & `README.md` Table of Contents:**
  - Added a clickable `Table of Contents` index at the top of `README.md` with anchor links to all 52 sections and subsections.
  - Documented `Functional Tests Against a Test Account` and `Audit Logs` in `README.md`, covering file locations, `0600` permissions, JSONL record schemas, and `jq` / CLI filtering for `mutation_audit.jsonl`, `<UTC_TIMESTAMP>_hitl_policy_functional_audit.jsonl`, and `<UTC_TIMESTAMP>_<conversation_id>.jsonl`.
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
  - Added unit and regression tests in `tests/test_components.py`, `tests/test_python_315.py`, `tests/test_hitl_functional_suite.py`, and `tests/test_security_and_consistency_regressions.py` (including Windows `USERPROFILE` home isolation, escaped hook path checks, and `sync_client_libs.py` archive and tar-safety coverage) so every module and category exceeds 80% coverage (83.5% total across 14,328 statements, 331 passed tests).
- **Financial Transaction Upper Limits by `Service.field` (`config/financial_limits` & `set_financial_limits.py`):**
  - Added `config/financial_limits` and `set_financial_limits.py` (`skills/execute-mutation/scripts/set_financial_limits.py`, `config/set_financial_limits.py`, and `./set_financial_limits.py`) to set financial transaction upper limits with `<Service>.<field>` keys across all 20 Google Ads API services that have mutable financial fields (118 `Service.field` entries and 2 global fallbacks: `all_micros_transactions` and `all_currency_unit_transactions`).
  - Checked all `Service.field` entries against Google Ads API v26 Protobuf request descriptors and removed all immutable, output-only, and invalid fields.
  - Set the default for every entry in `config/financial_limits` to `0` (for `int64` fields) or `0.0` (for `double`/`float` fields) so financial fields cannot be changed by default. Set a value `> 0` in the API numeric unit (`micros`, `currency_units`, `decimal_ratio`, or `micros_proportion`) to allow changes up to that upper limit.
  - Enforced `Service.field` upper limits in `check_financial_transaction_limits`, `_wrap_service_for_audit`, `write_dry_run_receipt`, and `load_and_verify_receipt` (`run_mutation.py`), `evaluate_mutation_guard` (`config/config_init.py`), and `PREPARE_MUTATION` / `EXECUTE_MUTATION` (`sidecars/google-ads-a2a-service/server.py`). Writes `BLOCKED_FINANCIAL_LIMIT_EXCEEDED` to `saved/logs/mutation_audit.jsonl` when a command changes a `0`-valued field or exceeds an upper limit.
  - Added parametrized unit tests in `tests/test_hitl_mutation_guard.py` (`_ALL_FINANCIAL_LIMIT_TEST_CASES`, `test_all_financial_limits_have_explicit_test_cases_and_v26_mutability`, and `test_each_financial_limit_value_enforcement`) for every entry in `config/financial_limits`.
- **HITL Policy Functional Suite, Standalone Mutate Test Harness & Benchmark Updates:**
  - Added `tests/hitl_policy_functional_suite.py`, `tests/hitl_audit_logger.py`, `tests/test_account_config.yaml`, and `tests/test_hitl_functional_suite.py` (`--list-suites`, `--suite`, `--test-id`, `--validate-only`, and `--filter-errors`) with `127.0.0.1` loopback A2A sidecar binding and correlated `0600` JSONL audit logs (`SUITE_START`, `REQUEST`, `RESPONSE`, `ERROR`, `TEST_RESULT`, and `SUITE_SUMMARY` linked via `request_record_id`).
  - Added `tests/mutate_test_harness.py` (`--list`, `--category`, `--case`, `--json`, and `--verbose`) with 27 end-to-end test cases across 8 categories.
  - Updated `tests/benchmark_suite.py` to require two explicit version arguments (`--version-a` and `--version-b`) without fallback versions, and simplified OAuth credential parsing in `config/config_init.py` (`_extract_yaml_credentials`).
  - Scoped `_bench_config_sync_and_migration()` inside its temporary workspace across timed iterations and added an untimed warmup plus best-of-3 retry on transient CI I/O stalls in `_measure_benchmark()` (`tests/benchmark_suite.py`).
  - Reduced redundant `O_TRUNC` file overwrites and repeated `site-packages` scans in `config/config_init.py` (`sync_and_set_config_kv`, `copy_and_append_version`, and `detect_latest_api_version`).
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
