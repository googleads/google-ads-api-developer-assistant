# Google Ads API Developer Assistant

**Summary:** Use this assistant to work with the Google Ads API through natural language prompts. You can ask questions, create GAQL queries, generate code in multiple languages, and run API calls in your terminal.

## Table of Contents

- [Overview](#overview)
- [Agentic Design & Approach](#agentic-design--approach)
  - [1. Unified Context via `AGENTS.md` & `CLAUDE.md`](#1-unified-context-via-agentsmd--claudemd)
  - [2. Domain Skills & Slash Commands](#2-domain-skills--slash-commands)
- [Key Features](#key-features)
- [Supported Languages](#supported-languages)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
  - [1. Install Host Platform](#1-install-host-platform)
  - [2. Clone the Assistant](#2-clone-the-assistant)
  - [3. Run Install Script](#3-run-install-script)
  - [4. Configure Credentials](#4-configure-credentials)
  - [5. Configure Assistant Settings (`config/assistant_config`) & Enable/Disable Plugin](#5-configure-assistant-settings-configassistant_config--enabledisable-plugin)
- [Usage](#usage)
- [Stay in sync](#stay-in-sync)
  - [1. What Syncs at Session Startup (`config/config_init.py`)](#1-what-syncs-at-session-startup-configconfig_initpy)
  - [2. Sync Client Libraries During a Session](#2-sync-client-libraries-during-a-session)
  - [3. Manual Terminal Updates](#3-manual-terminal-updates)
  - [4. Client Library & Runtime Version Parity](#4-client-library--runtime-version-parity)
- [Directory Structure](#directory-structure)
- [Plugin Architecture](#plugin-architecture)
- [Sidecar Daemon & How It Functions](#sidecar-daemon--how-it-functions)
  - [What Is a Sidecar?](#what-is-a-sidecar)
  - [How the Sidecar Is Configured in This Repository](#how-the-sidecar-is-configured-in-this-repository)
  - [How the Host Manages the Sidecar Lifecycle](#how-the-host-manages-the-sidecar-lifecycle)
  - [How the Sidecar Functions Within the Assistant](#how-the-sidecar-functions-within-the-assistant)
  - [Run or Test the Sidecar Manually](#run-or-test-the-sidecar-manually)
- [How Mutates Work](#how-mutates-work)
  - [1. Configure the Mutate Switch (`execute_mutates` in `config/assistant_config`)](#1-configure-the-mutate-switch-execute_mutates-in-configassistant_config)
  - [2. The 4-Step HITL Mutation Workflow & What You See on Screen](#2-the-4-step-hitl-mutation-workflow--what-you-see-on-screen)
  - [3. Summary of Safeguards (`config/config_init.py` & `run_mutation.py`)](#3-summary-of-safeguards-configconfig_initpy--run_mutationpy)
- [Behavioral Differences in 4.1.0](#behavioral-differences-in-410)
- [Performance & Functionality Benchmarks](#performance--functionality-benchmarks)
  - [How to Run the Benchmarks](#how-to-run-the-benchmarks)
  - [How to Read the Benchmark Results](#how-to-read-the-benchmark-results)
- [Maintenance](#maintenance)
- [Uninstallation](#uninstallation)
  - [Antigravity](#antigravity)
  - [Claude Code](#claude-code)
- [Contributing](#contributing)
- [Support](#support)
- [License](#license)

---

## Overview

The Google Ads API Developer Assistant helps developers work with the Google Ads API. Use natural language prompts to do these tasks:

*   Get answers to Google Ads API questions.
*   Create Google Ads Query Language (GAQL) queries.
*   Generate executable code with the Google Ads client libraries.
*   Get and show data from the API.

The Google Ads API Developer Assistant (v4.1.0) runs on the **Antigravity** and **Claude Code** agent frameworks. It uses `AGENTS.md` / `CLAUDE.md` files, slash commands, and custom **Skills** to apply safety rules and run validation pipelines.

## Agentic Design & Approach

The assistant uses instruction files, slash commands, and domain tools to interact safely with the Google Ads API.

### 1. Unified Context via `AGENTS.md` & `CLAUDE.md`
The configuration files define the core rules for the assistant:
*   **Version Cache Protocol**: Finds and saves the latest active API version (`api_version` in `config/assistant_config`).
*   **Version Parity Check**: Compares the installed `google-ads` Python package with the local `client_libs/google-ads-python` files and warns you if they do not match.
*   **Code Generation Pipeline**: Checks all generated Python code with `ruff` before it saves or shows the code.
*   **GAQL Validation**: Checks queries against field metadata and compatibility rules.
*   **Safety Constraints (4-Step HITL Mutation Guard — `create` & `update` Only)**: Applies a mandatory 4-step Human-in-the-Loop (HITL) verification protocol to all API mutations. It allows only **`create`** and **`update`** operations and blocks all delete operations (**`remove`** / `remove_all` operations, `remove_*` / `delete_*` RPCs, and `status = REMOVED`). Before any live write runs, the protocol requires a GAQL before-state read, a `validate_only=True` dry-run with a SHA-256 receipt (`saved/data/last_dry_run.json`), a consequence summary, and `PreToolUse` hook confirmation (`"decision": "force_ask"`).

### 2. Domain Skills & Slash Commands
The assistant includes tool directories under `plugins/google-ads-api-developer-assistant/skills/` and slash commands under `plugins/google-ads-api-developer-assistant/commands/`.

You can start each tool with natural language prompts in Antigravity or with slash commands in Claude Code:
*   **HITL-Verified Mutations (`/execute-mutation`)**: Runs a two-step `--dry-run` (`validate_only=True`) and `--execute` workflow for `create` and `update` operations (blocks delete / `remove` operations) with SHA-256 receipt checks and consequence summaries.
*   **GAQL Validation (`/validate-gaql`)**: Validates queries with the API `validate_only` parameter.
*   **Object Inspection (`/inspect-object`)**: Checks API resources, nested messages, and enum definitions.
*   **MCC Account Mapping (`/get-cids`)**: Lists client account hierarchies and sub-account CIDs under manager accounts.
*   **Conversion Troubleshooting (`/troubleshoot-conversions`)**: Checks conversion upload summaries and validates CSV files.
*   **PMax Listing Filters & URL Exclusions (`/pmax-filter`)**: Creates product partition trees and webpage URL exclusions.
*   **Structured Explanations (`/explain`, `/step-by-step`, `/assistant-tutorial`)**: Gives 4-part explanations, numbered step lists, and interactive tutorials.
*   **Environment & Library Sync (`/sync-client-libs`, `/ext-version`)**: Updates client libraries and checks the active API version.

## Key Features

*   **Natural Language Q&A & Conceptual Guidance:** Ask questions about Google Ads API concepts, fields, and usage, or use explanation commands.
    *   *Natural Language:* "What are the available campaign types?", "Tell me about reporting for Performance Max campaigns."
    *   *Claude Code:* `/explain`, `/step-by-step`, `/assistant-tutorial`

*   **Natural Language to GAQL & Client Library Code:** Turn prompts into executable code that uses the Google Ads client libraries.
    *   The assistant saves executable code in `saved/code/`.
    *   *"Show me campaigns with the most conversions last 30 days."*
    *   *"Get all ad groups for customer '123-456-7890'."*
    *   *"Find disapproved ads across all campaigns."*

*   **Validate Complex GAQL Queries:** Check GAQL queries against API metadata and compatibility rules.
    *   *Claude Code:* `/validate-gaql`
    *   *Natural Language:*
        ```sql
        validate:
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.advertising_channel_type,
          ad_group.id,
          ad_group.name,
          ad_group.status,
          ad_group_ad.ad.id,
          ad_group_ad.status,
          ad_group_ad.ad.type,
          ad_group_ad.policy_summary.policy_topic_entries,
          metrics.clicks,
          metrics.impressions,
          metrics.cost_micros,
          metrics.conversions,
          segments.date
        FROM ad_group_ad
        WHERE campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND ad_group_ad.status = 'ENABLED'
          AND segments.date DURING LAST_30_DAYS
          AND metrics.impressions > 100
        ORDER BY metrics.clicks DESC
        LIMIT 500
        ```

*   **Direct API Execution:** Run generated Python code directly and see the results as tables.

*   **CSV Export:** Save API table results to a CSV file in the `saved/data/` directory.
    *   *"Save results to a csv file"*

*   **Conversion Troubleshooting & Diagnostics:** Create diagnostic reports to find offline conversion upload errors.
    *   *Claude Code:* `/troubleshoot-conversions`
    *   *Natural Language:* *"Troubleshoot my conversions for customer '123-456-7890'."* (Saves reports in `saved/data/`).


## Supported Languages

*   Python
*   PHP
*   Ruby
*   Java
*   C# (.NET)

The assistant can run Python, PHP, and Ruby code directly. Because of security rules, you must compile and run generated Java and C# code yourself. To generate C# code, include `'in dotnet'` in your prompt.

By default, the assistant uses Python to generate and run code, even if other language libraries or project files exist. The assistant uses another language only when you ask for it. Because the installation script installs the plugin globally, you can start `agy` or `claude` inside your own application directory so the assistant can read your project files.
   * Before you ask for code in another language, tell the assistant: `write saved code examples in <language of your application>`

## Prerequisites

1.  Basic knowledge of Google Ads API concepts and authentication.
2.  A credentials file in your home directory for Python (`google-ads.yaml`), PHP (`google_ads_php.ini`), or Ruby (`google_ads_config.rb`).
3.  An installed Antigravity or Claude Code CLI environment.
4.  A local clone of each client library that you want to use. Run `install.sh` (Linux/macOS) or `install.ps1` (Windows) to clone them automatically.
5.  Python >= 3.11 installed and on your system `PATH`.

## Setup

### 1. Install Host Platform

Set up your assistant CLI environment:

#### Antigravity CLI
* Download and install `antigravity-cli` from [https://antigravity.google/](https://antigravity.google/).
* Check your installation:
  ```bash
  agy --version
  ```

#### Claude Code
1. **Prerequisites:** Make sure [Node.js](https://nodejs.org/) (version 18 or later) is installed:
   ```bash
   node --version
   ```
2. **Install Claude Code CLI:** Install Claude Code globally with `npm`:
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
   *(Or on macOS with Homebrew: `brew install claude-code`)*
3. **Authenticate:** Run `claude` in your terminal to sign in to your Anthropic account or set your API key:
   ```bash
   claude
   ```
4. **Check Installation:** Verify that the CLI is available:
   ```bash
   claude --version
   ```

---

### 2. Clone the Assistant
Clone the repository to your computer:
```bash
git clone https://github.com/googleads/google-ads-api-developer-assistant
cd google-ads-api-developer-assistant
```

---

### 3. Run Install Script
Run the installation script for your platform:

*   **Antigravity (Linux/macOS):**
    ```bash
    ./install.sh agy
    ```
    *Installs the plugin globally in `~/.gemini/config/plugins/google-ads-api-developer-assistant`.*
    *To add more client libraries: `./install.sh agy --php --ruby --dotnet`.*

*   **Claude Code (Linux/macOS):**
    ```bash
    ./install.sh claude
    ```
    *Registers the repository as a local marketplace and installs the plugin in Claude Code.*
    *To add more client libraries: `./install.sh claude --php --ruby --dotnet`.*

*   **Antigravity (Windows - PowerShell):**
    ```powershell
    .\install.ps1 -Type agy
    ```
    *Installs the plugin globally in `%USERPROFILE%\.gemini\config\plugins\google-ads-api-developer-assistant`.*
    *To add more client libraries: `.\install.ps1 -Type agy -Php -Ruby -Dotnet`.*

*   **Claude Code (Windows - PowerShell):**
    ```powershell
    .\install.ps1 -Type claude
    ```
    *Registers the local marketplace and installs the plugin in Claude Code.*
    *To add more client libraries: `.\install.ps1 -Type claude -Php -Ruby -Dotnet`.*

---

### 4. Configure Credentials
Put your Google Ads API credentials file in your `$HOME` directory (`~/google-ads.yaml` for Python, `~/google_ads_php.ini` for PHP, `~/google_ads_config.rb` for Ruby, or `~/ads.properties` for Java). At session startup, [`config/config_init.py`](config/config_init.py) copies your credentials to `config/google-ads.yaml` (`0600` permissions) and sets `GOOGLE_ADS_CONFIGURATION_FILE_PATH`.

---

### 5. Configure Assistant Settings (`config/assistant_config`) & Enable/Disable Plugin
The [`config/assistant_config`](config/assistant_config) file (mirrored in [`plugins/google-ads-api-developer-assistant/config/assistant_config`](plugins/google-ads-api-developer-assistant/config/assistant_config)) stores all assistant settings in TOML format:

```toml
api_version = "<api_version> (e.g., vXX)"
customer_id = "12345678"
execute_mutates = false
enabled = true
```

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`api_version`** | `string` | `"<api_version>"` (e.g., `vXX`) | Active Google Ads API version for GAQL validation, Protobuf inspection, and code generation. Updated automatically when you run `install.sh`, `update.sh`, `sync_client_libs.py`, `get_latest_api_version.py`, or `python3 config/config_init.py --key api_version`. |
| **`customer_id`** | `string` | `"12345678"` | Default 10-digit Google Ads Customer ID (without dashes) used when your prompt does not include a CID (for example, *"Get my campaigns"*). |
| **`execute_mutates`** | `boolean` | `false` | Controls if the 4-Step HITL protocol allows live Google Ads API `create` and `update` mutations (`--execute` / `validate_only=False`). Delete (`remove`) operations are always blocked. |
| **`enabled`** | `boolean` | `true` | Controls if the plugin is active when you start `jetski`/`agy` or Claude Code. When set to `false` (with `./plugin.sh disable`), the host does not load the plugin on new sessions and its hooks do nothing. |

#### Turn the Plugin Off or On (`--enable` & `--disable`)

##### When to Use `--disable` and `--enable`
Because the installer puts the plugin in your global config directory (`~/.gemini/config/plugins/google-ads-api-developer-assistant` for Antigravity and `~/.claude/plugins/...` for Claude Code), the host CLI loads it in **every workspace** by default. When the plugin is on:
1. **Session Startup (`PreInvocation` Hook):** Your first prompt in each session syncs credentials, checks `pypi.org` and GitHub releases, and shows the **Google Ads API Version & Parity Verification Report** table.
2. **Context Window & Rules:** The host loads `rules/google_ads_rules.md`, 11 domain skills (`skills/`), and slash commands (`commands/`) into the context window.
3. **Command Interception (`PreToolUse` Hook) & Background Sidecar:** `config_init.py` checks every terminal command (to set `PYTHONPATH` and apply the 4-Step HITL Mutation Guard), and the host starts the A2A sidecar / MCP server (`sidecar.json` / `mcp_config.json`).

When you work on **non-Google Ads repositories**, run `--disable` (`disable`) to turn the plugin off **without uninstalling it** or deleting your `client_libs/` and `config/assistant_config` files. When you return to Google Ads API work, run `--enable` (`enable`) to turn the plugin back on.

##### What `--disable` and `--enable` Do
Passing `--disable` or `--enable` (to `plugin.sh`, `plugin.ps1`, `update.sh`, `update.ps1`, `install.sh`, `install.ps1`, or `config_init.py`) updates three layers so that both **running sessions** and **new sessions** use the new state:

| Layer | What `--disable` (`disable`) Does | What `--enable` (`enable`) Does |
| :--- | :--- | :--- |
| **1. Configuration (`config/assistant_config`)** | Sets `enabled = false` in `config/assistant_config` and keeps your `api_version`, `customer_id`, and `execute_mutates` values. | Sets `enabled = true` in `config/assistant_config` and keeps all other settings. |
| **2. Lifecycle Hooks (`config/config_init.py` & `hooks.json`)** | Sets `"enabled": false` in the installed `hooks.json` and causes `handle_hook()` in `config_init.py` to exit immediately:<br>• **`PreInvocation` / `SessionStart`:** Returns `{}` (skips credential sync, PyPI/GitHub checks, and the version table).<br>• **`PreToolUse`:** Returns `{"decision": "allow"}` without changing `PYTHONPATH` or running the mutation guard. | Sets `"enabled": true` in `hooks.json` and restores `PreInvocation` startup sync, version table output, `PYTHONPATH` setup, and `PreToolUse` mutation guard checks. |
| **3. Installed Plugin, MCP & Sidecar Manifests (`~/.gemini/...` & `~/.claude/...`)** | In installed plugin directories (never in the git repository), renames:<br>• `plugin.json` $\rightarrow$ `plugin.json.disabled`<br>• `.claude-plugin/plugin.json` $\rightarrow$ `.claude-plugin/plugin.json.disabled`<br>• `mcp_config.json` $\rightarrow$ `mcp_config.json.disabled`<br>• `sidecars/google-ads-a2a-service/sidecar.json` $\rightarrow$ `sidecar.json.disabled`<br>This stops `jetski`/`agy` and `claude` from loading the plugin rules, skills, MCP servers, or sidecar daemon on new sessions. | Renames all `.disabled` manifest files back to `plugin.json`, `.claude-plugin/plugin.json`, `mcp_config.json`, and `sidecar.json` so the host CLI loads the plugin on the next session. |

> **Tip — Single-Session Environment Override:** Set `GOOGLE_ADS_ASSISTANT_ENABLED=false` (or `true`) in your shell environment before you start `agy` or `claude` to turn the plugin hooks off or on for one terminal session without changing files on disk.

##### Commands to Enable, Disable, and Check Status (`plugin.sh` & `plugin.ps1`)
Run [`plugin.sh`](plugin.sh) (Linux/macOS) or [`plugin.ps1`](plugin.ps1) (Windows PowerShell) from the repository root or from **any directory** through your installed plugin path:

* **Linux/macOS (from repository root):**
  ```bash
  # Turn off the plugin
  ./plugin.sh disable

  # Turn on the plugin
  ./plugin.sh enable

  # Show the current plugin status and hook state (or pass --json)
  ./plugin.sh status

  # Run a self-test of the config, manifest, and hook state
  ./plugin.sh test

  # Check status in shell scripts (prints 'enabled' with exit 0, or 'disabled' with exit 1)
  ./plugin.sh is-enabled
  ```

* **Linux/macOS (from any directory):**
  ```bash
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh disable
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh enable
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh status
  ```

* **Windows PowerShell (from repository root):**
  ```powershell
  .\plugin.ps1 disable
  .\plugin.ps1 enable
  .\plugin.ps1 status
  .\plugin.ps1 test
  .\plugin.ps1 is-enabled
  ```

* **Windows PowerShell (from any directory):**
  ```powershell
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" disable
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" enable
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" status
  ```

You can also set options during installation (`./install.sh agy --cid 1234567890` or `./install.sh agy --disable`), edit `config/assistant_config` directly, or run `config_init.py`:
```bash
# Set default Customer ID in config/assistant_config and sync config/google-ads.yaml (from repo root)
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key customer_id --value 1234567890

# Or use the installed Antigravity plugin path:
python3 ~/.gemini/config/plugins/google-ads-api-developer-assistant/config/config_init.py --key customer_id --value 1234567890

# Find the latest API version across client_libs and site-packages and update config/assistant_config
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key api_version

# Set a specific API version in config/assistant_config (e.g., vXX)
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key api_version --value <api_version>

# Sync client_libs and api_version from the CLI
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --sync-client-libs

# Enable or disable live mutations in config/assistant_config
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates true
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates false

# Enable, disable, or check plugin status with config_init.py
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --disable
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --enable
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --status
```


## Usage

1.  **Start an Assistant Session:**
    Open Antigravity or Claude Code to ask questions, generate code, and validate queries.

2.  **Ask a Question:**
    > "What are the resource names for my enabled campaigns sorted by campaign id"

3.  **Generate Code:**
    > "Get me the top 5 campaigns by cost last month for customer 1234567890"

4.  **Run Code and Save Output:**
    > "Run the code"
    > ... (shows the output from the previous request) ...
    > "Save the results to csv"

## Stay in sync

The assistant includes sync tools to keep your runtime credentials, `config/assistant_config`, local client libraries (`client_libs/`), Protobuf definitions, and system `google-ads` package up to date.

### 1. What Syncs at Session Startup (`config/config_init.py`)

When you enter your first prompt in Antigravity (`agy`) or Claude Code (`claude`), the `PreInvocation` hook in [`hooks.json`](plugins/google-ads-api-developer-assistant/hooks.json) runs `python3 config/config_init.py --hook`. This command syncs your credentials and runs a 5-step version check:

| Startup Step | Execution Mode | What Happens | What Changes |
| :--- | :--- | :--- | :--- |
| **Credential Sync & `api_version` Lookup** (`sync_and_set_config_kv` & `detect_latest_api_version`) | **Automatic** (Every session start) | Reads your `$HOME` config (`~/google-ads.yaml`, `~/google_ads_php.ini`, `~/google_ads_config.rb`, `~/ads.properties`, or `.NET` `App.config` / `appsettings.json`), writes `config/google-ads.yaml` (`0600` permissions) with `use_proto_plus: True` and `ads_assistant: <version>`, exports `GOOGLE_ADS_CONFIGURATION_FILE_PATH`, checks `v<N>` directories in `client_libs/google-ads-python` and `google.ads.googleads.__path__`, and updates `api_version` in `config/assistant_config` when a newer version is installed. | `config/google-ads.yaml` and `config/assistant_config` (Never changes your `$HOME` config) |
| **Step 1 — Check Python Site-Directory Version Against PyPI** (`detect_system_package_version` / `fetch_latest_pypi_python_version`) | **Automatic** (Read-only check) | Checks `google-ads` in `site.getsitepackages()` (`importlib.metadata.version("google-ads")`) and queries `pypi.org` (`https://pypi.org/pypi/google-ads/json`) for the latest release. | None (Read-only check) |
| **Step 2 — Check Latest GitHub Release** (`fetch_latest_github_python_version` / `fetch_github_latest_release`) | **Automatic** (Read-only check, 1-hour cache) | Queries the GitHub Releases API (`googleads/google-ads-python/releases/latest`, cached in `$TMPDIR/gads_assistant_github_release.json` for 1 hour) to find the latest client library release. | `$TMPDIR/gads_assistant_github_release.json` |
| **Step 3 — Select Active API Version & Show Table** (`determine_api_version` & `format_parity_table_markdown`) | **Automatic** (First-prompt display) | Selects the active Google Ads API version from steps 1 and 2, adds the comparison table to the assistant context, and shows the table at the top of the first response. | None (Session display) |
| **Step 4 — Ask User If Any Version Is Outdated** (`handle_hook` $\rightarrow$ `PreInvocation`) | **Interactive Prompt** (When any version `<` upstream) | If the version in your Python site directory or `client_libs/` is older than `pypi.org` or GitHub, the assistant asks if you want to update before continuing. | None (Waits for your `yes` or `no` reply) |
| **Step 5 — Upgrade on Confirmation or Keep Current Versions** (`sync_client_libs.py --upgrade_system` / `--check_only`) | **On Confirmation (`Yes`) or Decline (`No`)** | If **Yes**: installs the latest `google-ads` from `pypi.org`, updates `client_libs/google-ads-python`, and updates `api_version` in `config/assistant_config`. If **No**: keeps the installed versions. | Python `site-packages`, `client_libs/`, and `config/assistant_config` (only if you reply `Yes`) |

> **Run the sync directly from your terminal:**
> ```bash
> # Check installed site-packages and client_libs versions against GitHub
> python3 plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py --check_only
>
> # Upgrade site-packages from pypi.org, update client_libs, and refresh api_version
> python3 plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system
> ```

### 2. Sync Client Libraries During a Session
Use these prompts or commands to check for updates during an active session:

* **Natural Language Prompts (Antigravity & Claude Code):**
  * *"Sync my client libraries"*
  * *"Check for Google Ads client library updates"*
  * *"Update the Python client library to the latest release"*

* **Slash Command (Claude Code):**
  * Run `/sync-client-libs` to check and update all local client libraries.
  * Update one library: `/sync-client-libs python` or `/sync-client-libs dotnet`.

* **Check the Active Version:**
  * Claude Code: `/ext-version`
  * Natural Language: *"What is the active Google Ads API version?"*

### 3. Manual Terminal Updates
Run `update.sh` or `update.ps1` from the repository root or from **any directory** through your installed plugin directory:
* **Linux/macOS (from repository root):**
  ```bash
  ./update.sh agy --all          # Update Antigravity plugin and all client libraries
  ./update.sh claude --all       # Update Claude Code plugin and all client libraries
  ```
* **Linux/macOS (from any directory):**
  ```bash
  # Update plugin and all client libraries
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --all
  ~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/update.sh claude --all

  # Disable or enable the plugin from any directory (with update.sh or plugin.sh)
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --disable
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --enable
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh disable
  ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh enable
  ```
* **Windows PowerShell (from repository root):**
  ```powershell
  .\update.ps1 -Type agy -All
  .\update.ps1 -Type claude -All
  ```
* **Windows PowerShell (from any directory):**
  ```powershell
  # Update plugin and all client libraries
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -All
  & "$HOME\.claude\plugins\google-ads-assistant-local\plugins\google-ads-api-developer-assistant\update.ps1" -Type claude -All

  # Disable or enable the plugin from any directory (with update.ps1 or plugin.ps1)
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -Disable
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -Enable
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" disable
  & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" enable
  ```

### 4. Client Library & Runtime Version Parity
The assistant reads local client library files (`client_libs/google-ads-python`) as the **source of truth** for Protobuf schemas, resource definitions, and enum descriptors. It runs queries and generated code with the installed `google-ads` Python package in your environment.

To prevent schema mismatches or missing fields:
* **Automatic Parity Checks:** Tool scripts (`inspect_object.py` and `sync_client_libs.py`) compare the installed package version (`importlib.metadata.version('google-ads')`) against `client_libs/google-ads-python` (`pyproject.toml` / `ChangeLog`) and GitHub releases.
* **System Site-Directory Upgrades:** When a newer release of `google-ads` is available, the sync tool checks `site.getsitepackages()`. If the versions do not match, the assistant shows a warning and asks if you want to upgrade. If you confirm, it runs `pip install --upgrade google-ads` (or `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system`).
* **Warning Banner:** If the versions do not match, the tools print this warning:
  ```text
  WARNING: Installed google-ads package version (<installed_version>) does not match client_libs/google-ads-python version (<client_libs_version>) used for protobuf inspection. Schema inspection or API calls may encounter field discrepancies.
  ```
* **How to Fix a Mismatch:**
  * Sync client libraries: `/sync-client-libs` (or enter *"Sync client libraries"*).
  * Upgrade the Python package: `pip install --upgrade google-ads` (or run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system`).
  * Run a full update: `./update.sh agy --all` or `./update.sh claude --all`.


## Directory Structure

*   `plugins/google-ads-api-developer-assistant/`: Source directory for the assistant plugin.
*   `plugins/google-ads-api-developer-assistant/commands/`: Slash commands for Claude Code.
*   `plugins/google-ads-api-developer-assistant/skills/`: Assistant skills (GAQL validator, proto inspector, HITL mutation runner, and others).
*   `plugins/google-ads-api-developer-assistant/rules/`: Agent rules and safety protocols.
*   `plugins/google-ads-api-developer-assistant/sidecars/`: Background sidecar services.
*   `plugins/google-ads-api-developer-assistant/client_libs/`: Cloned client libraries.
*   `plugins/google-ads-api-developer-assistant/config/`: Plugin configuration files (`assistant_config` and `config_init.py`).
*   `plugins/google-ads-api-developer-assistant/mcp_config.json`: Model Context Protocol configuration.
*   `config/`: Workspace configuration directory:
    *   `config/assistant_config`: Unified TOML file that stores `api_version`, `customer_id`, `execute_mutates`, and `enabled`.
    *   `config/config_init.py`: Session initializer and `PreInvocation` / `PreToolUse` hook handler.
    *   `config/google-ads.yaml`: Runtime Google Ads API credentials file (`0600` permissions).
*   `saved/`: Working directory for saved files and scripts:
    *   `saved/` (or `saved/code/`): Executable Python scripts saved for later use.
    *   `saved/data/`: GAQL validation cache, CSV exports, diagnostic reports, and mutation dry-run receipts.
    *   `saved/logs/`: Append-only audit logs (`mutation_audit.jsonl`).

## Plugin Architecture

For details on how Antigravity and Claude define plugins, see the [Antigravity plugin specification](https://antigravity.google/docs/cli/plugins/) and the [Claude plugin specification](https://github.com/anthropics/knowledge-work-plugins).

## Sidecar Daemon & How It Functions

### What Is a Sidecar?

A **sidecar** is a separate helper process that runs next to a main application on the same computer. It shares the local network (`127.0.0.1`), local files, and session lifecycle with the main application.

In CLI agent environments such as **Antigravity (`agy`)** and **Claude Code CLI**, tools run in two ways:
*   **Skill Scripts & Hooks (One-Time Subprocesses)**: When the agent runs a skill script (in `skills/`) or a hook (`config_init.py`), the host starts a new OS process for that command, reads the output, and stops the process.
*   **Sidecar Daemons (Background Services)**: The host CLI starts a sidecar server in the background when the plugin loads and keeps it running during the session.

A sidecar daemon gives you three benefits:
1.  **Low Latency**: The Python interpreter and libraries stay in memory, so requests do not wait for process startup.
2.  **Structured HTTP & MCP Requests**: The sidecar listens on a local port (`127.0.0.1`) and accepts typed JSON requests over HTTP or Model Context Protocol (MCP).
3.  **Automatic Lifecycle Control**: The host CLI starts, monitors, restarts, and stops the sidecar automatically using `sidecar.json` or `mcp_config.json`.

### How the Sidecar Is Configured in This Repository

The sidecar is the **Google Ads Agent-to-Agent (A2A) Service** in `plugins/google-ads-api-developer-assistant/sidecars/google-ads-a2a-service/`:
*   **`sidecar.json`**: The sidecar manifest read by Antigravity (`command: "python3"`, `args: ["server.py"]`, `restart_policy: "always"`).
*   **`mcp_config.json`**: The MCP server configuration that registers `google-ads-api-assistant` at `http://127.0.0.1:8900`.
*   **`server.py`**: The Python HTTP server (`A2AHandler` / `HTTPServer`) that handles health checks and task requests.

### How the Host Manages the Sidecar Lifecycle

1.  **Automatic Startup**: When `enabled = true` in `config/assistant_config`, the host reads `sidecar.json` and starts `python3 server.py` in the background.
2.  **Port Assignment**: The server listens on `127.0.0.1` using the port in `ANTIGRAVITY_SIDECAR_WEB_PORT`, or uses `A2A_PORT` (default `8900`).
3.  **Automatic Restart**: Because `sidecar.json` sets `"restart_policy": "always"`, the host restarts the process if it stops unexpectedly.
4.  **Stop the Sidecar**: Running `./plugin.sh disable` (or `./update.sh --disable`) renames `sidecar.json` to `sidecar.json.disabled` and `mcp_config.json` to `mcp_config.json.disabled`. The host detects this change and stops the background server immediately.

### How the Sidecar Functions Within the Assistant

When `server.py` runs, it does three tasks:

#### 1. Startup Credential & Configuration Sync
At startup (and before each task), `server.py` calls `config/config_init.py` (`sync_and_set_config_kv()`) to:
*   Copy credentials from `~/google-ads.yaml` to `config/google-ads.yaml` with `0600` permissions.
*   Read `customer_id`, `api_version`, and `execute_mutates` from `config/assistant_config`.

#### 2. Dynamic API Version Selection
For each task request, `get_effective_api_version()` selects the target Google Ads API version in this priority order:
1.  An `api_version` field in the request payload or the `GOOGLE_ADS_API_VERSION` environment variable.
2.  The `api_version` value in `config/assistant_config`.
3.  The highest `v<N>` directory in `client_libs/google-ads-python/google/ads/googleads/`.
4.  The highest `v<N>` package in the installed `google.ads.googleads` Python module.
5.  If it cannot find an API version, the server returns `API_VERSION_CONFIRMATION_REQUIRED` and asks the caller to set a version.

#### 3. HTTP & Agent-to-Agent (A2A) Task Endpoints
The sidecar exposes two HTTP endpoints on `http://127.0.0.1:8900`:

*   **`GET /` or `GET /health`**: Returns a JSON health status object with the service name, plugin version (`plugin.json`), and port:
    ```json
    {
      "status": "HEALTHY",
      "service": "google-ads-a2a-sidecar",
      "version": "4.1.0",
      "port": 8900
    }
    ```
*   **`POST /v1/a2a/tasks`**: Accepts a JSON task payload (`{"task_id": "...", "intent": "...", "payload": {...}}`) and runs one of these intents:

| Intent | Function |
| :--- | :--- |
| **`GAQL_VALIDATE`** | Runs static analysis checks on a GAQL query. It blocks `OR` operators, rejects `FROM` clauses in `GoogleAdsFieldService` metadata queries, and warns about `segments.hour` in `v23+`. |
| **`INSPECT_OBJECT`** | Returns Protobuf resource metadata and selectable fields for a `resource` and `api_version`. |
| **`GENERATE_CODE`** | Generates `ruff`-checked Python code that calls `GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version=...)` and catches `GoogleAdsException`. |
| **`TROUBLESHOOT_CONVERSIONS`** | Runs offline conversion upload checks (`offline_conversion_upload_client_summary` and `conversion_time > click_time` validation) for a `customer_id`. |
| **`PREPARE_MUTATION`** | Runs Steps 2 and 3 of the 4-Step HITL Mutation Protocol with `skills/execute-mutation/scripts/run_mutation.py`: writes a SHA-256 `validate_only=True` dry-run receipt to `saved/data/last_dry_run.json`, writes `DRY_RUN_VERIFIED` to `saved/logs/mutation_audit.jsonl`, and returns the **Mutation & Consequence Verification Card** (`status: "HITL_CONFIRMATION_REQUIRED"`). |
| **`EXECUTE_MUTATION`** | Enforces Step 4 of the HITL Mutation Protocol: checks `user_confirmed=True`, a non-empty `confirmation_summary`, `execute_mutates = true` in `config/assistant_config`, and a valid matching SHA-256 receipt in `saved/data/last_dry_run.json` before marking the receipt `EXECUTED` and logging the execution in `saved/logs/mutation_audit.jsonl`. |

### Run or Test the Sidecar Manually

Start the sidecar from the repository or check its health endpoint from a terminal:

```bash
# Start the sidecar server in the foreground (default port 8900)
python3 plugins/google-ads-api-developer-assistant/sidecars/google-ads-a2a-service/server.py

# Check the health endpoint in another terminal
curl http://127.0.0.1:8900/health
```

## How Mutates Work

When you ask the assistant to run a write or mutation operation (such as creating a campaign, ad group, or ad, updating a campaign budget, pausing an ad group, applying a recommendation, or uploading conversions), the plugin enforces a **4-Step Human-in-the-Loop (HITL) Verification Protocol** (`skills/execute-mutation/`) with `PreToolUse` hooks (`config/config_init.py`) and pre-RPC SHA-256 checks.

> **Create & Update Only (Deletion Prohibited):** You can run only **`create`** and **`update`** mutations. The `PreToolUse` hook, `run_mutation.py`, and the A2A sidecar block any delete operation (`remove` / `remove_all` operations, `remove_*` RPC calls, or setting `status = REMOVED`) with `BLOCKED_PROHIBITED_DELETION`. To stop ad serving without deleting a resource, update its `status` to `PAUSED`.

---

### 1. Configure the Mutate Switch (`execute_mutates` in `config/assistant_config`)

By default, live mutations are **off** (`execute_mutates = false` in `config/assistant_config`). In this state, the assistant can run read-only GAQL queries and `validate_only=True` dry-runs (`--dry-run`), but it blocks any live write (`--execute` or `validate_only=False`).

#### How to Enable or Disable Live Mutations
Use either of these methods:

1. **Edit `config/assistant_config` (TOML) directly:**
   Open `config/assistant_config` and set `execute_mutates` to `true` or `false`:
   ```toml
   api_version = "<api_version> (e.g., vXX)"
   customer_id = "12345678"
   execute_mutates = false
   ```
   ```toml
   api_version = "<api_version> (e.g., vXX)"
   customer_id = "12345678"
   execute_mutates = true
   ```
2. **Use the `config_init.py` CLI flag:**
   ```bash
   # Enable live mutations in config/assistant_config (from repo root)
   python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates true

   # Disable live mutations (default)
   python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates false
   ```

**Configuration File Priority:**
When checking a mutation, the plugin checks these paths in order and uses the **first file that exists**:
1. `config/assistant_config` (workspace `config/` directory) — **first priority**
2. `plugins/google-ads-api-developer-assistant/config/assistant_config` (plugin source directory)
3. `~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config` (installed global plugin directory)

*(If `execute_mutates = false` and a command tries to run a live mutation, the `PreToolUse` hook and `run_mutation.py` block it with: `BLOCKED BY HITL MUTATION GUARD: Mutate support is disabled by configuration (execute_mutates = false in config/assistant_config). Set 'execute_mutates = true' in config/assistant_config to enable live Google Ads API mutations.`)*

---

#### Financial Transaction Upper Limits (`config/financial_limits` & `set_financial_limits.py`)
In addition to `execute_mutates`, you can set upper limits for financial Google Ads API mutate fields in [`config/financial_limits`](plugins/google-ads-api-developer-assistant/config/financial_limits) using `Service.field` keys (for example, `CampaignBudgetService.amount_micros`, `AssetService.amount_micros`, `AdGroupService.cpc_bid_micros`, and `AdGroupCriterionService.cpc_bid_micros`).

* **API Format & Units:** Write each `Service.field` value in `config/financial_limits` in the exact numeric format that the Google Ads API field uses:
  * **`micros` (`int64` integer):** `1,000,000` micros = `1.00` unit of the account's local currency (for example, `50000000` = `50.00` currency units). Used for budgets (`CampaignBudgetService.amount_micros`, `CampaignBudgetService.total_amount_micros`, `RecommendationService.new_budget_amount_micros`), bids (`AdGroupService.cpc_bid_micros`, `AdGroupCriterionService.cpc_bid_micros`, `BiddingStrategyService.target_cpa_micros`), promotions and prices (`AssetService.amount_micros`), and user transactions (`UserDataService.transaction_amount_micros`).
  * **`currency_units` (`double` / `float`):** Standard decimal units of the account's currency (not micros; for example, `500.0` = `500.00` currency units). Used for conversion uploads (`ConversionUploadService.conversion_value`, `ConversionUploadService.unit_price`), adjustments (`ConversionAdjustmentUploadService.adjusted_value`), value rules (`ConversionValueRuleService.value`), and goals (`GoalService.additional_value`, `CampaignGoalConfigService.additional_value`).
  * **`decimal_ratio` (`double` / `float`):** Decimal multiplier or ROAS ratio (not micros; for example, `5.0` = `500%` Target ROAS, `2.0` = `+100%` bid modifier). Used for `BiddingStrategyService.target_roas`, `CampaignService.target_roas`, `AdGroupBidModifierService.bid_modifier`, `BiddingSeasonalityAdjustmentService.conversion_rate_modifier`, and `GoalService.value_multiplier`.
  * **`micros_proportion` (`int64` integer):** Proportion in micros (`1,000,000` = `100%`; for example, `150000` = `15%`). Used for `AdGroupService.percent_cpc_bid_micros`, `CampaignService.commission_rate_micros`, and `BiddingStrategyService.location_fraction_micros`.
* **Default (`0` / `0.0` = Not Modifiable):** By default, each `Service.field` value is `0` (for `int64` fields) or `0.0` (for `double` fields). A value of `0` or `0.0` means that the field **cannot be changed**. Set a value **greater than zero (`> 0`)** to allow changes up to that **upper limit**.
* **Enforcement at HITL & RPC Execution:** `run_mutation.py` (`--dry-run` and `--execute`), the `PreToolUse` hook (`config/config_init.py`), and the A2A sidecar (`server.py`) check both the Protobuf `Mutate*Request` payload and the mutation script against `config/financial_limits`. If a mutation tries to change a `0` / `0.0` field or exceeds its upper limit (`> 0`), the plugin blocks the call at the HITL step (`[HITL BLOCKED - FINANCIAL UPPER LIMIT EXCEEDED]`), writes `BLOCKED_FINANCIAL_LIMIT_EXCEEDED` to `saved/logs/mutation_audit.jsonl`, and does not run the command.

Use [`set_financial_limits.py`](set_financial_limits.py) (at `./set_financial_limits.py`, `config/set_financial_limits.py`, and `skills/execute-mutation/scripts/set_financial_limits.py`) to list, set (`> 0`), or reset (`0` / `0.0`) limits by `Service.field`, wildcard `*.field`, or flag:

```bash
# List all Service.field financial limits, units, and current upper limits
./set_financial_limits.py --list

# Set a value > 0 to allow changes to specific Service.field entries up to that limit
./set_financial_limits.py \
  --set CampaignBudgetService.amount_micros=50000000 \
  --set AssetService.amount_micros=20000000 \
  --set AdGroupService.cpc_bid_micros=5000000 \
  --set AdGroupCriterionService.cpc_bid_micros=2000000 \
  --set ConversionUploadService.conversion_value=500.0 \
  --set BiddingStrategyService.target_roas=10.0

# Set a field across all services with a wildcard (*.field) or shorthand flag
./set_financial_limits.py --set "*.cpc_bid_micros=5000000"
./set_financial_limits.py --type CampaignBudgetService.total_amount_micros --amount 5000000000
./set_financial_limits.py --campaign-budget-amount-micros 50000000 --target-cpa-micros 25000000

# Run from any directory through the installed plugin
python3 ~/.gemini/config/plugins/google-ads-api-developer-assistant/set_financial_limits.py --list

# Reset one limit or all limits to 0 / 0.0 (not modifiable)
./set_financial_limits.py --reset CampaignBudgetService.amount_micros
./set_financial_limits.py --reset-all
```

---

### 2. The 4-Step HITL Mutation Workflow & What You See on Screen

Every mutation request follows 4 steps so you can check the current state, the API dry-run result, the SHA-256 request hash, and the financial or serving effects before any live change runs.

#### Step 1 — Pre-Mutation State & Blast Radius Lookup (Mandatory GAQL Read)
Before the assistant generates or runs mutation code, it queries your account with `GoogleAdsService.search_stream` to get the **Before State** and **Blast Radius**:
* Resource names (for example, `customers/1234567890/campaignBudgets/98765`).
* Current `status` (`ENABLED`, `PAUSED`, `REMOVED`).
* Current budget or bid amounts (`amount_micros`, `cpc_bid_micros`) converted to standard currency (`micros / 1,000,000`).
* Count of active child entities affected (such as active `ad_group` and `ad_group_ad` counts, or shared campaigns).

#### Step 2 — Mandatory `validate_only=True` Dry-Run & Signed Receipt
The assistant writes a Python script in `saved/code/` that supports `--dry-run` (`validate_only=True`, default) and `--execute` (`validate_only=False`), checks it with `ruff`, and runs the dry-run through `run_mutation.py`:
```bash
python3 skills/execute-mutation/scripts/run_mutation.py \
  --script saved/code/update_campaign_budget.py \
  --dry-run \
  --customer-id "1234567890" \
  --operation "Update CampaignBudget (customers/1234567890/campaignBudgets/98765)" \
  --before "$50.00/day (50,000,000 micros), Status: ENABLED" \
  --after "$250.00/day (250,000,000 micros), Status: ENABLED" \
  --consequences "Daily budget cap increases by +$200.00/day (+400%); Max monthly spend exposure increases to ~$7,600.00/mo" \
  --reversibility "REVERSIBLE"
```
* The Google Ads API checks all schema rules, resource IDs, and policy rules with `validate_only=True` **without** changing your account.
* If validation passes, `run_mutation.py` calculates the script SHA-256 (`script_sha256`) and the normalized Protobuf request SHA-256 (`request_sha256`), and writes a receipt to `saved/data/last_dry_run.json` (valid for 30 minutes).

#### Step 3 — On-Screen Verification Card & Consequence Disclosure
After `--dry-run` passes, `run_mutation.py` prints the **Mutation & Consequence Verification Card** to your screen:

```text
======================================================================
GOOGLE ADS API MUTATION & CONSEQUENCE VERIFICATION CARD
======================================================================
Customer ID   : 1234567890
Operation     : Update CampaignBudget (customers/1234567890/campaignBudgets/98765)
Mutates Config: ENABLED (execute_mutates = true)
Dry-Run Status: PASSED (validate_only=True verified at 2026-10-12T15:30:00+00:00)
Request SHA256: 8f4e2b9a1c3d5e7f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f
Before State  : $50.00/day (50,000,000 micros), Status: ENABLED
After State   : $250.00/day (250,000,000 micros), Status: ENABLED
Reversibility : REVERSIBLE
Consequences  :
  - Daily budget cap increases by +$200.00/day (+400%)
  - Max monthly spend exposure increases to ~$7,600.00/mo
======================================================================
NEXT STEP: Present this card to the user and obtain explicit confirmation
before running with --execute.
======================================================================
```

The assistant explains the effects of the change and **waits for your confirmation**:
* **Budgets & Bidding:** Shows the currency change (`$X.XX/day` $\rightarrow$ `$Y.YY/day`, `%` change), maximum monthly spend (`daily_budget * 30.4`), and Smart Bidding learning-phase warnings for changes $>20\%$.
* **Status Changes (`PAUSED` $\leftrightarrow$ `ENABLED`):** Shows the number of active Ad Groups and Ads that will stop or start serving.
* **Deletion / `REMOVE` Operations (Prohibited):** Blocks all delete operations (`remove` / `remove_all` operations, `remove_*` RPCs, or `status = REMOVED`) with `BLOCKED_PROHIBITED_DELETION`. Only `create` and `update` mutations are allowed (set `status = PAUSED` to stop serving).
* **Targeting & Conversion Goals:** Shows warnings about traffic changes or automated bidding signals.

#### Step 4 — Hook-Gated CLI Confirmation & Live Execution (`--execute`)
After you confirm in chat and `execute_mutates = true` is set in `config/assistant_config`, the assistant runs:
```bash
python3 skills/execute-mutation/scripts/run_mutation.py \
  --script saved/code/update_campaign_budget.py \
  --execute
```

1. **CLI Hook Confirmation Prompt (`PreToolUse`):**
   Before the command runs, the `PreToolUse` hook (`config/config_init.py`) checks `execute_mutates = true`, `script_sha256`, and `request_sha256` against `saved/data/last_dry_run.json`. It then forces an interactive CLI permission prompt (`"decision": "force_ask"` in **Antigravity (`agy`)** or `"permissionDecision": "ask"` in **Claude Code CLI**):
   ```text
   ⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION [Customer ID: 1234567890]
   • Operation: Update CampaignBudget (customers/1234567890/campaignBudgets/98765)
   • Change: $50.00/day (50,000,000 micros), Status: ENABLED -> $250.00/day (250,000,000 micros), Status: ENABLED
   • Request SHA256: 8f4e2b9a1c3d5e7f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f
   • Reversibility: REVERSIBLE
   • Consequences: Daily budget cap increases by +$200.00/day (+400%); Max monthly spend exposure increases to ~$7,600.00/mo
   Confirm execution of this live Google Ads API mutation?
   ```
2. **Pre-RPC SHA-256 Check:**
   When you approve the prompt, `run_mutation.py` intercepts `GoogleAdsClient.get_service` and calculates the SHA-256 hash of the outgoing `Mutate*Request` **before** it sends the gRPC call. If the request payload differs from the `validate_only=True` dry-run (except for `validate_only` changing from `True` to `False`), or if the script tries to send an extra mutation call, `run_mutation.py` blocks the RPC (`BLOCKED_SHA256_MISMATCH`).
3. **Live Result & One-Time Receipt Use:**
   The live mutation runs with `ResponseContentType.MUTABLE_RESOURCE` and prints the mutated resource names. `run_mutation.py` marks `saved/data/last_dry_run.json` as `"status": "EXECUTED"` so the receipt cannot be used a second time.
4. **Audit Log (`saved/logs/mutation_audit.jsonl`):**
   Both `--dry-run` and `--execute` write a JSONL audit record (`0600` permissions, with credentials removed) to `saved/logs/mutation_audit.jsonl` containing:
   * `actor`: OS user, hostname, `login_customer_id`, `target_customer_id`, auth type, and CLI conversation/transcript IDs.
   * `request`: `sent_at_iso`, `validate_only`, `script_sha256`, `request_sha256`, `request_sha256_verified`, and the Protobuf request payload.
   * `approval`: `dry_run_validated_at_iso`, `hook_prompted_at_iso`, `user_approved_at_iso`, `before_state`, `after_state`, `consequences`, and `reversibility`.
   * `response`: `received_at_iso`, `duration_ms`, `google_ads_request_ids`, and the Protobuf response or error payload.

---

### 3. Summary of Safeguards (`config/config_init.py` & `run_mutation.py`)

| Condition | Hook / Runner Decision | What Happens on Screen |
| :--- | :--- | :--- |
| Read-only query (`search`, `search_stream`) or `--dry-run` (`validate_only=True`) within configured limits | **`allow`** | Runs immediately and shows query results or the **Mutation & Consequence Verification Card**. |
| Delete / `remove` operation attempted (`remove` / `remove_all` operations, `remove_*` / `delete_*` RPCs, or `status = REMOVED`) | **`deny` / `BLOCKED_PROHIBITED_DELETION`** | Blocked across the `PreToolUse` hook, `run_mutation.py` (`--dry-run` and `--execute`), and A2A sidecar before any RPC runs; recommends `status = PAUSED` with an `update` operation and writes to `saved/logs/mutation_audit.jsonl`. |
| Financial transaction amount exceeds the upper limit in `config/financial_limits` (`> 0`) or modifies a `0` / `0.0` field | **`deny` / `BLOCKED_FINANCIAL_LIMIT_EXCEEDED`** | Blocked at the HITL step (`--dry-run`, `--execute`, `PreToolUse` hook, and sidecar); shows the limit and unit, writes to `saved/logs/mutation_audit.jsonl`, and does not run. |
| Live mutation attempted while `execute_mutates = false` (default) | **`deny` (Hard Block)** | Blocked before execution with instructions to set `execute_mutates = true` in `config/assistant_config`. |
| Live mutation attempted without a valid ($\le 30\text{ min}$) `DRY_RUN_PASSED` receipt | **`deny` (Hard Block)** | Blocked before execution with instructions to run `--dry-run` first. |
| Script file (`script_sha256`) or RPC request payload (`request_sha256`) changed after dry-run | **`deny` / `BLOCKED_SHA256_MISMATCH`** | Blocked before any live RPC is sent to Google Ads; writes mismatch to `saved/logs/mutation_audit.jsonl`. |
| Valid receipt + `execute_mutates = true` + matching SHA-256 hashes + within financial limits | **`force_ask` (Interactive CLI Prompt)** | Shows the `⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION` card in the CLI and waits for your approval. |

## Behavioral Differences in 4.1.0

When you upgrade from `4.0.0` to `4.1.0`, existing CLI arguments, A2A sidecar payloads, and old configuration files (`config/customer_id`, `config/customer_id.txt`, `config/api_version.txt`, and `~/google-ads.yaml`) continue to work and migrate automatically. Note these two changes:

1. **Default Output Path (`~/saved/...` $\rightarrow$ `./saved/...`):**
   * In `4.0.0`, skill scripts (`get_cids_under_mcc.py` and `troubleshoot_conversions.py`) wrote default output files to `~/saved/csv/` and `~/saved/logs/` in your home directory.
   * In `4.1.0`, scripts write default outputs to `saved/data/`, `saved/logs/`, and `saved/code/` in the current workspace (unless you pass `--output_dir`).
2. **Hook-Enforced Mutation Guard (`evaluate_mutation_guard` — `create` & `update` Only):**
   * In `4.0.0`, only prompt rules (`NO MUTATE`) restricted live mutations.
   * In `4.1.0`, the plugin allows only **`create`** and **`update`** mutations and blocks all delete (**`remove`**) operations (`BLOCKED_PROHIBITED_DELETION`). In addition, the `PreToolUse` hook in `config/config_init.py` (`handle_hook`) blocks (`deny`) any live `.mutate*()` command unless `execute_mutates = true` in `config/assistant_config` and a valid dry-run receipt (`saved/data/last_dry_run.json`) exists. Read-only queries and `validate_only=True` dry-runs (for `create` and `update` operations) continue to run normally.

## Performance & Functionality Benchmarks

The repository includes a benchmark suite (`tests/benchmark_suite.py`) that checks functional correctness and execution speed (`total_ms`, `mean_ms`, `p50_ms`, `p95_ms`, `ops/sec`) across 8 subsystems of the Google Ads API Developer Assistant. It compares results between **any two versions that you specify** (`<base_version>` and `<target_version>`). The benchmark runner does not use default fallback versions or hardcoded version numbers.

| Benchmark | Iterations | `<base_version>` (ms) | `<target_version>` (ms) | Budget (ms) | Delta | Speedup | Status |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| `version_resolution_in_process` | 1,000 | `119.87` | `0.57` | `50.0` | `-99.5%` | **211.41x** | `PASS` |
| `gaql_static_analysis` | 200 | `42.79` | `4.68` | `150.0` | `-89.1%` | **9.15x** | `PASS` |
| `protobuf_type_discovery_and_inspection` | 200 | `99.53` | `10.30` | `60.0` | `-89.7%` | **9.66x** | `PASS` |
| `client_libs_parallel_release_sync` | 5 | `632.77` | `145.02` | `400.0` | `-77.1%` | **4.36x** | `PASS` |
| `conversion_csv_validation` | 50 | `101.16` | `91.35` | `450.0` | `-9.7%` | **1.11x** | `PASS` |
| `config_sync_and_legacy_migration` | 50 | `N/A` | `99.31` | `350.0` | `NEW` | `N/A` | `PASS` |
| `hook_pre_tool_use_interception` | 500 | `N/A` | `49.63` | `250.0` | `NEW` | `N/A` | `PASS` |
| `hitl_mutation_receipt_and_sha256_normalization` | 100 | `N/A` | `82.47` | `450.0` | `NEW` | `N/A` | `PASS` |

### How to Run the Benchmarks

Specify the **two versions to compare** (`<base_version>` and `<target_version>`), or pass `--run-current` to test only the current working tree. If you run `python3 tests/benchmark_suite.py` with no arguments, the script exits with an error.

Each version argument (`<base_version>` or `<target_version>`) can be:
* **A Git ref** (a tag, branch, or commit SHA in the repository, such as `<tag_a>`, `<tag_b>`, `main`, `dev_next`, or `HEAD~1`),
* **A saved baseline name** in `tests/benchmarks/` (matching `tests/benchmarks/baseline_<version>.json`),
* **A baseline JSON file path** (for example, `path/to/baseline_a.json`), or
* **`workspace`** (or `current` / `.`) to test the current working tree.

#### 1. Compare Any Two Versions (`<base_version> <target_version>`)
Pass the two versions as positional arguments, with `--compare`, or with `--base-version` and `--target-version`:
```bash
# Positional: compare <base_version> against <target_version>
python3 tests/benchmark_suite.py <base_version> <target_version>

# Compare a Git ref or saved baseline against the current working tree
python3 tests/benchmark_suite.py <base_version> workspace

# Use --compare or --base-version / --target-version flags
python3 tests/benchmark_suite.py --compare <base_version> <target_version>
python3 tests/benchmark_suite.py --base-version <base_version> --target-version <target_version>
```

#### 2. Compare Two Saved Baseline JSON Files
```bash
python3 tests/benchmark_suite.py \
  tests/benchmarks/baseline_<base_version>.json \
  tests/benchmarks/baseline_<target_version>.json
```

#### 3. Compare Two Git Tags, Branches, or Commits Live
When you pass Git refs that do not have saved JSON files, the runner checks out each ref into a temporary Git worktree, runs the benchmarks on each ref, and compares them:
```bash
python3 tests/benchmark_suite.py <git_ref_1> <git_ref_2>
python3 tests/benchmark_suite.py main dev_next
```

#### 4. Run on the Current Working Tree Only (`--run-current`)
Run all benchmarks and check functional assertions and latency budgets on the current workspace without comparing two versions:
```bash
python3 tests/benchmark_suite.py --run-current
```

#### 5. Save or Update Version Baselines (`--save-baseline` & `--save-git-ref-baseline`)
Save baseline JSON files when you create a new release:
```bash
# Save the current workspace benchmark results to a JSON file
python3 tests/benchmark_suite.py --save-baseline tests/benchmarks/baseline_<version>.json

# Run benchmarks against a Git ref and save its baseline JSON file
python3 tests/benchmark_suite.py --save-git-ref-baseline <git_ref> tests/benchmarks/baseline_<git_ref>.json
```

#### 6. Set the Regression Threshold & JSON Output (`--max-regression-pct` & `--json`)
By default, the runner flags a regression if a benchmark exceeds its latency budget (`max_total_ms`) or slows down by more than `50%` (with at least a `+5.0 ms` increase) compared to `<base_version>`. Use `--max-regression-pct` to change this threshold, or pass `--json` for CI pipelines:
```bash
# Use a 25% regression threshold between two versions
python3 tests/benchmark_suite.py --compare <base_version> <target_version> --max-regression-pct 25

# Print JSON output (contains "baseline", "current", and "comparison" objects)
python3 tests/benchmark_suite.py --compare <base_version> <target_version> --json
```

#### 7. Run from the Assistant
`tests/benchmark_suite.py` also includes `pytest` test cases that check functional assertions, latency budgets, two-version comparisons, CLI argument rules, and regression detection:
```text
prompt: benchmark <version_1> <version_2>
```

#### 8. CLI Options Summary (`tests/benchmark_suite.py`)

| Flag / Argument | Description |
| :--- | :--- |
| `<base_version> <target_version>` | Positional arguments for the two versions to compare (required unless you use `--compare`, `--base-version`/`--target-version`, `--run-current`, or `--save-*`). |
| `--compare BASE TARGET` | Compares `BASE` version against `TARGET` version (Git refs, baseline JSON paths, saved baseline names, or `workspace`). |
| `--base-version BASE` | Base version to compare from (use with `--target-version TARGET`). |
| `--target-version TARGET` | Target version to compare against `--base-version BASE`. |
| `--run-current` | Runs benchmarks on the current working tree only. |
| `--save-baseline PATH` | Writes the current working tree benchmark report to `PATH` as JSON. |
| `--save-git-ref-baseline REF PATH` | Runs benchmarks on Git `REF` and writes the report to `PATH`. |
| `--max-regression-pct PCT` | Maximum allowed latency increase percentage before flagging a regression (default: `50.0`). |
| `--json` | Prints the benchmark report and comparison results as JSON to `stdout`. |

---

### How to Read the Benchmark Results

#### 1. Read the Comparison Table
When you compare two versions (`<base_version>` and `<target_version>`), `tests/benchmark_suite.py` prints this table:

```text
============================================================================================================
GOOGLE ADS API DEVELOPER ASSISTANT — BENCHMARK SUITE (<target_version>) vs Baseline (<base_version>)
============================================================================================================
Benchmark                                  | Func   |  Base (ms) |  Curr (ms) |    Budget |     Delta |  Speedup | Status  
------------------------------------------------------------------------------------------------------------
version_resolution_in_process              | PASS   |     119.87 |       0.57 |    50.0ms |    -99.5% |  211.41x | PASS    
config_sync_and_legacy_migration           | PASS   |        N/A |      99.31 |   350.0ms |       NEW |      N/A | PASS    
hook_pre_tool_use_interception             | PASS   |        N/A |      49.63 |   250.0ms |       NEW |      N/A | PASS    
gaql_static_analysis                       | PASS   |      42.79 |       4.68 |   150.0ms |    -89.1% |    9.15x | PASS    
protobuf_type_discovery_and_inspection     | PASS   |      99.53 |      10.30 |    60.0ms |    -89.7% |    9.66x | PASS    
client_libs_parallel_release_sync          | PASS   |     632.77 |     145.02 |   400.0ms |    -77.1% |    4.36x | PASS    
conversion_csv_validation                  | PASS   |     101.16 |      91.35 |   450.0ms |     -9.7% |    1.11x | PASS    
hitl_mutation_receipt_and_sha256_normaliza | PASS   |        N/A |      82.47 |   450.0ms |       NEW |      N/A | PASS    
============================================================================================================
Total Suite Time: 483.33 ms | Verdict: PASSED (No functional or performance regressions)
============================================================================================================
```

Column descriptions:

| Column | JSON Field | Meaning |
| :--- | :--- | :--- |
| **`Benchmark`** | `name` | Name of the subsystem benchmark. |
| **`Func`** | `functional_passed` | **`PASS`** if the functional checks (`verify_fn`) passed before timing; **`FAIL`** if any check failed. |
| **`Base (ms)`** | `baseline_ms` | Total time (in milliseconds) across all iterations in `<base_version>`. Shows **`N/A`** if the benchmark did not exist in `<base_version>`. |
| **`Curr (ms)`** | `current_ms` / `total_ms` | Total time (in milliseconds) across all iterations in `<target_version>`. Lower values are faster. |
| **`Budget`** | `max_total_ms` | Maximum allowed total time (in milliseconds) for that benchmark. **`Curr (ms)` must be `<= Budget`**. |
| **`Delta`** | `pct_change` | Percentage change in time from `<base_version>` to `<target_version>` (`((Curr - Base) / Base) * 100%`):<br>• **Negative (`-89.1%`)**: `<target_version>` is faster than `<base_version>`.<br>• **Positive (`+15.2%`)**: `<target_version>` is slower than `<base_version>`.<br>• **`NEW`**: Benchmark exists only in `<target_version>`.<br>• **`REMOVED`**: Benchmark existed only in `<base_version>`. |
| **`Speedup`** | `speedup_factor` | Ratio of `Base (ms) / Curr (ms)`:<br>• **`> 1.00x`** (for example, `9.66x`): `<target_version>` is that many times faster.<br>• **`1.00x`**: Same speed.<br>• **`< 1.00x`** (for example, `0.80x`): `<target_version>` is slower.<br>• **`N/A`**: Benchmark exists in only one version. |
| **`Status`** | `regressed` | **`PASS`** when functional checks pass, `Curr (ms) <= Budget`, and no latency regression occurred; **`REGRESS`** (or **`FAIL`**) if any check fails. |

#### 2. Read Single-Run Metrics (`Iters`, `p50`, `p95`, `ops_per_sec`)
When you run `--run-current` (or inspect `"baseline"` and `"current"` in `--json` output), each benchmark also reports per-iteration metrics:
* **`iterations` (`Iters`)**: Number of timed runs after the functional check.
* **`total_ms` (`Total (ms)`)**: Total time across all iterations in milliseconds.
* **`mean_ms`**: Average time per operation (`total_ms / iterations`).
* **`p50_ms` (`p50 (ms)`)**: Median time per operation (`50th` percentile).
* **`p95_ms` (`p95 (ms)`)**: `95th` percentile time per operation.
* **`ops_per_sec`**: Operations per second (`iterations / (total_ms / 1000)`).

#### 3. How the Runner Flags Regressions
The runner marks a benchmark as **`REGRESS`** (and exits with code **`1`**) if **any** of these three conditions occur:
1. **Functional Failure (`Func == FAIL`)**: Any assertion in `verify_fn()` fails.
2. **Budget Exceeded (`Curr (ms) > Budget`)**: The total runtime exceeds `max_total_ms`.
3. **Relative Slowdown (`Delta > --max-regression-pct` AND `delta_ms > 5.0 ms`)**: The benchmark slows down by more than `--max-regression-pct` (default **`+50.0%`**) compared to `<base_version>` **and** the slowdown is greater than **`5.0 ms`**.

**Exit Codes:**
* **`0`**: All functional checks passed, all budgets were met, and no latency regressions occurred (`Verdict: PASSED`).
* **`1`**: One or more functional checks failed, a budget was exceeded, or a latency regression occurred (`Verdict: FAILED`).
* **`2`**: Invalid CLI arguments.

#### 4. What Each Benchmark Measures

| Benchmark Name | What It Tests | Purpose |
| :--- | :--- | :--- |
| **`version_resolution_in_process`** | Reads the plugin version across `config_init.get_version()` and `server.get_plugin_version()` (1,000 iterations). | Tests in-memory version caching (`_CACHED_VERSION`). |
| **`config_sync_and_legacy_migration`** | Copies `~/google-ads.yaml` to `config/google-ads.yaml` (`0600`), deletes dummy YAML files in `client_libs/`, and migrates `customer_id` / `api_version.txt` into `config/assistant_config` (50 iterations). | Tests top-level directory checks and config sync speed. |
| **`hook_pre_tool_use_interception`** | Runs `evaluate_mutation_guard()` on read-only GAQL commands (`allow`), `--dry-run` mutation commands (`allow`), and unverified live `.mutate*()` commands (`deny`) (500 iterations). | Measures `PreToolUse` hook speed on terminal tool calls. |
| **`gaql_static_analysis`** | Checks GAQL syntax, rejects `OR` clauses, `COUNT()` aggregates, and `segments.hour` + date combinations, and checks dry-run cache hits (200 iterations). | Tests SHA-256 query cache (`compute_gaql_cache_key`) and static validator speed. |
| **`protobuf_type_discovery_and_inspection`** | Finds available Protobuf message and enum types for the active API version and reads field definitions (200 iterations). | Tests two-tier memory (`_AVAILABLE_TYPES_CACHE`) and disk (`gads_assistant_types_<ver>.json`) caching. |
| **`client_libs_parallel_release_sync`** | Checks client library repositories against GitHub releases (`check_only=True`) with simulated `25 ms` network latency per repo (5 iterations). | Tests concurrent `ThreadPoolExecutor` release checks. |
| **`conversion_csv_validation`** | Validates a 100-row offline conversion CSV file (headers, ISO-8601 timestamps with timezones, and GCLIDs) (50 iterations). | Checks CSV validation speed across 5,000 rows. |
| **`hitl_mutation_receipt_and_sha256_normalization`** | Calculates normalized Protobuf SHA-256 hashes, writes signed `last_dry_run.json` receipts, and checks receipt integrity (100 iterations). | Tests the receipt verification pipeline that gates live mutations. |

## Maintenance

During installation, the installer copies `update.sh` and `update.ps1` (and the repository path in `config/.repo_root`) into your installed plugin directory. You can run updates from the repository root or from **any directory**:

*   **Linux/macOS (from repository root):**
    ```bash
    ./update.sh agy          # Update Antigravity plugin
    ./update.sh claude       # Update Claude Code plugin
    ```
    To add or update specific client libraries:
    ```bash
    ./update.sh agy --java --dotnet
    ```
*   **Linux/macOS (from any directory):**
    ```bash
    # Update plugin and client libraries
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --java --dotnet
    ~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/update.sh claude

    # Enable or disable the plugin from any directory
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --disable
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/update.sh agy --enable
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh disable
    ~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.sh enable
    ```
*   **Windows PowerShell (from repository root):**
    ```powershell
    .\update.ps1 -Type agy
    .\update.ps1 -Type claude
    ```
    To add or update specific client libraries:
    ```powershell
    .\update.ps1 -Type agy -Java -Dotnet
    ```
*   **Windows PowerShell (from any directory):**
    ```powershell
    # Update plugin and client libraries
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -Java -Dotnet
    & "$HOME\.claude\plugins\google-ads-assistant-local\plugins\google-ads-api-developer-assistant\update.ps1" -Type claude

    # Enable or disable the plugin from any directory
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -Disable
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\update.ps1" -Type agy -Enable
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" disable
    & "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant\plugin.ps1" enable
    ```

## Uninstallation

Use the uninstallation command for your platform to remove the plugin:

### Antigravity

Delete the installed plugin directory:

*   **Linux/macOS:**
    ```bash
    rm -rf ~/.gemini/config/plugins/google-ads-api-developer-assistant
    ```
*   **Windows (PowerShell):**
    ```powershell
    Remove-Item -Recurse -Force "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant"
    ```

Restart your Antigravity / `agy` session to finish uninstallation.

### Claude Code

*   **In an active Claude Code session:**
    ```text
    /plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
*   **Or in your terminal:**
    ```bash
    claude plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```

*(Optional)* Remove the local marketplace registration:
*   **In Claude Code:** `/plugin marketplace remove google-ads-assistant-local`
*   **In your terminal:** `claude plugin marketplace remove google-ads-assistant-local`

Delete the local marketplace plugin directory:
*   **Linux/macOS:**
    ```bash
    rm -rf ~/.claude/plugins/google-ads-assistant-local
    ```
*   **Windows (PowerShell):**
    ```powershell
    Remove-Item -Recurse -Force "$HOME\.claude\plugins\google-ads-assistant-local"
    ```

## Contributing

Read `CONTRIBUTING.md` for instructions on how to report bugs, request features, and send pull requests.

## Support

Use the GitHub Issues tab for bug reports, feature requests, and support questions.

## License

Apache License 2.0. See the `LICENSE` file.
