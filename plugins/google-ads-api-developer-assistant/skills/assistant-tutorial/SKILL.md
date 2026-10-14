---
name: assistant-tutorial
description: An interactive tutorial on how to use the Google Ads API Developer Assistant.
---

# Google Ads API Developer Assistant Tutorial (Interactive Guide)

> [!NOTE]
> * If you want a real-world analogy and conceptual explanation for any Google Ads API concept, use the `/explain <concept>` command.
> * If you want to walk through a process or workflow step-by-step, use the `/step-by-step <process>` command.

## Critical Directive for the Agent
When a user invokes `/assistant-tutorial` or requests this tutorial:
1. **NO MD SYNOPSIS FILES:** You MUST NOT write any markdown files or artifacts summarizing the tutorial.
2. **ALWAYS INTERACTIVE:** You MUST run this tutorial as an interactive, conversational experience.
3. **TOPIC SELECTION:** Start by asking the user which specific topic they want to learn about first using an interactive question or message. Do NOT recommend a specific topic or pre-select an option with "(Recommended)".
4. **PROGRESSIVE DISCLOSURE:** Present information in small, manageable pieces. Ask checking questions or prompt the user to proceed before moving on to the next step.
5. **NEVER RECOMMEND AN ANSWER:** When presenting checking questions, quizzes, or multiple-choice questions to the user during the tutorial, you MUST NOT recommend an answer, hint at or reveal the correct option in advance, or mark any option with "(Recommended)". Present all choices completely neutrally so the user can test their knowledge independently.
6. **EXPLAIN ANSWER OPTION:** Whenever you pose an interactive check question or quiz to the user, include a neutral choice/option that allows them to ask the Assistant to reveal and explain the answer.

---

## Tutorial Content Reference

### Topic 1: Core Principles, Configuration & Credential Isolation
- **Unified TOML Assistant Configuration (`config/assistant_config`):** Stores `api_version`, `customer_id`, and `execute_mutates` (defaulting to `execute_mutates = false`) in TOML format with workspace-first precedence (`./config/assistant_config` overriding the global plugin config) and automatic migration from legacy single-value files (`customer_id`, `api_version.txt`).
- **Home-Directory Credential Isolation & Multi-Language Config Fallbacks (`config_init.py`):** At session start, `sync_and_set_config_kv()` copies `~/google-ads.yaml`—or parses PHP (`google_ads_php.ini`), Ruby (`google_ads_config.rb`), Java (`ads.properties`), or .NET (`App.config` / `appsettings.json`) credential files—into an isolated `config/google-ads.yaml` (`0600` permissions) and sets `GOOGLE_ADS_CONFIGURATION_FILE_PATH`. Scripts must always call `GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version=api_version)` and never reference `~/google-ads.yaml` directly.
- **Default-to-Python Execution Mandate:** Even when multi-language client libraries (`--php`, `--ruby`, `--java`, `--dotnet`) are installed under `client_libs/`, Python is the default language for running tasks and generating code unless another language is explicitly requested.
- **4-Step HITL Mutation Guard (`execute_mutates`):** By default, live mutations are disabled (`execute_mutates = false` in `config/assistant_config`), and generated code is saved in `saved/code/`. When enabled (`execute_mutates = true`), every write operation must pass the mandatory 4-Step Human-in-the-Loop (HITL) Verification & Consequence Disclosure Protocol (GAQL before-state lookup, `validate_only=True` dry-run receipt in `saved/data/last_dry_run.json`, explicit consequence disclosure, and `PreToolUse` hook-gated execution logged to `saved/logs/mutation_audit.jsonl`).

