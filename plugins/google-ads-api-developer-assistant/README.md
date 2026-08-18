# Google Ads API Developer Assistant Plugin

[![Plugin Version](https://img.shields.io/badge/version-4.0.0-blue.svg)](plugin.json)
[![Target Runtimes](https://img.shields.io/badge/runtimes-Antigravity%20%7C%20Claude%20Desktop%20%7C%20Claude%20Code-brightgreen.svg)](plugin.json)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](rules/google_ads_rules.md)

An agentic developer assistant plugin for the **Google Ads API**. This plugin equips AI assistants in **Antigravity (agy)**, **Claude Desktop**, and **Claude Code CLI** with deep domain intelligence, executable diagnostic tools, static analysis pipelines, Protobuf object inspectors, conversion validators, and strict API safety guardrails.

---

## 📑 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Plugin Architecture](#plugin-architecture)
- [Skills Reference](#skills-reference)
- [Core Directives & Guardrails](#core-directives--guardrails)
- [Installation & Setup](#installation--setup)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Plugin Installation](#2-plugin-installation)
  - [3. Credentials Configuration](#3-credentials-configuration)
  - [4. API Versioning](#4-api-versioning)
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

The **Google Ads API Developer Assistant** plugin is engineered specifically for developers building against the Google Ads API. It operates under a strict **read-only / zero-mutate execution policy**—ensuring the assistant analyzes and inspects live data safely while generating production-ready, Ruff-linted Python mutation scripts for manual execution.

---

## 🚀 Key Features

- **Programmatic GAQL Validation**: 4-step sequence (Schema Discovery, Compatibility Checking, Static Analysis, and Runtime Dry-Runs using `validate_only=True`). Enforces strict rules such as zero `OR` operator tolerance.
- **Dynamic Protobuf Object Inspection**: Real-time inspection of API resources, messages, and Enums from the official Python client library descriptors without guessing schema structures.
- **Strict Read-Only Safety Policy**: Hard constraints preventing accidental execution of destructive API mutations (`create`, `mutate`, `update`, `delete`). All mutations are generated as verified code in `~/saved/code/`.
- **Conversion Upload Troubleshooting**: Diagnostic reporting against `offline_conversion_upload_client_summary`, click timestamp vs. conversion timestamp logic validation, GCLID sampling, and pre-upload CSV structure checks.
- **MCC Account Hierarchy Exploration**: Recursive discovery of child Customer IDs (CIDs) and sub-manager structures with console trees or CSV exports.
- **Performance Max Webpage Exclusions**: Scripting for asset group webpage listing filter trees (`vertical = WEBPAGE`).
- **Automated Linting & Typing**: Automatic code formatting and linting via `ruff`, full Python type hinting, and standard `GoogleAdsException` traceback suppression wrappers.
- **A2A Sidecar & MCP Service**: Background HTTP daemon supporting agent-to-agent task execution and Model Context Protocol (MCP) tool integration.

---

## 📁 Plugin Architecture

```
google_ads_assistant_plugin/
├── plugin.json                              # Plugin manifest registering metadata & capabilities
├── README.md                                # Documentation & usage guide
├── migration.md                             # Platform migration notes & runtime limitations
├── mcp_config.json                          # MCP server configuration
├── rules/
│   └── google_ads_rules.md                  # Mandatory system directives & safety constraints
├── skills/                                  # Bundled skills and executable diagnostic scripts
│   ├── assistant-tutorial/                  # Interactive guided walkthrough
│   │   └── SKILL.md
│   ├── explain/                             # Conceptual 4-part explanations with real-world analogies
│   │   └── SKILL.md
│   ├── ext-version/                         # Assistant extension version extraction
│   │   ├── SKILL.md
│   │   └── scripts/get_extension_version.py
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
| **`step-by-step`** | Breaks complex multi-part procedures into numbered phases with verification checkpoints. | `skills/step-by-step/SKILL.md` |

---

## 🔒 Core Directives & Guardrails

The assistant strictly complies with [google_ads_rules.md](rules/google_ads_rules.md):

1. **Validate Before Act Protocol**:
   - Reads the target Google Ads API version from `config/api_version.txt`. If unset, identifies the latest stable release, presents it for user confirmation, and persists it.
2. **Zero-Mutate / Read-Only Constraint**:
   - The assistant **never** executes live mutations (`mutate`, `create`, `update`, `delete`). All mutation scripts are written to `~/saved/code/` for manual review and execution by the developer.
3. **GAQL Syntax Strictness**:
   - **No `OR` operator**: The `OR` operator is strictly forbidden in GAQL. The assistant rewrites queries using `IN` or splits them into separate requests.
   - **No `FROM` clause in metadata**: Queries against `GoogleAdsFieldService` must not contain a `FROM` clause.
   - **Bare field names**: Metadata queries use un-prefixed field names (`name`, `category`).
4. **Source of Truth**:
   - The local `client_libs/google-ads-python/` repository provides the ultimate local source of truth for `.proto` definitions and official examples. Client library files are strictly read-only.
5. **Traceback Suppression**:
   - All generated Python scripts wrap calls in `try...except GoogleAdsException` to suppress verbose gRPC call stack dumps and output clean, actionable error messages.

---

## 📦 Installation & Setup

### 1. Prerequisites

- Python 3.10+
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
mkdir -p ~/.claude/plugins
cp -r google-ads-api-developer-assistant ~/.claude/plugins/
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

### 4. API Versioning

Set your preferred API version in `config/api_version.txt` (e.g., `v25`):
```bash
mkdir -p config
echo "v25" > config/api_version.txt
```

---

## 💻 CLI Scripts & Usage

All skill scripts can be invoked directly from the command line:

### GAQL Validation

Pass a query via `stdin` or pipe to run static analysis and live API dry-run:
```bash
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

# Export to CSV under ~/saved/data/
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
  --url_condition "CONTAINS" \
  --url_value "example.com/excluded-category" \
  --api_version v25
```

### Client Libraries Discovery & Upstream GitHub Sync

Automatically inspect and synchronize all client libraries in `client_libs/` with latest GitHub releases:
```bash
# Check versions without updating (dry-run)
python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only

# Automatically sync outdated client libraries to latest GitHub releases
python3 skills/sync-client-libs/scripts/sync_client_libs.py

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
- `POST /v1/a2a/tasks`: Handles JSON-RPC style task payloads for `GAQL_VALIDATE`, `INSPECT_OBJECT`, `GENERATE_CODE`, and `TROUBLESHOOT_CONVERSIONS`.

### Model Context Protocol (MCP)

The plugin exposes tools via MCP as defined in `mcp_config.json`:
```json
{
  "mcpServers": {
    "google-ads-api-assistant": {
      "command": "python3",
      "args": ["-m", "google_ads_assistant_mcp"],
      "env": {
        "GOOGLE_ADS_CONFIGURATION_FILE_PATH": "~/.config/google-ads/google-ads.yaml"
      }
    }
  }
}
```

---

## ℹ️ Migration & Environment Notes

When running this plugin across different agent runtimes, keep the following platform considerations in mind:

- **Virtual Environments**: In custom IDE environments, ensure `google-ads` and `ruff` are installed in the active environment used by the host agent.
- **Interactive UI Modals**: In Antigravity environments, interactive questions render as modal selections; in standard Claude Desktop / CLI sessions, questions are presented directly in conversation text.
- **Directory Layouts**: Generated code and reports are saved to `~/saved/code/` and `~/saved/data/`.

For comprehensive details on runtime adaptations, refer to [migration.md](migration.md).

---

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](client_libs/google-ads-python/LICENSE) file for details.
