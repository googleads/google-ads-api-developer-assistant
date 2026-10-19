# Google Ads API Developer Assistant Plugin

[![Plugin Version](https://img.shields.io/badge/version-4.1.0-blue.svg)](plugin.json)
[![Target Runtimes](https://img.shields.io/badge/runtimes-Antigravity%20%7C%20Claude%20Desktop%20%7C%20Claude%20Code-brightgreen.svg)](plugin.json)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](rules/google_ads_rules.md)

An agentic developer assistant plugin for the **Google Ads API**. This plugin equips AI assistants in **Antigravity (agy)**, **Claude Desktop**, and **Claude Code CLI** with deep domain intelligence, executable diagnostic tools, static analysis pipelines, Protobuf object inspectors, conversion validators, and strict HITL API mutation guardrails.

---

## 📑 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Plugin Architecture](#plugin-architecture)
- [Skills Reference](#skills-reference)
- [Core Directives & Guardrails](#core-directives--guardrails)
- [Mutate Operations (4-Step HITL & Consequence Verification)](#-mutate-operations-4-step-hitl--consequence-verification)
- [Installation & Setup](#installation--setup)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Plugin Installation](#2-plugin-installation)
  - [3. Credentials Configuration](#3-credentials-configuration)
  - [4. Assistant Configuration (`config/assistant_config`)](#4-assistant-configuration-configassistant_config)
- [CLI Scripts & Usage](#cli-scripts--usage)
  - [GAQL Validation](#gaql-validation)
  - [Protobuf Object & Enum Inspection](#protobuf-object--enum-inspection)
  - [Manager Account (MCC) Hierarchy](#manager-account-mcc-hierarchy)
  - [Conversion Troubleshooting & CSV Validation](#conversion-troubleshooting--csv-validation)
  - [Performance Max Webpage Exclusion Filter](#performance-max-webpage-exclusion-filter)
- [Sidecar Daemon & MCP Integration](#sidecar-daemon--mcp-integration)
- [Migration & Environment Notes](#migration--environment-notes)
- [License](#license)

---

## 🎯 Overview

The **Google Ads API Developer Assistant** plugin is engineered specifically for developers building against the Google Ads API. It combines deep schema inspection and read-only diagnostics with a **4-Step Human-in-the-Loop (HITL) Mutation & Consequence Verification Protocol**—ensuring any API write is first dry-run validated (`validate_only=True`), cryptographically signed (`saved/data/last_dry_run.json`), and explicitly approved by the user after reviewing its financial and operational consequences.

---

## 🚀 Key Features

- **4-Step HITL Mutation & Consequence Verification (`execute-mutation`)**: Two-phase `--dry-run` (`validate_only=True`) and `--execute` workflow with SHA-256 tamper-evident receipts (`saved/data/last_dry_run.json`), financial/serving consequence analysis, and deterministic `PreToolUse` hook confirmation (`"decision": "force_ask"`).
- **Programmatic GAQL Validation**: 4-step sequence (Schema Discovery, Compatibility Checking, Static Analysis, and Runtime Dry-Runs using `validate_only=True`). Enforces strict rules such as zero `OR` operator tolerance.
- **Dynamic Protobuf Object Inspection**: Real-time inspection of API resources, messages, and Enums from the official Python client library descriptors without guessing schema structures.
- **Conversion Upload Troubleshooting**: Diagnostic reporting against `offline_conversion_upload_client_summary`, click timestamp vs. conversion timestamp logic validation, GCLID sampling, and pre-upload CSV structure checks.
- **MCC Account Hierarchy Exploration**: Recursive discovery of child Customer IDs (CIDs) and sub-manager structures with console trees or CSV exports.
- **Performance Max Webpage Exclusions**: Scripting for asset group webpage listing filter trees (`vertical = WEBPAGE`).
- **Automated Linting & Typing**: Automatic code formatting and linting via `ruff`, full Python type hinting, and standard `GoogleAdsException` traceback suppression wrappers.
- **A2A Sidecar & MCP Service**: Background HTTP daemon supporting agent-to-agent task execution and Model Context Protocol (MCP) tool integration.

---

## 📁 Plugin Architecture

```
google-ads-api-developer-assistant/
├── plugin.json                              # Plugin manifest registering metadata & capabilities
├── README.md                                # Documentation & usage guide
├── migration.md                             # Platform migration notes & runtime limitations
├── mcp_config.json                          # MCP server configuration
├── config/
│   ├── assistant_config                     # Unified TOML config (api_version, customer_id, execute_mutates)
│   └── config_init.py                       # Session config initializer & PreInvocation/PreToolUse hook
├── rules/
│   └── google_ads_rules.md                  # Mandatory system directives & safety constraints
├── commands/                               # Claude Code custom slash commands
│   ├── validate-gaql.md                     # /validate-gaql [query]
│   ├── inspect-object.md                    # /inspect-object <name>
│   ├── troubleshoot-conversions.md          # /troubleshoot-conversions [cid] [csv]
│   ├── get-cids.md                          # /get-cids <mcc_id>
│   ├── pmax-filter.md                       # /pmax-filter [cid] [asset_group_id]
│   ├── explain.md                           # /explain <concept>
│   ├── assistant-tutorial.md                # /assistant-tutorial
│   ├── step-by-step.md                      # /step-by-step <task>
│   ├── sync-client-libs.md                  # /sync-client-libs [lang]
│   └── ext-version.md                       # /ext-version
├── skills/                                  # Bundled skills and executable diagnostic scripts
│   ├── assistant-tutorial/                  # Interactive guided walkthrough
│   │   └── SKILL.md
│   ├── execute-mutation/                    # 4-Step HITL mutation runner & consequence verifier
│   │   ├── SKILL.md
│   │   └── scripts/run_mutation.py
│   ├── explain/                             # Conceptual 4-part explanations with real-world analogies
│   │   └── SKILL.md
│   ├── ext-version/                         # Assistant & API version discovery
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── get_extension_version.py
│   │       └── get_latest_api_version.py
│   ├── get-cids-under-mcc/                  # Account hierarchy resolution & CID listing
│   │   ├── SKILL.md
│   │   └── scripts/get_cids_under_mcc.py
│   ├── inspect-object/                      # Dynamic Protobuf message and Enum inspector
│   │   ├── SKILL.md
│   │   └── scripts/inspect_object.py
│   ├── pmax-listing-filter/                 # Performance Max asset group webpage listing filters
│   │   ├── SKILL.md
│   │   └── scripts/create_pmax_webpage_filter.py
│   ├── step-by-step/                        # Structured multi-phase task breakdown
│   │   └── SKILL.md
│   ├── troubleshoot-conversions/            # Conversion diagnostics, CSV validation & GCLID sampling
│   │   ├── SKILL.md
│   │   ├── references/report_template.md
│   │   └── scripts/
│   │       ├── get_recent_gclids.py
│   │       ├── troubleshoot_conversions.py
│   │       └── validate_conversion_upload.py
│   ├── sync-client-libs/                    # Automated client library discovery & GitHub sync
│   │   ├── SKILL.md
│   │   └── scripts/sync_client_libs.py
│   └── validate-gaql/                       # 4-step GAQL validation and live dry-run runner
│       ├── SKILL.md
│       └── scripts/validate_gaql.py
├── sidecars/
│   └── google-ads-a2a-service/              # Agent-to-Agent (A2A) HTTP sidecar service
│       ├── sidecar.json
│       └── server.py
└── client_libs/                             # Source-of-truth Google Ads Python client library & protos
    └── google-ads-python/
```

---

## ⚡ Claude Code Custom Slash Commands

When installed in Claude Code, the plugin provides custom slash commands with built-in parameter extraction:

| Slash Command | Description | Example Usage |
| :--- | :--- | :--- |
| **`/validate-gaql`** | Validates GAQL queries via 4-step static analysis and API dry-runs. | `/validate-gaql SELECT campaign.id FROM campaign` |
| **`/inspect-object`** | Inspects Protobuf fields, field types, labels, and Enum values. | `/inspect-object Campaign` or `/inspect-object CampaignStatusEnum` |
| **`/troubleshoot-conversions`** | Diagnoses conversion upload failures, validates CSV format, samples GCLIDs. | `/troubleshoot-conversions 1234567890 uploads.csv` |
| **`/get-cids`** | Retrieves child account hierarchy under an MCC account. | `/get-cids 1234567890` |
| **`/pmax-filter`** | Generates Asset Group webpage exclusion filter trees for PMax. | `/pmax-filter 1234567890 987654321` |
| **`/explain`** | Formats conceptual topics into 4 sections (*Big Picture*, *Analogy*, *Interconnectedness*, *Simple Language*). | `/explain click_view` |
| **`/assistant-tutorial`** | Starts an interactive, progressive conversational guide. | `/assistant-tutorial` |
| **`/step-by-step`** | Breaks complex Google Ads API tasks into structured sequential phases. | `/step-by-step Create an AI Max for Search campaign` |
| **`/sync-client-libs`** | Synchronizes local client libraries in `client_libs/` with latest GitHub releases. | `/sync-client-libs python` |
| **`/ext-version`** | Displays the assistant plugin version and active API version. | `/ext-version` |

---

## 🛠 Skills Reference

| Skill Name | Description | Key Script / Asset |
| :--- | :--- | :--- |
| **`validate-gaql`** | Validates GAQL queries via 4-step static analysis and runtime dry-runs with `validate_only=True`. | `skills/validate-gaql/scripts/validate_gaql.py` |
| **`inspect-object`** | Inspects Protobuf fields, field types, labels (`OPTIONAL`/`REPEATED`), and Enum values dynamically. | `skills/inspect-object/scripts/inspect_object.py` |
| **`troubleshoot-conversions`** | Diagnoses conversion upload failures, verifies upload summaries, samples GCLIDs, and pre-validates CSVs. | `skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py` |
| **`get-cids-under-mcc`** | Traverses Manager Account (MCC) hierarchy to list child CIDs with tree depth and export to CSV. | `skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py` |
| **`pmax-listing-filter`** | Generates asset group webpage exclusion listing filter trees (`vertical = WEBPAGE`) for PMax campaigns. | `skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py` |
| **`ext-version`** | Retrieves current version information for diagnostic reports. | `skills/ext-version/scripts/get_extension_version.py` |
| **`explain`** | Formats conceptual topics into 4 mandatory sections: *Big Picture*, *Analogy*, *Interconnectedness*, *Simple Language*. | `skills/explain/SKILL.md` |
| **`assistant-tutorial`** | Interactive, progressive conversational guide covering 11 core Google Ads API topics. | `skills/assistant-tutorial/SKILL.md` |
| **`sync-client-libs`** | Discovers client libraries under `client_libs/`, verifies installed releases against GitHub, and automatically syncs outdated codebases. | `skills/sync-client-libs/scripts/sync_client_libs.py` |
| **`execute-mutation`** | Executes Google Ads API write/mutation operations using the 4-Step HITL Verification & Consequence Disclosure Protocol. | `skills/execute-mutation/scripts/run_mutation.py` |
| **`step-by-step`** | Breaks complex multi-part procedures into numbered phases with verification checkpoints. | `skills/step-by-step/SKILL.md` |

---

## 🔒 Core Directives & Guardrails

The assistant strictly complies with [google_ads_rules.md](rules/google_ads_rules.md):

1. **Validate Before Act Protocol**:
   - Reads the target Google Ads API version (`api_version`) from `config/assistant_config`. If unset, identifies the latest stable release, presents it for user confirmation, and persists it.
2. **4-Step HITL Mutation & Consequence Verification Mandate**:
   - Executing live mutations (`mutate`, `create`, `update`, `remove`) requires `execute_mutates = true` in `config/assistant_config`, a verified `validate_only=True` dry-run receipt (`saved/data/last_dry_run.json`), and explicit consequence confirmation via the `PreToolUse` hook (`config/config_init.py`).
3. **GAQL Syntax Strictness**:
   - **No `OR` operator**: The `OR` operator is strictly forbidden in GAQL. The assistant rewrites queries using `IN` or splits them into separate requests.
   - **No `FROM` clause in metadata**: Queries against `GoogleAdsFieldService` must not contain a `FROM` clause.
   - **Bare field names**: Metadata queries use un-prefixed field names (`name`, `category`).
4. **Source of Truth**:
   - The local `client_libs/google-ads-python/` repository provides the ultimate local source of truth for `.proto` definitions and official examples. Client library files are strictly read-only.
5. **Traceback Suppression**:
   - All generated Python scripts wrap calls in `try...except GoogleAdsException` to suppress verbose gRPC call stack dumps and output clean, actionable error messages.

---

## 🛡️ Mutate Operations (4-Step HITL & Consequence Verification)

All write/mutation requests follow a strict two-gate defense-in-depth architecture combining the [`execute-mutation` skill](skills/execute-mutation/SKILL.md) with deterministic `PreToolUse` lifecycle interception in [`config/config_init.py`](config/config_init.py):

1. **Pre-Mutation State & Blast Radius Lookup (GAQL Read):** Queries target resource state (`status`, `amount_micros`, `cpc_bid_micros` converted from `micros` by dividing by `1,000,000`) and active child entity counts (`ad_group`, `ad_group_ad`).
2. **Mandatory `validate_only=True` Dry-Run & Signed Receipt:** Executes the script in `--dry-run` mode via `skills/execute-mutation/scripts/run_mutation.py --dry-run` to validate schema, `FieldMask` paths, and policy compliance against the live Google Ads API, writing a SHA-256 signed receipt to `saved/data/last_dry_run.json`.
3. **Structured Consequence Disclosure & User Prompt:** Presents the **Mutation & Consequence Verification Card** detailing financial deltas, ad-serving blast radius, and reversibility (`REVERSIBLE` vs. `IRREVERSIBLE`), pausing for explicit user confirmation.
4. **Deterministic `PreToolUse` Hook Gate & `Mutate-to-Get` Execution:** When `--execute` runs, `config/config_init.py` verifies `execute_mutates = true` in `config/assistant_config` and checks the freshness ($\le 30\text{ min}$), `script_sha256`, and `request_sha256` of `saved/data/last_dry_run.json`. Unverified or modified scripts are hard-blocked (`"decision": "deny"`), while verified mutations trigger a native CLI confirmation prompt (`"decision": "force_ask"` in `agy` and `"permissionDecision": "ask"` in `Claude Code CLI`) displaying the consequence summary before executing with `ResponseContentType.MUTABLE_RESOURCE`.

---

## 📦 Installation & Setup

### 1. Prerequisites

- Python 3.11+
- Install required Python packages:
  ```bash
  pip install google-ads ruff pytest
  ```

### 2. Plugin Installation

Copy or symlink the plugin into your target agent environment:

#### For Antigravity / agy:
```bash
mkdir -p ~/.gemini/config/plugins
cp -r google-ads-api-developer-assistant ~/.gemini/config/plugins/
```

#### For Claude Desktop / Claude Code:
```bash
mkdir -p ~/.claude/plugins/marketplaces
cp -r google-ads-api-developer-assistant ~/.claude/plugins/marketplaces/
```

### 3. Credentials Configuration

Create a `google-ads.yaml` configuration file at `config/google-ads.yaml` (or `~/.config/google-ads/google-ads.yaml`):

```yaml
developer_token: "INSERT_DEVELOPER_TOKEN"
client_id: "INSERT_OAUTH_CLIENT_ID"
client_secret: "INSERT_OAUTH_CLIENT_SECRET"
refresh_token: "INSERT_REFRESH_TOKEN"
use_proto_plus: true
login_customer_id: "INSERT_MCC_CUSTOMER_ID_IF_APPLICABLE"
```

Set the environment variable:
```bash
export GOOGLE_ADS_CONFIGURATION_FILE_PATH="config/google-ads.yaml"
```

### 4. Assistant Configuration (`config/assistant_config`) & Startup Synchronization

Configure your API version, default Customer ID, and mutate switch in `config/assistant_config` (TOML format):
```toml
api_version = "v26"
customer_id = "12345678"
execute_mutates = false
```

When the user enters their first prompt in an Antigravity (`agy`) session, or in Claude Code CLI (`claude`), the `PreInvocation` hook (`python3 config/config_init.py --hook`) normalizes credentials into `config/google-ads.yaml` (`0600` permissions), advances `api_version` in `config/assistant_config`, and executes the **5-Step Client Library & API Version Verification Workflow**:
1. **Check Python Site-Directory Version Against PyPI:** Inspects the version of `google-ads` installed in the Python site directory (`site.getsitepackages()`, `importlib.metadata.version("google-ads")`) against `pypi.org` (`https://pypi.org/pypi/google-ads/json`).
2. **Check Latest GitHub Release:** Queries the latest release version of the client library on GitHub (`googleads/google-ads-python/releases/latest`).
3. **Determine Active Google Ads API Version:** Determines the Google Ads API version to use based on (1) and (2).
4. **Present Results in a Formatted Table:** Displays the 3-component parity report table at the very top of the first response to the user.
5. **Prompt User When Any Version Outdated:** If any component is not the latest version, asks the user if they want to update them before proceeding:
   - **If the User Replies `Yes` (`sync_client_libs.py --upgrade_system`):** Installs the latest version of `google-ads` from `pypi.org` into the site directory, installs the latest version of the client library into the site directory, updates `client_libs/google-ads-python` in the Assistant directory structure, updates `api_version` in `config/assistant_config` (and `config/api_version.txt` if present) to the latest version, and prints the results table to the screen.
   - **If the User Replies `No` (`sync_client_libs.py --check_only`):** Retains currently installed versions and proceeds.

---

## 💻 CLI Scripts & Usage

All skill scripts can be invoked directly from the command line:

### GAQL Validation

Pass a query directly via `--query` / `-q` or pipe via `stdin`:
```bash
# Pass query via CLI flag
python3 skills/validate-gaql/scripts/validate_gaql.py \
  --customer_id 1234567890 \
  --api_version v25 \
  --query "SELECT campaign.id, campaign.name, metrics.impressions FROM campaign WHERE segments.date DURING LAST_30_DAYS"

# Or pipe query via stdin
echo "SELECT campaign.id, campaign.name, metrics.impressions FROM campaign WHERE segments.date DURING LAST_30_DAYS" | \
  python3 skills/validate-gaql/scripts/validate_gaql.py \
    --customer_id 1234567890 \
    --api_version v25
```

### Protobuf Object & Enum Inspection

Inspect field definitions, labels (`OPTIONAL` vs `REPEATED`), and nested types:
```bash
# Inspect a resource message
python3 skills/inspect-object/scripts/inspect_object.py \
  --object_name Campaign \
  --api_version v25

# Inspect an Enum
python3 skills/inspect-object/scripts/inspect_object.py \
  --object_name CampaignStatusEnum.CampaignStatus \
  --api_version v25
```

### Manager Account (MCC) Hierarchy

Traverse and list all client accounts under an MCC:
```bash
# Print account tree to console
python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py \
  --customer_id 1234567890 \
  --api_version v25 \
  --print_cids

# Export to CSV under saved/data/
python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py \
  --customer_id 1234567890 \
  --api_version v25 \
  --save_csv
```

### Conversion Troubleshooting & CSV Validation

```bash
# Generate comprehensive conversion diagnostic report
python3 skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py \
  --customer_id 1234567890 \
  --api_version v25

# Pre-validate offline conversion upload CSV before sending to API
python3 skills/troubleshoot-conversions/scripts/validate_conversion_upload.py \
  --csv_path data/conversions.csv \
  --api_version v25

# Sample recent GCLIDs with click timestamps
python3 skills/troubleshoot-conversions/scripts/get_recent_gclids.py \
  --customer_id 1234567890 \
  --api_version v25
```

### Performance Max Webpage Exclusion Filter

Generate listing filter exclusion trees for PMax asset groups:
```bash
python3 skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py \
  --customer_id 1234567890 \
  --asset_group_id 987654321 \
  --url_exclusion "example.com/excluded-category" \
  --api_version v25
```

### Client Libraries Discovery & Upstream GitHub Sync

Automatically inspect and synchronize all client libraries in `client_libs/` with latest GitHub releases and verify system site-packages parity:
```bash
# Check versions and system site-packages parity without updating (dry-run)
python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only

# Automatically sync outdated client libraries to latest GitHub releases
python3 skills/sync-client-libs/scripts/sync_client_libs.py

# Upgrade system site-packages package (google-ads) to latest release
python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system

# Output structured JSON
python3 skills/sync-client-libs/scripts/sync_client_libs.py --json
```

---

## 🔌 Sidecar Daemon & MCP Integration

### A2A Sidecar Server

The plugin includes an Agent-to-Agent (A2A) HTTP service located in `sidecars/google-ads-a2a-service/`.

To start the sidecar manually:
```bash
python3 sidecars/google-ads-a2a-service/server.py
```

The daemon listens on port `8900` (or the port defined by `ANTIGRAVITY_SIDECAR_WEB_PORT`):
- `GET /health`: Health check endpoint.
- `POST /v1/a2a/tasks`: Handles JSON-RPC style task payloads for `GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`, `PREPARE_MUTATION`, and `EXECUTE_MUTATION`.

### Model Context Protocol (MCP)

The plugin exposes tools via MCP as defined in `mcp_config.json`:
```json
{
  "mcpServers": {
    "google-ads-api-assistant": {
      "command": "python3",
      "args": [
        "sidecars/google-ads-a2a-service/server.py"
      ],
      "env": {
        "A2A_PORT": "8900",
        "GOOGLE_ADS_CONFIGURATION_FILE_PATH": "config/google-ads.yaml"
      },
      "url": "http://127.0.0.1:8900"
    }
  }
}
```

---

## ℹ️ Migration & Environment Notes

When running this plugin across different agent runtimes, keep the following platform considerations in mind:

- **Virtual Environments**: In custom IDE environments, ensure `google-ads` and `ruff` are installed in the active environment used by the host agent.
- **Interactive UI Modals**: In Antigravity environments, interactive questions render as modal selections; in standard Claude Desktop / CLI sessions, questions are presented directly in conversation text.
- **Directory Layouts**: When asked to save code that can be run later, it MUST strictly be saved in the current working directory in a sub-directory called `saved` (e.g. `./saved/` or `./saved/code/`). Generated code, CSV exports, diagnostic reports/receipts, and mutation audit logs are saved to `saved/code/`, `saved/csv/`, `saved/data/`, and `saved/logs/`.

For comprehensive details on runtime adaptations, refer to [migration.md](migration.md).

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](../../LICENSE) file for details.
