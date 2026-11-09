# Google Ads API Developer Assistant Plugin

[![Plugin Version](https://img.shields.io/badge/version-4.1.0-blue.svg)](plugin.json)
[![Target Runtimes](https://img.shields.io/badge/runtimes-Antigravity%20%7C%20Claude%20Desktop%20%7C%20Claude%20Code-brightgreen.svg)](plugin.json)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](rules/google_ads_rules.md)

This plugin adds **Google Ads API** tools to AI assistants in **Antigravity (`agy`)**, **Claude Desktop**, and **Claude Code CLI**. It includes diagnostic scripts, static analysis tools, Protobuf object inspectors, conversion validators, and a 4-Step Human-in-the-Loop (HITL) mutation guard.

---

## 📑 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Plugin Architecture](#-plugin-architecture)
- [Claude Code Custom Slash Commands](#-claude-code-custom-slash-commands)
- [Skills Reference](#-skills-reference)
- [Core Directives & Guardrails](#-core-directives--guardrails)
- [Mutate Operations (4-Step HITL & Consequence Verification)](#-mutate-operations-4-step-hitl--consequence-verification)
- [Installation & Setup](#-installation--setup)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Plugin Installation](#2-plugin-installation)
  - [3. Credentials Configuration](#3-credentials-configuration)
  - [4. Assistant Configuration (`config/assistant_config`) & Startup Synchronization](#4-assistant-configuration-configassistant_config--startup-synchronization)
- [CLI Scripts & Usage](#-cli-scripts--usage)
  - [GAQL Validation](#gaql-validation)
  - [Protobuf Object & Enum Inspection](#protobuf-object--enum-inspection)
  - [Manager Account (MCC) Hierarchy](#manager-account-mcc-hierarchy)
  - [Conversion Troubleshooting & CSV Validation](#conversion-troubleshooting--csv-validation)
  - [Performance Max Webpage Exclusion Filter](#performance-max-webpage-exclusion-filter)
  - [Client Libraries Discovery & Upstream GitHub Sync](#client-libraries-discovery--upstream-github-sync)
- [Sidecar Daemon & MCP Integration](#-sidecar-daemon--mcp-integration)
- [Migration & Environment Notes](#-migration--environment-notes)
- [License](#-license)

---

## 🎯 Overview

The **Google Ads API Developer Assistant** plugin helps developers build and test code for the Google Ads API. It combines schema inspection and read-only diagnostics with a **4-Step Human-in-the-Loop (HITL) Mutation & Consequence Verification Protocol**. Before any live API write runs, the plugin validates the request with `validate_only=True`, writes a SHA-256 receipt to `saved/data/last_dry_run.json`, shows the financial and serving effects, and waits for your approval.

---

## 🚀 Key Features

- **4-Step HITL Mutation & Consequence Verification (`execute-mutation` — `create` & `update` Only)**: Runs a two-step `--dry-run` (`validate_only=True`) and `--execute` workflow for `create` and `update` operations. Delete (`remove`) operations are always blocked. It writes SHA-256 receipts (`saved/data/last_dry_run.json`), shows financial and serving effects, and prompts for `PreToolUse` hook confirmation (`"decision": "force_ask"`).
- **GAQL Validation**: Checks queries in 4 steps (Schema Lookup, Compatibility Check, Static Analysis, and Live Dry-Run with `validate_only=True`). It blocks invalid syntax such as the `OR` operator.
- **Protobuf Object Inspection**: Reads API resources, messages, and Enums directly from the Python client library descriptors.
- **Conversion Upload Troubleshooting**: Checks `offline_conversion_upload_client_summary`, compares click timestamps with conversion timestamps, samples GCLIDs, and validates CSV files before upload.
- **MCC Account Hierarchy Lookup**: Finds child Customer IDs (CIDs) and sub-manager accounts, and prints a console tree or saves a CSV file.
- **Performance Max Webpage Exclusions**: Creates scripts for asset group webpage exclusion filters (`listing_source = WEBPAGE`).
- **Code Linting & Error Handling**: Formats and checks all generated Python scripts with `ruff`, adds Python type hints, and catches `GoogleAdsException` errors.
- **A2A Sidecar & MCP Service**: Runs a background HTTP server for Agent-to-Agent (A2A) tasks and Model Context Protocol (MCP) tools.

---

## 📁 Plugin Architecture

```
google-ads-api-developer-assistant/
├── plugin.json                              # Plugin manifest for metadata and features
├── README.md                                # Documentation and usage guide
├── migration.md                             # Platform migration notes
├── mcp_config.json                          # MCP server configuration
├── config/
│   ├── assistant_config                     # Unified TOML config (api_version, customer_id, execute_mutates)
│   └── config_init.py                       # Session config initializer and PreInvocation/PreToolUse hook
├── rules/
│   └── google_ads_rules.md                  # System directives and safety rules
├── commands/                               # Claude Code slash commands
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
├── skills/                                  # Skills and diagnostic scripts
│   ├── assistant-tutorial/                  # Interactive user tutorial
│   │   └── SKILL.md
│   ├── execute-mutation/                    # 4-Step HITL mutation runner and consequence verifier
│   │   ├── SKILL.md
│   │   └── scripts/run_mutation.py
│   ├── explain/                             # 4-part explanations with analogies
│   │   └── SKILL.md
│   ├── ext-version/                         # Assistant and API version lookup
│   │   ├── SKILL.md
│   │   └── scripts/
│   │       ├── get_extension_version.py
│   │       └── get_latest_api_version.py
│   ├── get-cids-under-mcc/                  # Account hierarchy lookup and CID list
│   │   ├── SKILL.md
│   │   └── scripts/get_cids_under_mcc.py
│   ├── inspect-object/                      # Protobuf message and Enum inspector
│   │   ├── SKILL.md
│   │   └── scripts/inspect_object.py
│   ├── pmax-listing-filter/                 # Performance Max asset group webpage listing filters
│   │   ├── SKILL.md
│   │   └── scripts/create_pmax_webpage_filter.py
│   ├── step-by-step/                        # Multi-step task list
│   │   └── SKILL.md
│   ├── troubleshoot-conversions/            # Conversion diagnostics, CSV checks, and GCLID sampling
│   │   ├── SKILL.md
│   │   ├── references/report_template.md
│   │   └── scripts/
│   │       ├── get_recent_gclids.py
│   │       ├── troubleshoot_conversions.py
│   │       └── validate_conversion_upload.py
│   ├── sync-client-libs/                    # Client library lookup and GitHub sync
│   │   ├── SKILL.md
│   │   └── scripts/sync_client_libs.py
│   └── validate-gaql/                       # 4-step GAQL validation and live dry-run runner
│       ├── SKILL.md
│       └── scripts/validate_gaql.py
├── sidecars/
│   └── google-ads-a2a-service/              # Agent-to-Agent (A2A) HTTP sidecar service
│       ├── sidecar.json
│       └── server.py
└── client_libs/                             # Local Google Ads Python client library and protos
    └── google-ads-python/
```

---

## ⚡ Claude Code Custom Slash Commands

In Claude Code, use these slash commands to run specific tools:

| Slash Command | Description | Example Usage |
| :--- | :--- | :--- |
| **`/validate-gaql`** | Checks GAQL queries with 4-step static analysis and API dry-runs. | `/validate-gaql SELECT campaign.id FROM campaign` |
| **`/inspect-object`** | Shows Protobuf fields, field types, labels, and Enum values. | `/inspect-object Campaign` or `/inspect-object CampaignStatusEnum` |
| **`/troubleshoot-conversions`** | Checks conversion upload errors, validates CSV format, and samples GCLIDs. | `/troubleshoot-conversions 1234567890 uploads.csv` |
| **`/get-cids`** | Lists child accounts under an MCC account. | `/get-cids 1234567890` |
| **`/pmax-filter`** | Creates Asset Group webpage exclusion filter trees for PMax. | `/pmax-filter 1234567890 987654321` |
| **`/explain`** | Explains a topic in 4 parts (*Big Picture*, *Analogy*, *Interconnectedness*, *Simple Language*). | `/explain click_view` |
| **`/assistant-tutorial`** | Starts an interactive tutorial. | `/assistant-tutorial` |
| **`/step-by-step`** | Breaks complex Google Ads API tasks into numbered steps. | `/step-by-step Create an AI Max for Search campaign` |
| **`/sync-client-libs`** | Updates local client libraries in `client_libs/` from the latest GitHub releases. | `/sync-client-libs python` |
| **`/ext-version`** | Shows the plugin version and the active API version. | `/ext-version` |

---

## 🛠 Skills Reference

| Skill Name | Description | Key Script / Asset |
| :--- | :--- | :--- |
| **`validate-gaql`** | Checks GAQL queries with 4-step static analysis and `validate_only=True` dry-runs. | `skills/validate-gaql/scripts/validate_gaql.py` |
| **`inspect-object`** | Shows Protobuf fields, field types, labels (`OPTIONAL` or `REPEATED`), and Enum values. | `skills/inspect-object/scripts/inspect_object.py` |
| **`troubleshoot-conversions`** | Checks conversion upload errors, reads upload summaries, samples GCLIDs, and validates CSV files. | `skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py` |
| **`get-cids-under-mcc`** | Finds child CIDs under a Manager Account (MCC) and prints a tree or saves a CSV file. | `skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py` |
| **`pmax-listing-filter`** | Builds asset group webpage exclusion filters (`listing_source = WEBPAGE`) for PMax campaigns. | `skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py` |
| **`ext-version`** | Reads current version numbers for diagnostic reports. | `skills/ext-version/scripts/get_extension_version.py` |
| **`explain`** | Explains topics in 4 parts: *Big Picture*, *Analogy*, *Interconnectedness*, and *Simple Language*. | `skills/explain/SKILL.md` |
| **`assistant-tutorial`** | Guides you through 16 Google Ads API topics in an interactive tutorial. | `skills/assistant-tutorial/SKILL.md` |
| **`sync-client-libs`** | Checks client libraries in `client_libs/` against GitHub releases and updates older libraries. | `skills/sync-client-libs/scripts/sync_client_libs.py` |
| **`execute-mutation`** | Runs Google Ads API `create` and `update` mutations (blocks delete / `remove` operations) with the 4-Step HITL protocol. | `skills/execute-mutation/scripts/run_mutation.py` |
| **`step-by-step`** | Divides complex tasks into numbered steps with verification checks. | `skills/step-by-step/SKILL.md` |

---

## 🔒 Core Directives & Guardrails

The assistant follows the rules in [google_ads_rules.md](rules/google_ads_rules.md):

1. **Validate Before Act Protocol**:
   - Reads the active Google Ads API version (`api_version`) from `config/assistant_config`. If `api_version` is not set, the assistant finds the latest stable release, asks for your confirmation, and saves it.
2. **4-Step HITL Mutation Mandate (`create` and `update` Only — Deletion Prohibited)**:
   - Allows only **`create`** and **`update`** mutations. It blocks all delete operations (`remove` / `remove_all` operations, `remove_*` RPCs, or `status = REMOVED`). To run a live `create` or `update` mutation, you must set `execute_mutates = true` in `config/assistant_config`, have a valid `validate_only=True` dry-run receipt (`saved/data/last_dry_run.json`), and approve the `PreToolUse` hook prompt (`config/config_init.py`).
3. **GAQL Syntax Rules**:
   - **No `OR` operator**: GAQL does not allow the `OR` operator. The assistant rewrites queries to use `IN` or splits them into separate queries.
   - **No `FROM` clause in metadata**: Queries to `GoogleAdsFieldService` must not contain a `FROM` clause.
   - **Bare field names**: Metadata queries use field names without prefixes (`name`, `category`).
4. **Source of Truth**:
   - The local `client_libs/google-ads-python/` directory is the primary reference for `.proto` definitions and code examples. The assistant never modifies files in `client_libs/`.
5. **Clean Error Output**:
   - Generated Python scripts catch `GoogleAdsException` errors to hide long gRPC stack traces and print clear error messages.

---

## 🛡️ Mutate Operations (4-Step HITL & Consequence Verification)

> **Create & Update Only (Deletion Prohibited):** You can run only **`create`** and **`update`** mutations. The `PreToolUse` hook, `run_mutation.py`, and the A2A sidecar block any delete operation (`remove` or `remove_all` fields, `remove_*` or `delete_*` RPC methods, or `status = REMOVED`) with `BLOCKED_PROHIBITED_DELETION` before any RPC call. To stop ad serving without deleting a resource, update its `status` to `PAUSED`.

All write and mutation requests use the [`execute-mutation` skill](skills/execute-mutation/SKILL.md) and the `PreToolUse` hook in [`config/config_init.py`](config/config_init.py):

1. **Pre-Mutation State & Blast Radius Lookup (GAQL Read):** Reads the current resource state (`status`, `amount_micros`, and `cpc_bid_micros` divided by `1,000,000`) and counts active child entities (`ad_group` and `ad_group_ad`).
2. **Mandatory `validate_only=True` Dry-Run & Signed Receipt:** Runs the script in `--dry-run` mode with `skills/execute-mutation/scripts/run_mutation.py --dry-run`. This step checks the schema, `FieldMask` paths, and policy rules against the Google Ads API, and writes a SHA-256 receipt to `saved/data/last_dry_run.json`.
3. **Consequence Disclosure & User Prompt:** Shows the **Mutation & Consequence Verification Card** with financial changes, affected child entities, and reversibility (`REVERSIBLE` or `IRREVERSIBLE`). Then it waits for your confirmation.
4. **`PreToolUse` Hook Gate & Live Execution:** When `--execute` runs, `config/config_init.py` checks that `execute_mutates = true` in `config/assistant_config`. It also checks the age ($\le 30\text{ min}$), `script_sha256`, and `request_sha256` of `saved/data/last_dry_run.json`. The hook blocks unverified or changed scripts (`"decision": "deny"`). For verified mutations, the hook shows a CLI confirmation prompt (`"decision": "force_ask"` in `agy` and `"permissionDecision": "ask"` in `Claude Code CLI`) and runs the request with `ResponseContentType.MUTABLE_RESOURCE`.

---

## 📦 Installation & Setup

### 1. Prerequisites

- Install Python 3.11 or later.
- Install the required Python packages:
  ```bash
  pip install google-ads ruff pytest
  ```

### 2. Plugin Installation

Run the installation script from the root directory of the repository:

#### For Antigravity / agy:
```bash
./install.sh agy
```
This command installs a standalone copy into `~/.gemini/config/plugins/google-ads-api-developer-assistant`.

#### For Claude Desktop / Claude Code:
```bash
./install.sh claude
```
This command installs a standalone copy into `~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant` and registers the local marketplace.

### 3. Credentials Configuration

Create a `google-ads.yaml` file at `~/google-ads.yaml` (or `config/google-ads.yaml`):

```yaml
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

Set your API version, default Customer ID, mutate switch, and plugin state in `config/assistant_config` (in TOML format):
```toml
api_version = "<api_version> (e.g., vXX)"
customer_id = "12345678"
execute_mutates = false
enabled = true
```

To turn off the plugin so `jetski`/`agy` does not load it, run `./plugin.sh disable` (or `.\plugin.ps1 disable` on Windows). To turn it on again or check its status, run `./plugin.sh enable`, `./plugin.sh status`, or `./plugin.sh test`.

#### Financial Transaction Upper Limits (`config/financial_limits` & `set_financial_limits.py`)

Set upper limits for financial Google Ads API mutate operations in [`config/financial_limits`](config/financial_limits) with `Service.field` keys. Write each value in the exact numeric unit that the API field uses: `micros` (`int64`), `currency_units` (`double`), `decimal_ratio` (`double`), or `micros_proportion` (`int64`).

By default, every value is `0` (`int64`) or `0.0` (`double`). A value of `0` or `0.0` means that the field **cannot be changed**. To allow changes to a field, set a value **greater than zero (`> 0`)** as its **upper limit**. If a mutation tries to change a `0` / `0.0` field or exceeds a configured upper limit (`> 0`), the plugin blocks the command at the HITL step, shows an error, and writes `BLOCKED_FINANCIAL_LIMIT_EXCEEDED` to `saved/logs/mutation_audit.jsonl`.

Use [`config/set_financial_limits.py`](config/set_financial_limits.py) (or `skills/execute-mutation/scripts/set_financial_limits.py`) to list, set (`> 0`), or reset (`0` / `0.0`) financial limits:
```bash
# List all Service.field financial limits, units, and current values
python3 config/set_financial_limits.py --list

# Set a value > 0 in the API unit to allow changes up to that limit
python3 config/set_financial_limits.py \
  --set CampaignBudgetService.amount_micros=50000000 \
  --set AssetService.amount_micros=20000000 \
  --set AdGroupService.cpc_bid_micros=5000000 \
  --set ConversionUploadService.conversion_value=500.0 \
  --set BiddingStrategyService.target_roas=10.0

# Reset one limit or all limits to 0 / 0.0 (not modifiable)
python3 config/set_financial_limits.py --reset CampaignBudgetService.amount_micros
python3 config/set_financial_limits.py --reset-all
```

When `enabled = true` and you enter your first prompt in Antigravity (`agy`) or Claude Code CLI (`claude`), the `PreInvocation` hook (`python3 config/config_init.py --hook`) copies your credentials to `config/google-ads.yaml` (`0600` permissions), updates `api_version` in `config/assistant_config`, and runs a 5-step version check:
1. **Check Python Site-Directory Version Against PyPI:** Compares the installed `google-ads` package in `site.getsitepackages()` against `pypi.org` (`https://pypi.org/pypi/google-ads/json`).
2. **Check Latest GitHub Release:** Checks the latest release of `googleads/google-ads-python` on GitHub.
3. **Select Active Google Ads API Version:** Selects the Google Ads API version from steps 1 and 2.
4. **Show Results Table:** Shows the 3-component version table at the top of the first response.
5. **Ask to Update Outdated Packages:** If any component is outdated, the assistant asks if you want to update it before continuing:
   - **If You Reply `Yes` (`sync_client_libs.py --upgrade_system`):** Installs the latest `google-ads` package from `pypi.org`, updates `client_libs/google-ads-python`, updates `api_version` in `config/assistant_config`, and prints the updated table.
   - **If You Reply `No` (`sync_client_libs.py --check_only`):** Keeps the installed versions and continues.

---

## 💻 CLI Scripts & Usage

You can run all skill scripts from the command line. Replace `<api_version>` with your target version (for example, `vXX`).

### GAQL Validation

Pass a query with `--query` / `-q` or through `stdin`:
```bash
# Pass query with CLI flag
python3 skills/validate-gaql/scripts/validate_gaql.py \
  --customer_id 1234567890 \
  --api_version <api_version> \
  --query "SELECT campaign.id, campaign.name, metrics.impressions FROM campaign WHERE segments.date DURING LAST_30_DAYS"

# Or pipe query through stdin
echo "SELECT campaign.id, campaign.name, metrics.impressions FROM campaign WHERE segments.date DURING LAST_30_DAYS" | \
  python3 skills/validate-gaql/scripts/validate_gaql.py \
    --customer_id 1234567890 \
    --api_version <api_version>
```

### Protobuf Object & Enum Inspection

Check field definitions, labels (`OPTIONAL` or `REPEATED`), and nested types:
```bash
# Check a resource message
python3 skills/inspect-object/scripts/inspect_object.py \
  --object_name Campaign \
  --api_version <api_version>

# Check an Enum
python3 skills/inspect-object/scripts/inspect_object.py \
  --object_name CampaignStatusEnum.CampaignStatus \
  --api_version <api_version>
```

### Manager Account (MCC) Hierarchy

List all client accounts under an MCC:
```bash
# Print account tree to console
python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py \
  --customer_id 1234567890 \
  --api_version <api_version> \
  --print_cids

# Save to CSV under saved/data/
python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py \
  --customer_id 1234567890 \
  --api_version <api_version> \
  --save_csv
```

### Conversion Troubleshooting & CSV Validation

```bash
# Create conversion diagnostic report
python3 skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py \
  --customer_id 1234567890 \
  --api_version <api_version>

# Validate offline conversion upload CSV before upload
python3 skills/troubleshoot-conversions/scripts/validate_conversion_upload.py \
  --csv_path data/conversions.csv \
  --api_version <api_version>

# Sample recent GCLIDs with click timestamps
python3 skills/troubleshoot-conversions/scripts/get_recent_gclids.py \
  --customer_id 1234567890 \
  --api_version <api_version>
```

### Performance Max Webpage Exclusion Filter

Create listing filter exclusion trees for PMax asset groups:
```bash
python3 skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py \
  --customer_id 1234567890 \
  --asset_group_id 987654321 \
  --url_exclusion "example.com/excluded-category" \
  --api_version <api_version>
```

### Client Libraries Discovery & Upstream GitHub Sync

Check and update client libraries in `client_libs/` from GitHub releases, and check system `site-packages` versions:
```bash
# Check versions without updating (dry-run)
python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only

# Update outdated client libraries to the latest GitHub releases
python3 skills/sync-client-libs/scripts/sync_client_libs.py

# Upgrade the system site-packages package (google-ads) to the latest release
python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system

# Print JSON output
python3 skills/sync-client-libs/scripts/sync_client_libs.py --json
```

---

## 🔌 Sidecar Daemon & MCP Integration

### What Is a Sidecar?

A **sidecar** is a separate helper process that runs next to a main application on the same computer. It shares the local network (`127.0.0.1`), local files, and session lifecycle with the main application.

In CLI agent environments such as **Antigravity (`agy`)** and **Claude Code CLI**, tools run in two ways:
- **Skill Scripts & Hooks (One-Time Subprocesses)**: When the agent runs a skill script (in `skills/`) or a hook (`config_init.py`), the host starts a new OS process for that command, reads the output, and stops the process.
- **Sidecar Daemons (Background Services)**: The host CLI starts a sidecar server in the background when the plugin loads and keeps it running during the session.

A sidecar daemon gives you three benefits:
1. **Low Latency**: The Python interpreter and libraries stay in memory, so requests do not wait for process startup.
2. **Structured HTTP & MCP Requests**: The sidecar listens on a local port (`127.0.0.1`) and accepts typed JSON requests over HTTP or Model Context Protocol (MCP).
3. **Automatic Lifecycle Control**: The host CLI starts, monitors, restarts, and stops the sidecar automatically using `sidecar.json` or `mcp_config.json`.

### How the Sidecar Works in the Assistant

The plugin includes an Agent-to-Agent (A2A) HTTP service in `sidecars/google-ads-a2a-service/` (`sidecar.json` and `server.py`).

1. **Lifecycle Control**: When `enabled = true` in `config/assistant_config`, the host reads `sidecars/google-ads-a2a-service/sidecar.json` and starts `python3 server.py` in the background. It sets the port through `ANTIGRAVITY_SIDECAR_WEB_PORT` (or `A2A_PORT`, default `8900`) and restarts the process if it stops (`"restart_policy": "always"`). When you run `./plugin.sh disable`, the script renames `sidecar.json` and `mcp_config.json` to `.disabled` and stops the background server.
2. **Startup Credential & Config Sync**: At startup (and before each task), `server.py` runs `config_init.sync_and_set_config_kv()`. This function copies credentials from `~/google-ads.yaml` to `config/google-ads.yaml` (`0600` permissions) and reads `customer_id`, `api_version`, and `execute_mutates` from `config/assistant_config`.
3. **API Version Selection**: For each task, `get_effective_api_version()` checks the request payload, the `GOOGLE_ADS_API_VERSION` environment variable, `config/assistant_config`, local `client_libs/google-ads-python` `v<N>` directories, and installed `google.ads.googleads` packages.
4. **A2A HTTP Endpoints**: The server listens on `127.0.0.1:8900` (or `ANTIGRAVITY_SIDECAR_WEB_PORT`):
   - `GET /` or `GET /health`: Returns service status, active plugin version, and listening port.
   - `POST /v1/a2a/tasks`: Runs structured tasks for `GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, `TROUBLESHOOT_CONVERSIONS`, `PREPARE_MUTATION` (writes a SHA-256 `validate_only=True` receipt to `saved/data/last_dry_run.json` and returns the **Mutation & Consequence Verification Card**), and `EXECUTE_MUTATION` (checks `execute_mutates = true`, user confirmation, and the SHA-256 dry-run receipt before writing to `saved/logs/mutation_audit.jsonl`).

To start or test the sidecar manually:
```bash
python3 sidecars/google-ads-a2a-service/server.py
curl http://127.0.0.1:8900/health
```

### Model Context Protocol (MCP)

The `mcp_config.json` file configures the MCP server:
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

Keep these points in mind when you run the plugin across different agent environments:

- **Virtual Environments**: Make sure you install `google-ads` and `ruff` in the active Python environment that your host agent uses.
- **Interactive Prompts**: Antigravity shows interactive questions as UI modal dialogs. Claude Desktop and Claude Code CLI show questions as text in the chat.
- **Saved File Paths**: Executable code must be saved in the `saved` subdirectory of your current working directory (for example, `./saved/` or `./saved/code/`). The assistant saves generated code, CSV exports, diagnostic reports/receipts, and mutation audit logs in `saved/code/`, `saved/data/`, and `saved/logs/`.

See [migration.md](migration.md) for more details on runtime behavior.

---

## 📄 License

This project uses the Apache License 2.0. See the [LICENSE](../../LICENSE) file for details.
