# Google Ads API Developer Assistant Plugin for Claude & agy

## Overview
This plugin packages all capabilities, skills, slash commands, lifecycle hooks, rules, diagnostic scripts, sidecars, and protocol constraints of the **Google Ads API Developer Assistant** (v4.1.0) into a portable plugin for **Claude Desktop**, **Claude Code CLI**, or **Antigravity / agy** environments.

---

## Plugin Directory Structure

```
google-ads-api-developer-assistant/
├── plugin.json                              <-- Manifest registering rules, 11 skills, commands, hooks, sidecars & MCP servers
├── hooks.json                               <-- PreInvocation & PreToolUse lifecycle hooks (config sync & HITL mutation guard)
├── README.md                                <-- Installation Guide & Usage Reference
├── config/
│   ├── assistant_config                     <-- Unified TOML config (api_version, customer_id, execute_mutates)
│   └── config_init.py                       <-- Credential sync, TOML config manager & deterministic PreToolUse guard
├── commands/                                <-- Native slash commands for Claude Code & agy
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
│   └── google_ads_rules.md                  <-- System directives, hard constraints & 4-Step HITL mutation protocol
├── skills/                                  <-- Complete skill packages & executable helper scripts
│   ├── assistant-tutorial/                  <-- Interactive user tutorial
│   │   └── SKILL.md
│   ├── execute-mutation/                    <-- 4-Step HITL mutation verification, consequence disclosure & runner
│   │   ├── SKILL.md
│   │   └── scripts/run_mutation.py
│   ├── explain/                             <-- Conceptual 4-part explanations with analogies
│   │   └── SKILL.md
│   ├── ext-version/                         <-- Extension & latest API version retrieval
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── get_extension_version.py
│   │       └── get_latest_api_version.py
│   ├── get-cids-under-mcc/                  <-- Account hierarchy resolution
│   │   ├── SKILL.md
│   │   └── scripts/get_cids_under_mcc.py
│   ├── inspect-object/                      <-- Dynamic Protobuf & Enum inspection
│   │   ├── SKILL.md
│   │   └── scripts/inspect_object.py
│   ├── pmax-listing-filter/                 <-- Asset Group webpage exclusion filters
│   │   ├── SKILL.md
│   │   └── scripts/create_pmax_webpage_filter.py
│   ├── step-by-step/                        <-- Task breakdown workflow
│   │   └── SKILL.md
│   ├── sync-client-libs/                    <-- Client library discovery & GitHub release sync
│   │   ├── SKILL.md
│   │   └── scripts/sync_client_libs.py
│   ├── troubleshoot-conversions/            <-- Conversion upload diagnostics & validation
│   │   ├── SKILL.md
│   │   ├── references/report_template.md
│   │   └── scripts/
│   │       ├── get_recent_gclids.py
│   │       ├── troubleshoot_conversions.py
│   │       └── validate_conversion_upload.py
│   └── validate-gaql/                       <-- 4-Step GAQL static analysis & live dry-runs
│       ├── SKILL.md
│       └── scripts/validate_gaql.py
├── sidecars/
│   └── google-ads-a2a-service/              <-- A2A Daemon Service
│       ├── sidecar.json
│       └── server.py
└── mcp_config.json                          <-- MCP Server configuration
```

---

## Migrated Capabilities Summary

1. **System Directives & Rules (`rules/google_ads_rules.md`)**:
   - Validate Before Act (cached `api_version` lookup in `config/assistant_config` / release notes fallback).
   - 4-Step HITL Mutation & Consequence Verification Protocol (gated by `execute_mutates` in `config/assistant_config`; code generated in `saved/code/`, dry-run receipts in `saved/data/last_dry_run.json`, audit trail in `saved/logs/mutation_audit.jsonl`).
   - GAQL validation protocol (no `OR`, no `FROM` in metadata queries, bare field names).
   - Automated code generation pipeline with `ruff` linting and `GoogleAdsException` traceback suppression.
   - Source-of-truth priority for local `client_libs/` definitions.
