# Google Ads API Developer Assistant Plugin for Claude & agy

## Overview
This plugin packages all capabilities, skills, rules, diagnostic scripts, sidecars, and protocol constraints of the **Google Ads API Developer Assistant** into a portable plugin for **Claude Desktop**, **Claude Code CLI**, or **Antigravity / agy** environments.

---

## Plugin Directory Structure

```
google_ads_assistant_plugin/
├── plugin.json                              <-- Manifest registering rules, 9 skills, sidecars & MCP servers
├── README.md                                <-- Installation Guide & Migration Limitations
├── rules/
│   └── google_ads_rules.md                  <-- System directives, hard constraints & workflow protocols
├── skills/                                  <-- Complete skill packages & executable helper scripts
│   ├── assistant-tutorial/                  <-- Interactive user tutorial
│   │   └── SKILL.md
│   ├── explain/                             <-- Conceptual 4-part explanations with analogies
│   │   └── SKILL.md
│   ├── ext-version/                         <-- Extension version retrieval
│   │   ├── SKILL.md
│   │   └── scripts/get_extension_version.py
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
   - Validate Before Act (cached API version lookup / release notes fallback).
   - Strict Read-Only Policy (No mutate API calls; code generated in `~/saved/code/`).
   - GAQL validation protocol (no `OR`, no `FROM` in metadata queries, bare field names).
   - Automated code generation pipeline with `ruff` linting and `GoogleAdsException` traceback suppression.
   - Source-of-truth priority for local `client_libs/` definitions.
2. **All 9 Skills (`skills/`)**:
   - `validate-gaql`: GAQL dry-runs and 4-step static analysis.
   - `inspect-object`: Dynamic Protobuf resource/message/Enum inspection script.
   - `pmax-listing-filter`: Performance Max webpage exclusion listing tree script.
   - `troubleshoot-conversions`: Offline conversion diagnostics, CSV validator, GCLID sampler, and report generator.
   - `get-cids-under-mcc`: Manager Account child CID tree retriever.
   - `ext-version`: Plugin/assistant version checker script.
   - `explain`: Structured 4-part explanations (Big Picture, Analogy, Interconnectedness, Simple Language).
   - `assistant-tutorial`: Interactive guided walkthrough.
   - `step-by-step`: Structured workflow breakdown.
3. **Daemon Services (`sidecars/`) & MCP Configuration (`mcp_config.json`)**:
   - Agent-to-Agent (A2A) HTTP service for external tool integration.

---

## Functionality That Cannot Be Migrated (Limitations & Adaptations)

While all domain rules, prompt context, Python diagnostic scripts, and skills are fully preserved in this plugin, certain native host platform features cannot be automatically migrated to standard Claude / agy plugin runtimes:

### 1. PreInvocation Host Lifecycle Hooks (`.agents/hooks.json` & `hooks/configure_environment.py`)
- **Limitation**: Standard Claude Desktop, Claude Code, or agy plugin specifications do NOT support native `PreInvocation` shell execution hooks that run arbitrary Python scripts on the host before every model turn.
- **Impact**: Automatic background actions (such as copying `~/google-ads.yaml` into `config/google-ads.yaml`, dynamically creating/updating a local Python virtual environment `.venv`, deleting stale `api_version.txt` files older than 19 hours, or injecting ephemeral environment context into the context window) cannot be run automatically on every turn by the host plugin engine.
- **Adaptation**: Users must set up their local Python environment (`pip install google-ads ruff pytest`) and provide `GOOGLE_ADS_CONFIGURATION_FILE_PATH=config/google-ads.yaml` manually or via an initial setup script (`install.sh`).

### 2. Background Auto-Updates via GitHub (`hooks/check_github_version.py`)
- **Limitation**: Standard plugin architectures do not allow unprompted network calls prior to model response generation to check for newer assistant versions on GitHub.
- **Adaptation**: Version updates must be managed via git pulls or manual updates rather than a pre-session background hook.

### 3. Native IDE / Workspace Isolation Enforcement
- **Limitation**: In the standalone assistant workspace, hooks strictly enforce using `./.venv/bin/python3` and prohibit bare system `python3` commands.
- **Adaptation**: The plugin relies on prompt rules (`rules/google_ads_rules.md`) instructing the agent to run Python scripts using the active virtual environment, rather than hardcoded environment injection.

### 4. Interactive UI Form Controls (`ask_question` tool with multi-choice widgets)
- **Limitation**: The custom multi-choice modal rendered by the Antigravity `ask_question` tool is platform-specific.
- **Adaptation**: In standard Claude environments, the agent presents multiple-choice questions directly as text in the chat interface instead of launching interactive UI modals.

---

## Installation & Setup

### Step 1: Copy Plugin Directory
Copy `google_ads_assistant_plugin` to your agent configuration directory:
- **Antigravity / agy**: `~/.gemini/config/plugins/google_ads_assistant_plugin`
- **Claude Desktop / Claude Code**: `~/.config/claude/plugins/google_ads_assistant_plugin`

### Step 2: Configure Credentials
Ensure your `google-ads.yaml` config file exists at `config/google-ads.yaml` or `~/google-ads.yaml`:
```yaml
developer_token: "YOUR_DEVELOPER_TOKEN"
client_id: "YOUR_OAUTH_CLIENT_ID"
client_secret: "YOUR_OAUTH_CLIENT_SECRET"
refresh_token: "YOUR_REFRESH_TOKEN"
use_proto_plus: true
```

### Step 3: Install Python Dependencies
```bash
pip install google-ads ruff pytest
```

### Step 4: Restart Agent Host
Upon restarting your agent host, the plugin rules, 9 skills, sidecars, and MCP tools will be active.
