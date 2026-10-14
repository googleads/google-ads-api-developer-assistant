# Frequently Asked Questions (FAQ)

## Installation & Setup

### How do I install the assistant plugin?
The Assistant installs as a plugin for Antigravity or Claude Code:
* **Antigravity (`agy`):**
  * Linux/macOS: `./install.sh agy`
  * Windows (PowerShell): `.\install.ps1 -Type agy`
* **Claude Code (`claude`):**
  * Linux/macOS: `./install.sh claude`
  * Windows (PowerShell): `.\install.ps1 -Type claude`

### How do I activate or reload the plugin after installation?
* **Antigravity:** Restart your Antigravity / `agy` host session to load the new plugin.
* **Claude Code:** Inside an active Claude Code session, run `/reload-plugins` or restart `claude`.

### How do I update the assistant or add client libraries?
Use the platform update scripts from within the repository root:
* **Linux/macOS:**
  ```bash
  ./update.sh agy                   # Update Antigravity plugin
  ./update.sh claude                # Update Claude Code plugin
  ./update.sh agy --java --dotnet   # Add or update specific client libraries
  ./update.sh claude --all          # Include all client libraries
  ```
* **Windows (PowerShell):**
  ```powershell
  .\update.ps1 -Type agy
  .\update.ps1 -Type claude
  .\update.ps1 -Type agy -Java -Dotnet
  .\update.ps1 -Type claude -All
  ```

### How do I uninstall the plugin?
Use the native platform uninstallation mechanisms:
* **Antigravity:**
  * Linux/macOS:
    ```bash
    rm -rf ~/.gemini/config/plugins/google-ads-api-developer-assistant
    ```
  * Windows (PowerShell):
    ```powershell
    Remove-Item -Recurse -Force "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant"
    ```
  Then restart your Antigravity / `agy` host session.
* **Claude Code:**
  * Within an active session:
    ```text
    /plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  * Or from your terminal:
    ```bash
    claude plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  * *(Optional)* To remove the local marketplace registration:
    ```bash
    claude plugin marketplace remove google-ads-assistant-local
    ```

---

## Configuration & Credentials

### How do I configure my Google Ads API credentials?
The Assistant looks for credential files in your home directory (`$HOME`) during initialization and syncs them into an isolated `config/google-ads.yaml` file (with `0600` permissions):
* **Python:** `google-ads.yaml`
* **PHP:** `google_ads_php.ini`
* **Ruby:** `google_ads_config.rb`
* **Java:** `ads.properties`
* **.NET:** `App.config` / `google-ads.json`

All runtime API calls use `config/google-ads.yaml` directly rather than reading from `$HOME` on each execution. Refer to the official Google Ads API documentation for the specific structure and credential fields of each file.

### What is `config/assistant_config` and which file takes precedence?
Runtime settings for the assistant are stored in a single TOML-formatted file named `config/assistant_config`:
```toml
api_version = "v25"
customer_id = "1234567890"
execute_mutates = false
```
The assistant checks two locations in priority order (**first found wins**):
1. **Workspace configuration (Highest Precedence):** `./config/assistant_config` in your current working directory.
2. **Installed plugin configuration (Fallback):**
   * **Antigravity (`agy`):** `~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config`
   * **Claude Code (`claude`):** `plugins/google-ads-api-developer-assistant/config/assistant_config`

### How do I set a default customer ID?
Set `customer_id` in `config/assistant_config` (TOML format, e.g., `customer_id = "1234567890"`). You can then use prompts like *"Get my campaigns"* and the Assistant will automatically use this CID for requests.

### Where is the Google Ads API version configured?
The active API version is stored in `config/assistant_config` (`api_version = "v25"`). On installation, update, or when running `get_latest_api_version.py` / `sync_client_libs.py`, the assistant automatically discovers the latest stable release and updates `api_version` in `config/assistant_config` while preserving your `customer_id` and `execute_mutates` settings.

### How do I provide context from my existing application codebase?
Run your Antigravity (`agy`) or Claude Code (`claude`) session directly inside your application codebase directory (with the plugin installed globally via `./install.sh agy` or `./install.sh claude`), or reference your application files in your prompt. The Assistant's `PreInvocation` and `PreToolUse` hooks automatically resolve global plugin skills while preserving your local workspace context and `./config/assistant_config` overrides.

---

## Code Generation & Execution

### Which languages are supported for code generation and execution?
* **Default Execution Language:** The Assistant defaults to **Python** whenever executing code against the Google Ads API unless you explicitly ask for another language.
* **Python, PHP, and Ruby:** Supported for code generation and direct execution (when respective runtimes and credentials are configured).
* **Java and C# (.NET):** Supported for code generation. Generated code must be compiled and executed separately due to environment execution and security policies.

