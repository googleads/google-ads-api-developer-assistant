# Google Ads API Developer Assistant Plugin for Claude & agy

## Overview
This plugin puts the skills, slash commands, lifecycle hooks, rules, diagnostic scripts, and sidecars of the **Google Ads API Developer Assistant** (v4.1.0) into one package. You can install this package in **Claude Desktop**, **Claude Code CLI**, or **Antigravity / agy**.

---

## Plugin Directory Structure

```
google-ads-api-developer-assistant/
├── plugin.json                              <-- Manifest for rules, 11 skills, commands, hooks, sidecars, and MCP servers
├── hooks.json                               <-- PreInvocation & PreToolUse lifecycle hooks (config sync & HITL mutation guard)
├── README.md                                <-- Installation Guide & Usage Reference
├── config/
│   ├── assistant_config                     <-- Unified TOML config (api_version, customer_id, execute_mutates)
│   ├── config_init.py                       <-- Credential sync, TOML config manager, and PreToolUse guard
│   ├── financial_limits                     <-- Per-service financial upper limits (Service.field)
│   ├── set_financial_limits.py              <-- CLI wrapper to list, set, or reset financial limits
│   └── sitecustomize.py                     <-- Runtime config path resolution shim
├── commands/                                <-- Slash commands for Claude Code & agy
│   ├── assistant-tutorial.md
│   ├── execute-mutation.md
│   ├── explain.md
│   ├── ext-version.md
│   ├── get-cids.md
│   ├── inspect-object.md
│   ├── pmax-filter.md
│   ├── step-by-step.md
│   ├── sync-client-libs.md
│   ├── troubleshoot-conversions.md
│   └── validate-gaql.md
├── rules/
│   └── google_ads_rules.md                  <-- System directives, safety rules, and 4-Step HITL mutation protocol
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
│   ├── explain/                             <-- 4-part explanations with analogies
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
│   ├── step-by-step/                        <-- Task step list workflow
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

---

## Summary of Migrated Features

1. **System Rules (`rules/google_ads_rules.md`)**:
   - **Validate Before Act**: Reads the cached `api_version` from `config/assistant_config` or checks the release notes.
   - **4-Step HITL Mutation & Consequence Verification Protocol**: Allows only `create` and `update` operations, and blocks all delete (`remove`) operations. Uses `execute_mutates` in `config/assistant_config`, saves generated code in `saved/code/`, writes dry-run receipts to `saved/data/last_dry_run.json`, and writes audit records to `saved/logs/mutation_audit.jsonl`.
   - **GAQL Validation Rules**: Blocks the `OR` operator, blocks `FROM` in metadata queries, and requires bare field names for metadata queries.
   - **Code Generation Pipeline**: Runs `ruff` to check generated Python code and uses `GoogleAdsException` to format error messages.
   - **Source of Truth**: Uses local `client_libs/` files as the primary reference for API definitions.
2. **All 11 Skills (`skills/`) & Slash Commands (`commands/`)**:
   - `execute-mutation` (`/execute-mutation`): Runs `validate_only=True` dry-runs, writes SHA-256 receipts, shows the consequence card, and runs live `create` and `update` mutations.
   - `validate-gaql` (`/validate-gaql`): Runs 4-step static analysis and live API dry-runs on GAQL queries.
   - `inspect-object` (`/inspect-object`): Checks Protobuf resources, messages, and Enums.
   - `pmax-listing-filter` (`/pmax-filter`): Builds Performance Max webpage exclusion filter trees.
   - `troubleshoot-conversions` (`/troubleshoot-conversions`): Checks offline conversion uploads, validates CSV files, samples GCLIDs, and creates diagnostic reports.
   - `get-cids-under-mcc` (`/get-cids`): Lists child customer IDs under a Manager Account (MCC).
   - `sync-client-libs` (`/sync-client-libs`): Checks local client library versions and updates them from GitHub releases.
   - `ext-version` (`/ext-version`): Checks the plugin version and the active API version.
   - `explain` (`/explain`): Gives 4-part explanations (Big Picture, Analogy, Interconnectedness, Simple Language).
   - `assistant-tutorial` (`/assistant-tutorial`): Starts an interactive tutorial.
   - `step-by-step` (`/step-by-step`): Breaks tasks into numbered steps.
3. **Lifecycle Hooks (`hooks.json` & `config/config_init.py`)**:
   - `PreInvocation` hook: Copies `~/google-ads.yaml` to `config/google-ads.yaml` (with `0600` permissions) and adds configuration and mutation notices to the session context.
   - `PreToolUse` hook: Resolves relative skill script paths to the global plugin directory, points credential paths to `config/google-ads.yaml`, and enforces the 4-Step HITL Mutation Guard (`allow`, `deny`, or `force_ask`).
4. **Daemon Services (`sidecars/`) & MCP Configuration (`mcp_config.json`)**:
   - Agent-to-Agent (A2A) HTTP service for external tools (`GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`, `PREPARE_MUTATION`, and `EXECUTE_MUTATION`).

---

## Runtime Behavior across Platforms

### 1. Host Hook Support (`hooks.json` & `config/config_init.py`)
- **Standard Behavior**: **Antigravity (`agy`)** and **Claude Code CLI (`claude`)** run the `PreInvocation` and `PreToolUse` hooks from `hooks.json`.
- **Fallback Behavior**: If host hooks are off, the skill scripts still read credentials from `config/google-ads.yaml` through `_get_config_path()`. In addition, `run_mutation.py` checks `execute_mutates`, verifies SHA-256 receipts, blocks delete operations, and writes audit logs.

### 2. Interactive User Prompts (`ask_question` tool vs. CLI prompts)
- **Antigravity (`agy`)**: Shows interactive UI modal dialogs and `PreToolUse` `"decision": "force_ask"` confirmation cards.
- **Claude Code (`claude`)**: Uses text prompts in chat and `PreToolUse` `"permissionDecision": "ask"` CLI prompts.

---

## Installation & Setup

### Step 1: Run the Installation Script
Go to the root directory of the repository and run `./install.sh` (Linux/macOS) or `.\install.ps1` (Windows):
- **Antigravity / agy**: Run `./install.sh agy` to copy the plugin to `~/.gemini/config/plugins/google-ads-api-developer-assistant`.
- **Claude Code**: Run `./install.sh claude` to register the local marketplace and install `google-ads-api-developer-assistant`.

### Step 2: Configure Credentials
Put your `google-ads.yaml` file at `~/google-ads.yaml`. At session startup, the plugin copies it to `config/google-ads.yaml`:
```yaml
client_id: "YOUR_OAUTH_CLIENT_ID"
client_secret: "YOUR_OAUTH_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
use_proto_plus: true
```

### Step 3: Restart Your Agent Host
Restart your agent host (or run `/reload-plugins` in Claude Code) to load the plugin rules, 11 skills, slash commands, hooks, sidecars, and MCP tools.
