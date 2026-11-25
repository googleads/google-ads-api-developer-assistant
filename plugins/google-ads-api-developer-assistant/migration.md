# Google Ads API Developer Assistant Plugin for Claude & agy

## Overview

This plugin puts the skills, slash commands, lifecycle hooks, rules, diagnostic
scripts, and sidecars of the **Google Ads API Developer Assistant** (v4.1.0)
into one package. You can install this package in **Claude Code CLI** or
**Antigravity CLI (`agy`)**.

--------------------------------------------------------------------------------

## Plugin Directory Structure

```
google-ads-api-developer-assistant/
├── plugin.json                              <-- Manifest for rules, 11 skills, commands, hooks, sidecars, and MCP servers
├── hooks.json                               <-- Antigravity (agy) SessionStart & PreToolUse lifecycle hooks
├── hooks/hooks.json                         <-- Claude Code CLI SessionStart, PreToolUse & PostToolUseFailure hooks
├── README.md                                <-- Installation Guide & Usage Reference
├── config/
│   ├── assistant_config                     <-- Unified TOML config (api_version, customer_id, execute_mutates, allow_tier1_financial_mutates, enabled)
│   ├── hook_guard.py                        <-- Fast stdlib SessionStart/PreToolUse/PostToolUseFailure guard entrypoint
│   ├── config_init.py                       <-- Credential sync, TOML config manager, and deep PreToolUse guard
│   ├── financial_limits                     <-- Per-service financial upper limits (Service.field)
│   ├── set_financial_limits.py              <-- CLI wrapper to list, set, or reset financial limits
│   └── sitecustomize.py                     <-- Runtime config path resolution shim
├── commands/                                <-- Slash commands for Claude Code CLI only (agy uses skills/*/SKILL.md)
│   ├── assistant-tutorial.md
│   ├── execute-mutation.md
│   ├── explain.md
│   ├── ext-version.md
│   ├── get-cids.md
│   ├── get-cids-under-mcc.md
│   ├── inspect-object.md
│   ├── pmax-filter.md
│   ├── pmax-listing-filter.md
│   ├── step-by-step.md
│   ├── sync-client-libs.md
│   ├── troubleshoot-conversions.md
│   └── validate-gaql.md
├── rules/
│   └── AGENTS.md                            <-- Concise system directives, safety rules, and 4-Step HITL mutation protocol
├── skills/                                  <-- Skill packages and helper scripts
│   ├── assistant-tutorial/                  <-- Interactive user tutorial
│   │   └── SKILL.md
│   ├── execute-mutation/                    <-- 4-Step HITL mutation verification, consequence disclosure, and runner
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── create_account.py
│   │       ├── create_ad.py
│   │       ├── create_ad_group.py
│   │       ├── create_campaign.py
│   │       ├── run_mutation.py
│   │       └── set_financial_limits.py
│   ├── google-ads-explain/                  <-- 4-part explanations with analogies
│   │   └── SKILL.md
│   ├── ext-version/                         <-- Extension and latest API version lookup
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── get_extension_version.py
│   │       └── get_latest_api_version.py
│   ├── get-cids-under-mcc/                  <-- Account hierarchy lookup
│   │   ├── SKILL.md
│   │   └── scripts/get_cids_under_mcc.py
│   ├── inspect-object/                      <-- Protobuf and Enum inspection
│   │   ├── SKILL.md
│   │   └── scripts/inspect_object.py
│   ├── pmax-listing-filter/                 <-- Asset Group webpage exclusion filters
│   │   ├── SKILL.md
│   │   └── scripts/create_pmax_webpage_filter.py
│   ├── google-ads-step-by-step/             <-- Task step list workflow
│   │   └── SKILL.md
│   ├── sync-client-libs/                    <-- Client library lookup and GitHub release sync
│   │   ├── SKILL.md
│   │   └── scripts/sync_client_libs.py
│   ├── troubleshoot-conversions/            <-- Conversion upload diagnostics and CSV checks
│   │   ├── SKILL.md
│   │   ├── references/report_template.md
│   │   └── scripts/
│   │       ├── get_recent_gclids.py
│   │       ├── troubleshoot_conversions.py
│   │       └── validate_conversion_upload.py
│   └── validate-gaql/                       <-- 4-Step GAQL static analysis and live dry-runs
│       ├── SKILL.md
│       └── scripts/validate_gaql.py
├── sidecars/
│   └── google-ads-a2a-service/              <-- A2A Daemon Service
│       ├── sidecar.json
│       └── server.py
├── mcp_config.json                          <-- MCP Server configuration
└── set_financial_limits.py                  <-- Installed root CLI wrapper for financial limits
```