2. **All 11 Skills (`skills/`) & Slash Commands (`commands/`)**:
   - `execute-mutation` (`/execute-mutation`): 4-Step HITL mutation dry-run receipt generator, consequence card, and live execution runner.
   - `validate-gaql` (`/validate-gaql`): GAQL dry-runs and 4-step static analysis.
   - `inspect-object` (`/inspect-object`): Dynamic Protobuf resource/message/Enum inspection script.
   - `pmax-listing-filter` (`/pmax-filter`): Performance Max webpage exclusion listing tree script.
   - `troubleshoot-conversions` (`/troubleshoot-conversions`): Offline conversion diagnostics, CSV validator, GCLID sampler, and report generator.
   - `get-cids-under-mcc` (`/get-cids`): Manager Account child CID tree retriever.
   - `sync-client-libs` (`/sync-client-libs`): Automated client library version discovery and GitHub synchronization.
   - `ext-version` (`/ext-version`): Plugin/assistant and active API version checker scripts.
   - `explain` (`/explain`): Structured 4-part explanations (Big Picture, Analogy, Interconnectedness, Simple Language).
   - `assistant-tutorial` (`/assistant-tutorial`): Interactive guided walkthrough.
   - `step-by-step` (`/step-by-step`): Structured workflow breakdown.
3. **Lifecycle Hooks (`hooks.json` & `config/config_init.py`)**:
   - `PreInvocation` hook: Synchronizes `~/google-ads.yaml` into `config/google-ads.yaml` (`0600` permissions) and injects ephemeral configuration & HITL mutation notices.
   - `PreToolUse` hook: Rewrites relative skill script paths to the global plugin directory, isolates credential paths to `config/google-ads.yaml`, and deterministically enforces the 4-Step HITL Mutation Guard (`allow` / `deny` / `force_ask`).
4. **Daemon Services (`sidecars/`) & MCP Configuration (`mcp_config.json`)**:
   - Agent-to-Agent (A2A) HTTP service for external tool integration (`GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`, `PREPARE_MUTATION`, `EXECUTE_MUTATION`).

---

## Runtime Considerations & Adaptations

### 1. Host Hook Support (`hooks.json` & `config/config_init.py`)
- **Behavior**: Both **Antigravity (`agy`)** and **Claude Code CLI (`claude`)** execute `PreInvocation` and `PreToolUse` hooks defined in `hooks.json`.
- **Fallback**: In environments where host hooks are disabled, skill scripts still enforce credential isolation via `_get_config_path()` and `run_mutation.py` independently verifies `execute_mutates`, SHA-256 receipts, and audit logging.

### 2. Interactive UI Form Controls (`ask_question` tool vs CLI prompts)
- **Antigravity (`agy`)**: Supports interactive UI modals and `PreToolUse` `"decision": "force_ask"` confirmation cards.
- **Claude Code (`claude`)**: Uses conversational text questions and `PreToolUse` `"permissionDecision": "ask"` CLI prompts.

---

## Installation & Setup

### Step 1: Run the Installer Script
From the repository root, run `./install.sh` (Linux/macOS) or `.\install.ps1` (Windows):
- **Antigravity / agy**: `./install.sh agy` (installs to `~/.gemini/config/plugins/google-ads-api-developer-assistant`, or use `./install.sh agy --link` to symlink directly to your git checkout).
- **Claude Code**: `./install.sh claude` (registers the local marketplace and installs `google-ads-api-developer-assistant`).

### Step 2: Configure Credentials
Ensure your `google-ads.yaml` config file exists at `~/google-ads.yaml` (automatically synced into `config/google-ads.yaml` at session startup):
```yaml
developer_token: "YOUR_DEVELOPER_TOKEN"
client_id: "YOUR_OAUTH_CLIENT_ID"
client_secret: "YOUR_OAUTH_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
use_proto_plus: true
```

### Step 3: Restart Agent Host
Upon restarting your agent host (or running `/reload-plugins` in Claude Code), the plugin rules, 11 skills, slash commands, hooks, sidecars, and MCP tools will be active.
