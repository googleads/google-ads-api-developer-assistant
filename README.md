# Google Ads API Developer Assistant

**TL;DR:** This assistant lets you interact with the Google Ads API using natural language. Ask questions, generate GAQL and code in several languages, and execute API calls directly in your terminal.

## Overview

The Google Ads API Developer Assistant streamlines workflows for developers working with the Google Ads API. Use natural language prompts to:

*   Get answers to Google Ads API questions.
*   Construct Google Ads Query Language (GAQL) queries.
*   Generate executable code in several languages using our client libraries for context.
*   Retrieve and display data from the API.

This assistant is powered by the **Antigravity** (v4.1.0) and **Claude Code** agent frameworks and leverages `AGENTS.md` / `CLAUDE.md` files, native slash commands, and custom **Skills** to deliver persistent context, robust safety constraints, and automated execution pipelines.

## Agentic Design & Approach

The Assistant uses a structured hierarchy of instruction files, slash commands, and specialized domain tools to ensure safe, precise, and highly competent interactions with the Google Ads API across supported agent environments.

### 1. Unified Context via `AGENTS.md` & `CLAUDE.md`
The master configuration files act as the system contract for the assistant:
*   **Version Cache Protocol**: Automatically discovers and locks the latest active API version (cached as `api_version` in `config/assistant_config`).
*   **Version Parity Enforcement**: Verifies parity between the runtime `google-ads` Python package and local `client_libs/google-ads-python` source-of-truth definitions, issuing warnings on discrepancies.
*   **Code Generation Pipeline**: Passes all generated Python code through strict `ruff` linting before saving or displaying it.
*   **Programmatic GAQL Validation**: Evaluates queries against field metadata and compatibility boundaries.
*   **Safety Constraints (4-Step HITL Mutation Guard)**: Enforces a mandatory 4-step Human-in-the-Loop (HITL) verification protocol for all API mutations—requiring a GAQL before-state read, a `validate_only=True` dry-run with a SHA-256 signed receipt (`saved/data/last_dry_run.json`), explicit consequence disclosure, and deterministic `PreToolUse` hook confirmation (`"decision": "force_ask"`) before any live write executes.

### 2. Domain-Specific "Skills" & Native Commands
Rather than relying on generic AI completions, the assistant is empowered with specialized, test-backed tool directories under `plugins/google-ads-api-developer-assistant/skills/` and native slash commands under `plugins/google-ads-api-developer-assistant/commands/`.

Key capabilities support dual invocation (natural language prompts in Antigravity or dedicated slash commands in Claude Code):
*   **HITL-Verified Mutations (`/execute-mutation`)**: Executes a two-phase `--dry-run` (`validate_only=True`) and `--execute` workflow with cryptographic receipt verification and financial/serving consequence disclosure.
*   **GAQL Validation (`/validate-gaql`)**: Dry-runs queries via the API `validate_only` parameter.
*   **Object Inspection (`/inspect-object`)**: Inspects API resources, nested messages, or enum definitions on the fly.
*   **MCC Account Mapping (`/get-cids`)**: Maps client hierarchies and retrieves sub-account CIDs under manager accounts.
*   **Conversion Troubleshooting (`/troubleshoot-conversions`)**: Investigates conversion upload summaries and pre-validates files.
*   **PMax Listing Filters & URL Exclusions (`/pmax-filter`)**: Generates product partition trees and webpage URL exclusions.
*   **Structured Explanations (`/explain`, `/step-by-step`, `/assistant-tutorial`)**: Delivers standardized multi-part explanations, step breakdowns, and interactive tutorials.
*   **Environment & Library Sync (`/sync-client-libs`, `/ext-version`)**: Synchronizes client libraries and verifies active API version settings.

## Key Features

*   **Natural Language Q&A & Conceptual Guidance:** Ask about Google Ads API concepts, fields, and usage in plain English, or use structured explanation commands.
    *   *Natural Language:* "What are the available campaign types?", "Tell me about reporting for Performance Max campaigns."
    *   *Claude Code:* `/explain`, `/step-by-step`, `/assistant-tutorial`

*   **Natural Language to GAQL & Client Library Code:** Convert requests into executable code using the Google Ads Client Libraries.
    *   Code is saved to `saved/code/`.
    *   *"Show me campaigns with the most conversions last 30 days."*
    *   *"Get all ad groups for customer '123-456-7890'."*
    *   *"Find disapproved ads across all campaigns."*

*   **Validate Complex GAQL Queries:** Validate complex GAQL queries against API metadata and compatibility rules.
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