--------------------------------------------------------------------------------

## Summary of Migrated Features

1.  **System Rules (`rules/AGENTS.md`)**:
    -   **Validate Before Act**: Reads the cached `api_version` from
        `config/assistant_config` or checks the release notes.
    -   **4-Step HITL Mutation & Consequence Verification Protocol**: Allows
        only `create` and `update` operations, and blocks all delete (`remove`)
        operations. Uses `execute_mutates` and `allow_tier1_financial_mutates`
        in `config/assistant_config`, saves generated code in `saved/code/`,
        writes dry-run receipts to `saved/data/last_dry_run.json`, and writes
        audit records to `saved/logs/mutation_audit.jsonl`.
    -   **GAQL Validation Rules**: Blocks the `OR` operator, blocks `FROM` in
        metadata queries, and requires bare field names for metadata queries.
    -   **Code Generation Pipeline**: Runs `ruff` to check generated Python code
        and uses `GoogleAdsException` to format error messages.
    -   **Source of Truth**: Uses local `client_libs/` files as the primary
        reference for API definitions.
2.  **All 11 Skills (`skills/`) & Slash Commands (`commands/`)**:
    -   `execute-mutation` (`/execute-mutation`): Runs `validate_only=True`
        dry-runs, writes SHA-256 receipts, shows the consequence card, and runs
        live `create` and `update` mutations.
    -   `validate-gaql` (`/validate-gaql`): Runs 4-step static analysis and live
        API dry-runs on GAQL queries.
    -   `inspect-object` (`/inspect-object`): Checks Protobuf resources,
        messages, and Enums.
    -   `pmax-listing-filter` (`/pmax-filter`): Builds Performance Max webpage
        exclusion filter trees.
    -   `troubleshoot-conversions` (`/troubleshoot-conversions`): Checks offline
        conversion uploads, validates CSV files, samples GCLIDs, and creates
        diagnostic reports.
    -   `get-cids-under-mcc` (`/get-cids`): Lists child customer IDs under a
        Manager Account (MCC).
    -   `sync-client-libs` (`/sync-client-libs`): Checks local client library
        versions and updates them from GitHub releases.
    -   `ext-version` (`/ext-version`): Checks the plugin version and the active
        API version.
    -   `google-ads-explain` (`/explain`): Gives 4-part explanations (Big
        Picture, Analogy, Interconnectedness, Simple Language).
    -   `assistant-tutorial` (`/assistant-tutorial`): Starts an interactive
        tutorial.
    -   `google-ads-step-by-step` (`/step-by-step`): Breaks tasks into numbered
        steps.
3.  **Lifecycle Hooks (`hooks.json`, `hooks/hooks.json`, `config/hook_guard.py`,
    & `config/config_init.py`)**:
    -   `SessionStart` hook: Copies `~/google-ads.yaml` to
        `config/google-ads.yaml` (`0600` permissions), resolves the local active
        API version without network calls, and injects session context
        (`systemMessage` in `agy`, `additionalContext` + `CLAUDE_ENV_FILE` in
        Claude Code).
    -   `PreToolUse` hook: Resolves relative skill script paths to the plugin
        directory, points credential paths to `config/google-ads.yaml`, protects
        config/receipt/audit/guard files from silent tampering, and enforces the
        4-Step HITL Mutation Guard across shell commands, file writes, and MCP
        mutation tools (`allow`, `deny`, or `force_ask`/`ask`).
    -   `PostToolUseFailure` hook (Claude Code): Audits failed
        `run_mutation.py --execute` calls.