### Topic 2: Campaign Creation & Cryptographic HITL Mutation Workflow (`/execute-mutation`)
- **4-Step HITL Mutation Workflow (`run_mutation.py`):**
  1. **GAQL Before-State & Blast-Radius Lookup:** Query current resource state and active child counts (`ad_group`, `ad_group_ad`), converting `micros` fields to standard currency (`/ 1,000,000`).
  2. **Cryptographically Bound `validate_only=True` Dry-Run:** Run `run_mutation.py --script saved/code/<script>.py --dry-run ...` to intercept serialized protobuf RPC payloads, strip `validate_only`, and write a tamper-evident receipt (`saved/data/last_dry_run.json`) binding both `script_sha256` and `request_sha256` (30-minute TTL, single-use replay protection).
  3. **5-Category Consequence Matrix & Verification Card:** Disclose specific impacts across *Budgets & Bidding*, *Status Changes (`PAUSED` / `ENABLED`)*, *Irreversible `REMOVE` Operations*, *Targeting & Exclusions*, and *Conversion Actions & Goals*, and wait for explicit user confirmation.
  4. **Hook-Gated Live Execution (`Mutate-to-Get`) & Audit Trail:** Execute with `--execute` (using `ResponseContentType.MUTABLE_RESOURCE` when supported) and record lifecycle events (`DRY_RUN_PASSED`, `DRY_RUN_FAILED`, `SUCCESS`, `FAILED`, `BLOCKED_MUTATES_DISABLED`, `BLOCKED_SHA256_MISMATCH`) to the append-only JSONL audit log at `saved/logs/mutation_audit.jsonl`.

### Topic 3: Shared Sets (Exclusion Lists)
- Explain `SharedSet` (reusable keyword/placement exclusion folders), `SharedCriterion` (items), and `CampaignSharedSet` (connector).
- Describe relationships and benefits.

### Topic 4: Code Quality & Standards
- Detail automated linting (`ruff check --fix`), explicit type annotations, and error handling (`GoogleAdsException` wrapper suppressing noisy gRPC tracebacks) that the assistant enforces.

### Topic 5: Finding Disapproved Ads (Cross-Account Audit & `/get-cids`)
- Phase 1: Determine Parent Manager Account (MCC) using `customer_manager_link`.
- Phase 2: Retrieve child accounts recursively using `get_cids_under_mcc.py` (supports `--json` output).
- Phase 3: Query disapproved ads via `ad_group_ad` resource.

### Topic 6: Creating an AI Max for Search Campaign
- **What is AI Max?** Refers to "AI Max for Search campaigns", NOT "Performance Max" campaigns.
- **Enabling AI Max:** Set `ai_max_setting.enable_ai_max = True` on the `Campaign` resource.
- **Campaign Configuration:** `advertising_channel_type = SEARCH`, budget, bidding strategy like Maximize Conversions.
- **Ad Creation:** RSA in `AdGroupAd` using `ResponsiveSearchAdInfo`.

### Topic 7: Creating a Demand Gen Campaign
- **What is Demand Gen?** Drives action across YouTube, Discover, and Gmail using image and video assets.
- **Campaign Configuration:** `advertising_channel_type = DEMAND_GEN`.
- **Ad Group Settings:** `demand_gen_ad_group_settings.channel_controls.selected_channels`.

### Topic 8: Writing Prompts to Produce Reports & GAQL Validation Caching (`/validate-gaql`)
- **Prompting Best Practices:** Define main resource, specify metrics, request date/device segments.
- **GAQL Validation Protocol (`validate_gaql.py`):** Programmatic 4-step sequence (Schema Discovery via `GoogleAdsFieldService` without `FROM` or `google_ads_field.` prefixes, Compatibility Check via `selectable_with`, Static Analysis blocking `OR` / SQL aggregates / deprecated `segments.hour` in favor of `segments.hour_of_day` in v23+, and Runtime Dry Run).
- **Two-Tier GAQL Validation Caching:** `validate_gaql.py` caches validated queries in memory and on disk (`saved/data/gaql_validation_cache.json`) keyed by `SHA-256(query + api_version)`, with `--cache-ttl`, `--no-cache`, and `--clear-cache` flags.

### Topic 9: Troubleshooting Conversion Problems (`/troubleshoot-conversions`)
- **Diagnostic Protocol (`troubleshoot_conversions.py`):** Investigates conversion upload issues with bounded history merging and `--json` output, generating structured diagnostic reports in `saved/data/`.
- **Recent GCLID Sampling (`get_recent_gclids.py`):** Queries `click_view` for a single-day window to sample valid recent GCLIDs for testing offline conversion uploads.
- **Pre-Upload CSV Validation (`validate_conversion_upload.py`):** Validates CSV formatting, required columns, and logical timestamp checks before uploading.