### Where is generated code and exported data saved?
* **Generated Code:** Saved to `saved/code/` within your workspace.
* **CSV Data Exports:** Saved to `saved/csv/` when requesting CSV outputs.
* **Diagnostic Reports & Dry-Run Receipts:** Saved to `saved/data/` (including `saved/data/last_dry_run.json` for verified mutation dry-runs).
* **Mutation Audit Trail:** Saved to `saved/logs/mutation_audit.jsonl` (append-only JSONL audit log of all dry-runs and live mutation executions).

### Can I mutate data (create/update/delete) using the Assistant?
By default, live mutations are **disabled** (`execute_mutates = false` in `config/assistant_config`), meaning the Assistant can generate mutation scripts and run safe `validate_only=True` dry-runs (`--dry-run`), but any live `--execute` call is blocked at both the `PreToolUse` hook and the execution runner.

To enable live mutations, set `execute_mutates = true` in `config/assistant_config` (or run `python3 config/config_init.py --execute-mutates true`). When enabled, every mutation must pass the mandatory **4-Step Human-in-the-Loop (HITL) Verification & Consequence Disclosure Protocol**:
1. **Step 1 — GAQL Before-State Lookup:** Queries current resource settings and 30-day spend/conversions to determine blast radius.
2. **Step 2 — Live API Dry-Run (`validate_only=True`):** Executes `--dry-run` via `run_mutation.py`, binds the script SHA-256 and serialized protobuf RPC payload SHA-256 into `saved/data/last_dry_run.json`, and prints the **Mutation & Consequence Verification Card**.
3. **Step 3 — Consequence Disclosure & User Confirmation:** Discloses the `Before -> After` state delta, reversibility, and financial/serving consequences, then waits for your approval.
4. **Step 4 — Hook-Gated Live Execution & Audit Log:** The `PreToolUse` hook verifies the receipt and hashes, triggers an interactive CLI confirmation prompt (`force_ask` in `agy`, `ask` in `claude`), executes the mutation with `ResponseContentType.MUTABLE_RESOURCE`, and records the result in `saved/logs/mutation_audit.jsonl`.

---

## Commands & Skills

### How do I validate a GAQL query?
You can dry-run and validate complex GAQL queries against API metadata and compatibility rules:
* **Antigravity (Natural Language):** Prefix your query with `validate:` (e.g., `validate: SELECT campaign.id FROM campaign WHERE ...`).
* **Claude Code:** Use the `/validate-gaql` slash command.

### How do I inspect Google Ads API resources, fields, or enums?
* **Antigravity (Natural Language):** *"Inspect Campaign resource"* or *"Show fields for ConversionActionType enum"*.
* **Claude Code:** Use `/inspect-object <resource_or_enum>`.

### How do I map accounts under a Manager Account (MCC)?
* **Antigravity (Natural Language):** *"Get all client customer IDs under manager 123-456-7890"*.
* **Claude Code:** Use `/get-cids <manager_cid>`.

### How do I troubleshoot offline conversion upload failures?
* **Antigravity (Natural Language):** *"Troubleshoot my conversions for customer 123-456-7890"*.
* **Claude Code:** Use `/troubleshoot-conversions`.
The assistant inspects upload summaries, pre-validates files, and writes detailed diagnostic reports to `saved/data/`.

### How do I generate Performance Max listing filters or URL exclusions?
* **Antigravity (Natural Language):** *"Create webpage exclusion filters for my PMax campaign"*.
* **Claude Code:** Use `/pmax-filter`.

### How do I get structured explanations or step-by-step guidance?
In Claude Code, use dedicated explanation slash commands:
* `/explain <concept>`: Delivers a 4-part structured explanation (Big Picture, Analogy, Interconnectedness, Simple Language).
* `/step-by-step <task>`: Provides an actionable multi-phase implementation breakdown.
* `/assistant-tutorial`: Launches an interactive walkthrough of the assistant capabilities.

---

## Troubleshooting & Prerequisites

### What are the system requirements?
1. **Python:** Python >= 3.11 installed and available on your system `PATH`.
2. **Platform CLI:** Antigravity CLI (`agy` / `antigravity`) or Claude Code CLI (`claude` with Node.js >= 18).
3. **Google Ads API Access:** A developer token and configured credentials in `$HOME`.

### Why does the assistant sometimes suggest deprecated fields?
The underlying language model may have been trained on older API versions. However, the Assistant automatically checks local client library definitions and locks the active API version via `config/assistant_config`. If an API error occurs during execution, the assistant uses client library context to self-correct automatically.