4.  **Daemon Services (`sidecars/`) & MCP Configuration (`mcp_config.json` /
    `.mcp.json`)**:
    -   Sandboxed Agent-to-Agent (A2A) HTTP service (`sidecar.json`) and stdio
        MCP server (`server.py --mcp`) supporting 11 A2A intents / 10 MCP tools
        (`GAQL_VALIDATE`, `INSPECT_OBJECT`, `TROUBLESHOOT_CONVERSIONS`,
        `PREPARE_MUTATION`, `EXECUTE_MUTATION`, `REJECT_MUTATION`,
        `CREATE_ACCOUNT`, `CREATE_CAMPAIGN`, `CREATE_AD_GROUP`, `CREATE_AD`,
        plus A2A-only `GENERATE_CODE`).

--------------------------------------------------------------------------------

## Runtime Behavior across Platforms

### 1. Host Hook Support (`hooks.json` vs `hooks/hooks.json`)

-   **Antigravity (`agy`)**: Loads root `hooks.json` (`SessionStart` and
    `PreToolUse` for `run_command`, `write_file|edit_file|...`,
    `read_file|view_file`, and `call_mcp_tool|mcp_.*`) via `PLUGIN_ROOT` (with
    `plugin.json`+`hooks.json`-verified CWD fallback).
-   **Claude Code CLI (`claude`)**: Loads `hooks/hooks.json` (`SessionStart`,
    `PreToolUse` for `Bash`, `Write|Edit|MultiEdit`, `Read`, and
    `mcp__(?:plugin_google-ads-api-developer-assistant_)?google-ads-api-assistant__*`
    mutation tools, plus `PostToolUseFailure` for `Bash`) via
    `${CLAUDE_PLUGIN_ROOT}`.
-   **Fallback Behavior**: If host hooks are off, the skill scripts still read
    credentials from `config/google-ads.yaml` through `_get_config_path()`. In
    addition, `run_mutation.py` and `server.py` enforce `execute_mutates`, Tier
    1 financial posture, financial limits, SHA-256 receipts, single-use
    execution tokens, deletion prohibition, and audit logs.

### 2. Interactive User Prompts (`ask_question` tool vs. CLI prompts)

-   **Antigravity CLI (`agy`)**: Shows interactive CLI prompts and `PreToolUse`
    `"decision": "force_ask"` confirmation cards.
-   **Claude Code CLI (`claude`)**: Uses text prompts in chat and `PreToolUse`
    `"permissionDecision": "ask"` CLI prompts.

--------------------------------------------------------------------------------

## Installation & Setup

### Step 1: Run the Installation Script

Go to the root directory of the repository and run `./install.sh` (Linux/macOS)
or `.\install.ps1` (Windows):

-   **Antigravity / agy**: Run `./install.sh agy` to copy the plugin to
    `~/.gemini/config/plugins/google-ads-api-developer-assistant`.
-   **Claude Code**: Run `./install.sh claude` to register the local marketplace
    and install `google-ads-api-developer-assistant`.

### Step 2: Configure Credentials

Put your `google-ads.yaml` file at `~/google-ads.yaml`. At session startup, the
plugin copies it to `config/google-ads.yaml`:

```yaml
client_id: "YOUR_OAUTH_CLIENT_ID"
client_secret: "YOUR_OAUTH_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
use_proto_plus: true
```

### Step 3: Restart Your Agent Host

Restart your agent host (or run `/reload-plugins` in Claude Code) to load the
plugin rules, 11 skills, slash commands, hooks, sidecars, and MCP tools.