### Topic 10: Obtaining Descriptions of API Concepts and Objects (`/explain` & `/inspect-object`)
- **Conceptual Explanations (`/explain`):** High-level summaries structured into 4 parts: *Big Picture*, *Real-World Analogy*, *Interconnectedness*, and *Simple Language*.
- **Structural Inspection (`inspect_object.py`):** Inspects Protobuf resource fields, nested messages, and Enum values with case-insensitive/normalized matching, fuzzy suggestions (`difflib`), source-file fallback (`inspect_from_source`), and two-tier mtime-keyed type caching.
- **Runtime vs. `client_libs` Version Parity (`check_version_parity`):** Automatically compares the installed `google-ads` Python package version against `client_libs/google-ads-python` metadata and warns if a version mismatch could cause schema or descriptor discrepancies.

### Topic 11: Creating a Listing Filter for a Performance Max (PMax) Campaign (`/pmax-filter`)
- **Webpage Listing Filter:** Configure webpage exclusion listing trees (`vertical = WEBPAGE`) on PMax Asset Groups using `create_pmax_webpage_filter.py` (enforcing `SUBDIVISION` parent nodes with an explicit "Everything else" sibling node).

### Topic 12: Synchronizing Client Libraries & Assistant Releases (`/sync-client-libs`)
- **Protocol 1.0 Startup Check:** Runs `sync_client_libs.py --check_only --json` at session startup to check installed `google-ads` packages, the assistant repository, and cloned `client_libs/` (`google-ads-python`, `google-ads-php`, `google-ads-ruby`, `google-ads-java`, `google-ads-dotnet`) against upstream GitHub releases in parallel (`ThreadPoolExecutor`).
- **Interactive Upgrade & Version Sync:** Prompts the user before upgrading outdated libraries and automatically refreshes `api_version` in `config/assistant_config`.

### Topic 13: Extension & Dynamic API Version Resolution (`/ext-version`)
- **Version Scripts:** `get_extension_version.py` reports the assistant plugin version from `plugin.json`; `get_latest_api_version.py` resolves and caches the active Google Ads API version.
- **5-Tier API Version Hierarchy:** Resolves API version via: (1) explicit caller/env override (`GOOGLE_ADS_API_VERSION`), (2) `config/assistant_config` (`api_version`), (3) local `client_libs/google-ads-python/google/ads/googleads/v*` directory discovery, (4) installed `google.ads.googleads` package inspection, and (5) fallback default (`v25`).

### Topic 14: Step-by-Step Workflow Breakdown (`/step-by-step`)
- **3-Phase Actionable Plans:** Breaks down complex Google Ads implementations into:
  1. **Phase 1: Prerequisites & Configuration** (required IDs, permissions, and target resources).
  2. **Phase 2: Execution Steps** (sequential API operations with GAQL validation and 4-Step HITL mutation checkpoints).
  3. **Phase 3: Verification & Next Steps** (confirming state changes via GAQL or `Mutate-to-Get` responses).

### Topic 15: Lifecycle Hooks & Deterministic Guardrails (`hooks.json` & `config_init.py`)
- **`PreInvocation` Hook:** Runs at the start of every turn to sync `config/google-ads.yaml` and inject an ephemeral status notice showing the active config path and `execute_mutates` state.
- **`PreToolUse` Hook (`handle_hook` & `evaluate_mutation_guard`):** Intercepts shell/Python commands before execution to:
  - Rewrite `GoogleAdsClient.load_from_storage()` and `~/google-ads.yaml` references to `config/google-ads.yaml`.
  - Rewrite relative `skills/<skill>/scripts/...` paths to the global plugin root (`GOOGLE_ADS_ASSISTANT_DIR`) when working outside the repository.
  - Deterministically allow read-only/dry-run commands (`"decision": "allow"`), block unverified or disabled live mutations (`"decision": "deny"`), and trigger an interactive confirmation card (`"decision": "force_ask"` / `"permissionDecision": "ask"`) for verified live mutations.

### Topic 16: Agent-to-Agent (A2A) Sidecar Service & Cross-Workspace Execution
- **A2A HTTP Sidecar (`sidecars/google-ads-a2a-service/server.py`):** Background daemon listening on `ANTIGRAVITY_SIDECAR_WEB_PORT` (default port `8900`) supporting 6 structured task intents: `GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`, `PREPARE_MUTATION`, and `EXECUTE_MUTATION`.
- **Global & Symlinked Installation (`install.sh` / `update.sh`):** Installing for Antigravity (`./install.sh agy --link`) or Claude Code (`./install.sh claude`), optional language flags (`--php`, `--ruby`, `--java`, `--dotnet`, `--all`), and running assistant skills globally from any workspace.