*   **Direct API Execution:** Run the generated Python code directly and view results, often formatted as tables. Execution takes place within a managed virtual environment that has the Google Ads API Client Libraries installed.

*   **CSV Export:** Save tabular API results to a CSV file in the `saved/csv/` directory.
    *   *"Save results to a csv file"*

*   **Conversion Troubleshooting & Diagnostics:** Generate structured diagnostic reports to debug offline conversion issues.
    *   *Claude Code:* `/troubleshoot-conversions`
    *   *Natural Language:* *"Troubleshoot my conversions for customer '123-456-7890'."* (Reports saved to `saved/data/`).


## Supported Languages

*   Python
*   PHP
*   Ruby
*   Java
*   C# (.NET)

Code generated by Python, PHP, and Ruby can be executed directly. Code generated by Java and C# must be compiled and executed separately. This is because of security policies. For C# code generation, use 'in dotnet' to set the context.

By default, Python is strictly used for all code generation and execution across the assistant, even when other language libraries or project files are present. The assistant will only switch to generating or executing in another language if specifically requested by the user. Because the plugin is installed globally, you can launch `agy` or `claude` directly inside your own application codebase so the assistant includes your application logic in its reasoning when creating responses.
   * Before requesting code output in a different language, tell the Assistant: `write saved code examples in <language of your application>`

## Prerequisites

1.  Familiarity with Google Ads API concepts and authentication.
2.  A Google Ads API developer token.
3.  A configured credentials file in your home directory if using Python (`google-ads.yaml`), PHP (`google_ads_php.ini`), or Ruby (`google_ads_config.rb`).
4.  Antigravity or Claude Code environment configured.
5.  A local clone of each client library for the languages you want to use. `install.sh` (Linux/macOS) or `install.ps1` (Windows) can set this up for you.
6.  Python >= 3.11 installed and available on your system PATH. This is required for executing the default generated Python code directly.

## Setup

### 1. Install Host Platform

Choose and set up your assistant environment:

#### Antigravity CLI
* Download and install `antigravity-cli` from [https://antigravity.google/](https://antigravity.google/).
* Verify your installation:
  ```bash
  agy --version
  ```

#### Claude Code
1. **Prerequisites:** Ensure [Node.js](https://nodejs.org/) (version 18 or higher) is installed on your system:
   ```bash
   node --version
   ```
2. **Install Claude Code CLI:** Install Claude Code globally using npm:
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```
   *(Alternatively on macOS via Homebrew: `brew install claude-code`)*
3. **Authenticate:** Run `claude` in your terminal to authenticate with your Anthropic account or configure your API key:
   ```bash
   claude
   ```
4. **Verify Installation:** Check that the CLI is accessible:
   ```bash
   claude --version
   ```

---

### 2. Clone the Assistant
Clone the repository to your local machine:
```bash
git clone https://github.com/googleads/google-ads-api-developer-assistant
cd google-ads-api-developer-assistant
```

---

### 3. Run Install Script
Run the installation script matching your platform:

*   **Antigravity (Linux/macOS):**
    ```bash
    ./install.sh agy
    ```
    *Installs plugin globally to `~/.gemini/config/plugins/google-ads-api-developer-assistant`.*
    *To symlink directly to your git checkout so `git pull` updates take effect immediately: `./install.sh agy --link`.*
    *To include additional client libraries: `./install.sh agy --php --ruby --dotnet`.*

*   **Claude Code (Linux/macOS):**
    ```bash
    ./install.sh claude
    ```
    *Registers the repository as a local marketplace and installs the plugin into Claude Code via the `claude` CLI.*
    *To include additional client libraries: `./install.sh claude --php --ruby --dotnet`.*

*   **Antigravity (Windows - PowerShell):**
    ```powershell
    .\install.ps1 -Type agy
    ```
    *Installs plugin globally to `%USERPROFILE%\.gemini\config\plugins\google-ads-api-developer-assistant`.*
    *To symlink directly to your git checkout: `.\install.ps1 -Type agy -Link`.*
    *To include additional client libraries: `.\install.ps1 -Type agy -Php -Ruby -Dotnet`.*

*   **Claude Code (Windows - PowerShell):**
    ```powershell
    .\install.ps1 -Type claude
    ```
    *Registers the local marketplace and installs the plugin into Claude Code via Claude CLI.*
    *To include additional client libraries: `.\install.ps1 -Type claude -Php -Ruby -Dotnet`.*

---

### 4. Configure Credentials
Make sure your Google Ads API credentials configuration file is in your `$HOME` directory (`~/google-ads.yaml` for Python, `~/google_ads_php.ini` for PHP, `~/google_ads_config.rb` for Ruby, or `~/ads.properties` for Java). At session startup, [`config/config_init.py`](config/config_init.py) automatically syncs your credentials into `config/google-ads.yaml` (`0600` permissions) and sets `GOOGLE_ADS_CONFIGURATION_FILE_PATH`.

---

### 5. Configure Assistant Settings (`config/assistant_config`)
All assistant settings—active API version, default Customer ID, and live mutation permissions—are stored in a single TOML file at [`config/assistant_config`](config/assistant_config) (and mirrored in [`plugins/google-ads-api-developer-assistant/config/assistant_config`](plugins/google-ads-api-developer-assistant/config/assistant_config)):

```toml
api_version = "v25"
customer_id = "12345678"
execute_mutates = false
```

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| **`api_version`** | `string` | `"v25"` | Active Google Ads API version used for GAQL validation, Protobuf inspection, and code generation. Automatically detected and updated when running `install.sh`, `update.sh`, `sync_client_libs.py`, `get_latest_api_version.py`, or `python3 config/config_init.py --key api_version`. |
| **`customer_id`** | `string` | `"12345678"` | Default Google Ads Customer ID (10-digit account ID without dashes) used when a prompt does not explicitly specify a CID (e.g., *"Get my campaigns"*). |
| **`execute_mutates`** | `boolean` | `false` | Controls whether live Google Ads API write/mutate operations (`--execute` / `validate_only=False`) are permitted through the 4-Step HITL protocol. |

You can configure `customer_id` during installation (`./install.sh agy --cid 1234567890`), edit `config/assistant_config` directly, or run `config_init.py`:
```bash
# Set default Customer ID in config/assistant_config and sync config/google-ads.yaml (from repo root)
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key customer_id --value 1234567890

# Or via the installed Antigravity plugin:
python3 ~/.gemini/config/plugins/google-ads-api-developer-assistant/config/config_init.py --key customer_id --value 1234567890

# Automatically detect the latest API version across client_libs and site-packages and update config/assistant_config
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key api_version

# Lock a specific API version in config/assistant_config
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --key api_version --value v26

# Synchronize client_libs and api_version synchronously from the CLI
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --sync-client-libs

# Enable or disable live mutations in config/assistant_config
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates true
python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates false
```

## Usage

1.  **Start Assistant Session:**
    Ask questions, generate code, and validate queries within your Antigravity terminal session or Claude Code.

2.  **Ask a question:**
    > "What are the resource names for my enabled campaigns sorted by campaign id"

3.  **Generate Code:**
    > "Get me the top 5 campaigns by cost last month for customer 1234567890"

4.  **Execute and Save:**
    > "Run the code"
    > ... (code displayed as the result of a previous request) ...
    > "Save the results to csv"

## Stay in sync

The Assistant includes automated synchronization tools to ensure your runtime credentials, `config/assistant_config`, local client libraries (`client_libs/`), Protobuf definitions, and system `google-ads` package remain aligned.

### 1. What Synchronizes at Session Startup (`config/config_init.py`)

When you start a CLI session in Antigravity (`agy`) or Claude Code (`claude`), the `PreInvocation` lifecycle hook in [`hooks.json`](plugins/google-ads-api-developer-assistant/hooks.json) executes `python3 config/config_init.py --hook` to synchronize credentials and run a **5-Step Client Library & API Version Verification Workflow**:

| Startup Step | Execution Mode | What Happens Under the Hood | What Is Modified |
| :--- | :--- | :--- | :--- |
| **Credential Normalization & `api_version` Discovery** (`sync_and_set_config_kv` & `detect_latest_api_version`) | **Automatic** (Every session start) | Reads your `$HOME` config (`~/google-ads.yaml`, `~/google_ads_php.ini`, `~/google_ads_config.rb`, `~/ads.properties`, or `.NET` `App.config` / `appsettings.json`), writes `config/google-ads.yaml` (`0600` permissions) with `use_proto_plus: True` and `ads_assistant: <version>`, exports `GOOGLE_ADS_CONFIGURATION_FILE_PATH`, scans `v<N>` subdirectories across both `client_libs/google-ads-python` and `google.ads.googleads.__path__` in Python `site-packages`, and auto-advances `api_version` in `config/assistant_config` when a newer version is installed. | `config/google-ads.yaml` and `config/assistant_config` (Never modifies your `$HOME` config) |
| **Step 1 — Check Python Site-Directory Version** (`check_python_client_lib_parity` / `detect_system_package_version`) | **Automatic** (Read-only check) | Inspects your active Python environment's site-packages directory (`site.getsitepackages()`, `importlib.metadata.version("google-ads")`) and local `client_libs/google-ads-python/pyproject.toml` to determine the currently installed `google-ads` package and client library versions. | None (Read-only inspection) |
| **Step 2 — Check Latest GitHub Release** (`fetch_latest_github_python_version` / `fetch_github_latest_release`) | **Automatic** (Read-only check, 1-hour cache) | Queries the GitHub Releases API (`googleads/google-ads-python/releases/latest`, cached in `$TMPDIR/gads_assistant_github_release.json` for 1 hour) to identify the latest upstream client library version on GitHub. | `$TMPDIR/gads_assistant_github_release.json` |
| **Step 3 — Prompt User When Site Version `<` GitHub Version** (`handle_hook` $\rightarrow$ `PreInvocation`) | **Interactive Prompt** (When `site_version < github_version`) | If the version of `google-ads` installed in your Python site directory (or `client_libs/google-ads-python` in the Assistant directory) is older (`<`) than the latest release on GitHub, the Assistant pauses and prompts you to ask whether you want to upgrade to the latest version on GitHub. | None (Waits for your `yes` / `no` response) |
| **Step 4 — If You Reply `Yes`: Full Site & Assistant Upgrade** (`sync_client_libs.py --upgrade_system`) | **On User Confirmation (`Yes`)** | 1. Installs the latest version of `google-ads` from `pypi.org` (`--index-url https://pypi.org/simple`) into the Python site directory.<br>2. Installs/synchronizes the latest version of the client library into the site directory.<br>3. Updates `client_libs/google-ads-python` in the Assistant directory structure to the latest GitHub release.<br>4. Updates `api_version` in `config/assistant_config` (and legacy `config/api_version.txt` if present) to the latest `v<N>` version.<br>5. Prints the synchronization results table to the screen. | Python `site-packages`, `client_libs/google-ads-python`, and `config/assistant_config` (`api_version`) |
| **Step 5 — If You Reply `No`: Version Comparison Table** (`sync_client_libs.py --check_only`) | **On User Decline (`No`)** | Leaves your Python site directory and `client_libs/` untouched and prints a comparison table showing the latest versions on GitHub/PyPI versus the versions currently installed on your system. | None (Read-only report) |

> **Want to run the full synchronization directly from your terminal?**
> You can execute the check or upgrade at any time outside a chat prompt:
> ```bash
> # Check installed site-packages and client_libs versions vs. GitHub (Step 5 table)
> python3 plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py --check_only
>
> # Upgrade site-packages from pypi.org, update Assistant client_libs, and refresh api_version (Step 4)
> python3 plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system
> ```

### 2. Requesting Synchronization During a Session
You can check for updates or trigger synchronization at any time while in an active session:

* **Natural Language Prompts (Antigravity & Claude Code):**
  * *"Sync my client libraries"*
  * *"Check for Google Ads client library updates"*
  * *"Update the Python client library to the latest release"*

* **Dedicated Slash Command (Claude Code):**
  * Run `/sync-client-libs` to inspect and synchronize all local client libraries.
  * Target a specific library: `/sync-client-libs python` or `/sync-client-libs dotnet`.

* **Verify Active Version:**
  * Claude Code: `/ext-version`
  * Natural Language: *"What is the active Google Ads API version?"*

### 3. Manual Terminal Updates
To update the repository, assistant plugin, and all configured client libraries outside an active session:
* **Linux/macOS:**
  ```bash
  ./update.sh agy --all          # Update Antigravity plugin and all client libraries
  ./update.sh claude --all       # Update Claude Code plugin and all client libraries
  ```
* **Windows (PowerShell):**
  ```powershell
  .\update.ps1 -Type agy -All
  .\update.ps1 -Type claude -All
  ```

### 4. Client Library & Runtime Version Parity
The Assistant relies on local client library sources (`client_libs/google-ads-python`) as the primary **source of truth** for Protobuf schemas, resource definitions, and enum descriptors, while executing queries and generated code through the installed `google-ads` Python package in your environment.

To prevent silent schema discrepancies, missing fields, or descriptor errors:
* **Automated Parity Checks:** Tool scripts (such as `inspect_object.py` and `sync_client_libs.py`) automatically compare the installed environment package version (`importlib.metadata.version('google-ads')`) against the local `client_libs/google-ads-python` version metadata (`pyproject.toml` / `ChangeLog`) and upstream GitHub releases.
* **System Site-Directory Parity & Upgrades:** When discovering a newer upstream release of `google-ads` or the Python client library, the sync tool automatically inspects the Python system site-packages directory (`site.getsitepackages()`). If the versions do not match, Gemini alerts you with an explicit warning and asks if you would like Gemini to upgrade the system version. Upon your confirmation, Gemini executes the upgrade (`pip install --upgrade google-ads` or `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system`).
* **Warning Directives:** If a version mismatch is detected, the Assistant and inspection tools output an explicit warning banner:
  ```text
  WARNING: Installed google-ads package version (<installed_version>) does not match client_libs/google-ads-python version (<client_libs_version>) used for protobuf inspection. Schema inspection or API calls may encounter field discrepancies.
  ```
* **Resolving Mismatches:**
  * Synchronize client libraries to latest: `/sync-client-libs` (or prompt *"Sync client libraries"*).
  * Upgrade the runtime Python package: `pip install --upgrade google-ads` (or run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system`).
  * Perform a complete update: `./update.sh agy --all` or `./update.sh claude --all`.


## Directory Structure

*   `plugins/google-ads-api-developer-assistant/`: Source directory for the assistant plugin.
*   `plugins/google-ads-api-developer-assistant/commands/`: Native slash commands for Claude Code.
*   `plugins/google-ads-api-developer-assistant/skills/`: Assistant skills (GAQL analyzer, proto inspect, HITL mutation runner, etc.).
*   `plugins/google-ads-api-developer-assistant/rules/`: Agent behavioral rules and protocols.
*   `plugins/google-ads-api-developer-assistant/sidecars/`: Background sidecar microservices.
*   `plugins/google-ads-api-developer-assistant/client_libs/`: Cloned client libraries.
*   `plugins/google-ads-api-developer-assistant/config/`: Plugin-bundled configuration (`assistant_config` and `config_init.py`).
*   `plugins/google-ads-api-developer-assistant/mcp_config.json`: Model Context Protocol configuration.
*   `config/`: Workspace configuration directory:
    *   `config/assistant_config`: Unified TOML configuration file storing `api_version`, `customer_id`, and `execute_mutates`.
    *   `config/config_init.py`: Session initializer and `PreInvocation` / `PreToolUse` lifecycle hook handler.
    *   `config/google-ads.yaml`: Generated runtime Google Ads API credentials file (`0600` permissions).
*   `saved/`: Working directory storage for artifacts and runnable scripts:
    *   `saved/` (or `saved/code/`): Runnable Python code saved for later execution (mandatory target sub-directory).
    *   `saved/data/`: GAQL validation cache, CSV exports, diagnostic reports, and mutation dry-run receipts.
    *   `saved/logs/`: Append-only audit logs (`mutation_audit.jsonl`).

## Plugin Architecture

To learn more about how Antigravity and Claude define plugins, see the [Antigravity plugin specification](https://antigravity.google/docs/cli/plugins/) and the [Claude plugin specification](https://github.com/anthropics/knowledge-work-plugins).

## How Mutates Work

When you ask the Assistant to perform any write or mutation operation (such as updating a campaign budget, pausing an ad group, applying a recommendation, removing a criterion, or uploading conversions), the plugin enforces a **Defense-in-Depth Human-in-the-Loop (HITL) Verification Protocol** (`skills/execute-mutation/`) backed by deterministic `PreToolUse` lifecycle hooks (`config/config_init.py`) and pre-RPC SHA-256 verification.

---

### 1. Configuring the Mutate Switch (`execute_mutates` in `config/assistant_config`)

By default, live mutations are **disabled** (`execute_mutates = false` in `config/assistant_config`). In this default state, the Assistant can still run read-only GAQL queries and `validate_only=True` dry-runs (`--dry-run`), but any live write (`--execute` or `validate_only=False`) is hard-blocked.

#### How to Enable or Disable Live Mutations
You can control this setting in either of two ways:

1. **Edit `config/assistant_config` (TOML) directly:**
   Open `config/assistant_config` and set `execute_mutates` to `true` or `false`:
   ```toml
   api_version = "v25"
   customer_id = "12345678"
   execute_mutates = false
   ```
   ```toml
   api_version = "v25"
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

**Configuration File Precedence:**
When evaluating a mutation, the plugin checks candidate files in this order and uses the **first file that exists**:
1. `config/assistant_config` (workspace `config/` directory) — **highest file precedence**
2. `plugins/google-ads-api-developer-assistant/config/assistant_config` (plugin source directory)
3. `~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config` (installed global plugin directory)

*(If `execute_mutates = false` is active and a live mutation is attempted, the `PreToolUse` hook and `run_mutation.py` immediately block execution on screen with: `BLOCKED BY HITL MUTATION GUARD: Mutate support is disabled by configuration (execute_mutates = false in config/assistant_config). Set 'execute_mutates = true' in config/assistant_config to enable live Google Ads API mutations.`)*

---

### 2. The 4-Step HITL Mutation Workflow & What You See on Screen

Every mutation request follows a strict 4-step sequence so you always see the current state, the API dry-run validation result, the cryptographic request hash, and the exact financial/serving consequences before any live change occurs.

#### Step 1 — Pre-Mutation State & Blast Radius Lookup (Mandatory GAQL Read)
Before generating or running any mutation code, the Assistant queries your account via `GoogleAdsService.search_stream` to capture the **Before State** and **Blast Radius**:
* Exact resource names (e.g., `customers/1234567890/campaignBudgets/98765`).
* Current `status` (`ENABLED`, `PAUSED`, `REMOVED`).
* Current budget or bid amounts (`amount_micros`, `cpc_bid_micros`) converted to standard currency (`micros / 1,000,000`).
* Count of active downstream child entities affected (e.g., active `ad_group` and `ad_group_ad` counts, or shared campaigns).

#### Step 2 — Mandatory `validate_only=True` Dry-Run & Signed Receipt
The Assistant generates a Python script in `saved/code/` supporting `--dry-run` (`validate_only=True`, default) and `--execute` (`validate_only=False`), lints it with `ruff`, and runs the dry-run against the live Google Ads API via `run_mutation.py`:
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
* The Google Ads API validates all schema rules, resource IDs, and policy constraints with `validate_only=True` **without** mutating your account.
* If validation succeeds, `run_mutation.py` computes both the script's SHA-256 (`script_sha256`) and a canonical SHA-256 digest of the normalized Protobuf mutate request payload (`request_sha256`), and writes a signed receipt to `saved/data/last_dry_run.json` (valid for 30 minutes).

#### Step 3 — On-Screen Verification Card & Consequence Disclosure
Immediately after `--dry-run` succeeds, you will see the **Mutation & Consequence Verification Card** printed to your terminal/chat screen:

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

The Assistant discloses category-specific consequences and **pauses for your explicit confirmation** before proceeding:
* **Budgets & Bidding:** Exact currency delta (`$X.XX/day` $\rightarrow$ `$Y.YY/day`, `%` change), maximum monthly spend exposure (`daily_budget * 30.4`), and Smart Bidding learning-phase warnings for $>20\%$ shifts.
* **Status Changes (`PAUSED` $\leftrightarrow$ `ENABLED`):** Exact count of downstream active Ad Groups and Ads that will immediately stop serving or resume spending.
* **Destructive Operations (`REMOVE`):** Explicit warning when an operation is **`IRREVERSIBLE (PERMANENT)`** and cannot be re-enabled (recommending `PAUSED` if temporary suspension is desired).
* **Targeting & Conversion Goals:** Warnings on traffic expansion/restriction or automated bidding signal changes.

#### Step 4 — Hook-Gated CLI Confirmation & Live Execution (`--execute`)
Once you confirm in chat and `execute_mutates = true` is enabled in `config/assistant_config`, the Assistant invokes:
```bash
python3 skills/execute-mutation/scripts/run_mutation.py \
  --script saved/code/update_campaign_budget.py \
  --execute
```

1. **Native CLI Hook Confirmation Prompt (`PreToolUse`):**
   Before the command is allowed to run, the `PreToolUse` lifecycle hook (`config/config_init.py`) verifies `execute_mutates = true`, `script_sha256`, and `request_sha256` against `saved/data/last_dry_run.json` and forces an interactive CLI permission prompt (`"decision": "force_ask"` in **Antigravity (`agy`)** / `"permissionDecision": "ask"` in **Claude Code CLI**), overriding any cached *"Always Allow"* settings. On your screen, the CLI displays:
   ```text
   ⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION [Customer ID: 1234567890]
   • Operation: Update CampaignBudget (customers/1234567890/campaignBudgets/98765)
   • Change: $50.00/day (50,000,000 micros), Status: ENABLED -> $250.00/day (250,000,000 micros), Status: ENABLED
   • Request SHA256: 8f4e2b9a1c3d5e7f0a2b4c6d8e0f1a3b5c7d9e1f3a5b7c9d1e3f5a7b9c1d3e5f
   • Reversibility: REVERSIBLE
   • Consequences: Daily budget cap increases by +$200.00/day (+400%); Max monthly spend exposure increases to ~$7,600.00/mo
   Confirm execution of this live Google Ads API mutation?
   ```
2. **Pre-RPC SHA-256 Verification:**
   When you approve the terminal prompt, `run_mutation.py` intercepts `GoogleAdsClient.get_service` inside the script subprocess and recomputes the canonical SHA-256 digest of the outgoing `Mutate*Request` **before** transmitting the gRPC call. If the request payload differs in any way from the `validate_only=True` dry-run (apart from `validate_only` changing from `True` to `False`), or if an extra unapproved mutation call is attempted, the RPC is blocked (`BLOCKED_SHA256_MISMATCH`) before it ever leaves your machine.
3. **Live Result & One-Time Receipt Consumption:**
   The live mutation executes with `ResponseContentType.MUTABLE_RESOURCE` and prints the mutated resource name(s) to your screen. The receipt in `saved/data/last_dry_run.json` is immediately marked `"status": "EXECUTED"` so the same receipt cannot be replayed.
4. **Immutable Audit Trail (`saved/logs/mutation_audit.jsonl`):**
   Both `--dry-run` and `--execute` append a structured JSONL audit record (`0600` permissions, with all credentials automatically redacted) to `saved/logs/mutation_audit.jsonl` capturing:
   * `actor`: OS user, hostname, `login_customer_id`, `target_customer_id`, auth type, and CLI conversation/transcript IDs.
   * `request`: `sent_at_iso`, `validate_only`, `script_sha256`, `request_sha256`, `request_sha256_verified`, and the serialized Protobuf request payload.
   * `approval`: `dry_run_validated_at_iso`, `hook_prompted_at_iso`, `user_approved_at_iso`, `before_state`, `after_state`, `consequences`, and `reversibility`.
   * `response`: `received_at_iso`, `duration_ms`, `google_ads_request_ids`, and the serialized Protobuf response or error payload.

---

### 3. Summary of Safeguards (`config/config_init.py` & `run_mutation.py`)

| Condition | Hook / Runner Decision | What Happens on Screen |
| :--- | :--- | :--- |
| Read-only query (`search`, `search_stream`) or `--dry-run` (`validate_only=True`) | **`allow`** | Executes immediately and displays query results or the **Mutation & Consequence Verification Card**. |
| Live mutation attempted while `execute_mutates = false` (default) | **`deny` (Hard Block)** | Blocked before execution with instructions to set `execute_mutates = true` in `config/assistant_config`. |
| Live mutation attempted without a valid ($\le 30\text{ min}$) `DRY_RUN_PASSED` receipt | **`deny` (Hard Block)** | Blocked before execution with instructions to run `--dry-run` first. |
| Script file (`script_sha256`) or RPC request payload (`request_sha256`) altered after dry-run | **`deny` / `BLOCKED_SHA256_MISMATCH`** | Blocked before any live RPC is sent to Google Ads; mismatch logged to `saved/logs/mutation_audit.jsonl`. |
| Valid receipt + `execute_mutates = true` + matching SHA-256 digests | **`force_ask` (Interactive CLI Prompt)** | Displays the `⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION` card in the CLI and waits for your explicit approval. |

## Behavioral Differences to Note in 4.1.0

When upgrading from `4.0.0` to `4.1.0`, existing CLI arguments, A2A sidecar payloads, and legacy configuration files (`config/customer_id`, `config/customer_id.txt`, `config/api_version.txt`, and `~/google-ads.yaml`) remain backward-compatible and are automatically migrated or synced. Note the following behavioral differences:

1. **Default Output Path (`~/saved/...` $\rightarrow$ `./saved/...`):**
   * In `4.0.0`, skill scripts (`get_cids_under_mcc.py`, `troubleshoot_conversions.py`) wrote default output files to `~/saved/csv/` and `~/saved/logs/` in the user's home directory.
   * In `4.1.0`, default outputs are written to workspace-relative `saved/data/`, `saved/logs/`, and `saved/code/` (unless `--output_dir` is explicitly passed).
2. **Hook-Enforced Mutation Guard (`evaluate_mutation_guard`):**
   * In `4.0.0`, live mutations were restricted only via prompt instructions (`NO MUTATE`).
   * In `4.1.0`, the `PreToolUse` hook in `config/config_init.py` (`handle_hook`) deterministically blocks (`deny`) any command invoking a live `.mutate*()` call unless `execute_mutates = true` is enabled in `config/assistant_config` and a valid dry-run receipt (`saved/data/last_dry_run.json`) exists. Read-only queries and `validate_only=True` dry-runs are unaffected.

## Performance & Functionality Benchmarks (`v4.0.0` vs `v4.1.0`)

The repository includes an automated cross-version benchmark suite (`tests/benchmark_suite.py`) that verifies functional correctness and latency budgets (`total_ms`, `p50_ms`, `p95_ms`, `ops/sec`) against saved version baselines (`tests/benchmarks/baseline_v4.0.0.json` and `tests/benchmarks/baseline_v4.1.0.json`) or arbitrary git refs.

| Benchmark | Iterations | `v4.0.0` Baseline (ms) | `v4.1.0` Current (ms) | Budget (ms) | Delta | Speedup | Status |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| `version_resolution_in_process` | 1,000 | `119.87` | `0.57` | `50.0` | `-99.5%` | **211.41x** | `PASS` |
| `gaql_static_analysis` | 200 | `42.79` | `4.68` | `150.0` | `-89.1%` | **9.15x** | `PASS` |
| `protobuf_type_discovery_and_inspection` | 200 | `99.53` | `10.30` | `60.0` | `-89.7%` | **9.66x** | `PASS` |
| `client_libs_parallel_release_sync` | 5 | `632.77` | `145.02` | `400.0` | `-77.1%` | **4.36x** | `PASS` |
| `conversion_csv_validation` | 50 | `101.16` | `91.35` | `450.0` | `-9.7%` | **1.11x** | `PASS` |
| `config_sync_and_legacy_migration` | 50 | `N/A (v4.1)` | `99.31` | `350.0` | `NEW` | `N/A` | `PASS` |
| `hook_pre_tool_use_interception` | 500 | `N/A (v4.1)` | `49.63` | `120.0` | `NEW` | `N/A` | `PASS` |
| `hitl_mutation_receipt_and_sha256_normalization` | 100 | `N/A (v4.1)` | `82.47` | `450.0` | `NEW` | `N/A` | `PASS` |

To run the benchmark suite or compare against a baseline or git tag:

```bash
# Run benchmark suite and compare against the saved v4.0.0 baseline
python3 tests/benchmark_suite.py

# Compare current workspace directly against git tag v4.0.0
python3 tests/benchmark_suite.py --compare-git-ref v4.0.0

# Run as part of pytest
pytest -v tests/benchmark_suite.py
```

## Known Quirks

*   The underlying model may have been trained on an older API version. It may occasionally generate code with deprecated fields. Execution errors often provide feedback that allows the assistant to self-correct on the next attempt, using the context from the client libraries. To avoid these errors, we always search for the latest version of the API when initializing the session and ask you to verify the version.

## Maintenance

We will periodically release updates to the assistant and client libraries.
To update your repository, plugin installation, and client libraries:

*   **Linux/macOS:**
    ```bash
    ./update.sh agy          # Update Antigravity plugin
    ./update.sh claude       # Update Claude Code plugin
    ```
    To add or update specific client libraries:
    ```bash
    ./update.sh agy --java --dotnet
    ```
*   **Windows:**
    ```powershell
    .\update.ps1 -Type agy
    .\update.ps1 -Type claude
    ```
    To add or update specific client libraries:
    ```powershell
    .\update.ps1 -Type agy -Java -Dotnet
    ```

## Uninstallation

To remove the Google Ads API Developer Assistant plugin, use the native uninstallation mechanism for your platform:

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

Restart your Antigravity / agy host session to complete the uninstallation.

### Claude Code

*   **Within an active Claude Code session:**
    ```text
    /plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
*   **Or from your terminal:**
    ```bash
    claude plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```

*(Optional)* To remove the local marketplace registration as well:
*   **Within Claude Code:** `/plugin marketplace remove google-ads-assistant-local`
*   **From terminal:** `claude plugin marketplace remove google-ads-assistant-local`

## Contributing

Please see `CONTRIBUTING.md` for guidelines on reporting bugs, suggesting features, and submitting pull requests.

## Support

Use the GitHub Issues tab for bug reports, feature requests, and support questions.

## License

Apache License 2.0. See the `LICENSE` file.
