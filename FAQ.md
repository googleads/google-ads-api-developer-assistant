# Frequently Asked Questions (FAQ)

## Installation & Setup

### How do I install the assistant plugin?
Run the installation script for Antigravity or Claude Code:
* **Antigravity (`agy`):**
  * Linux/macOS: `./install.sh agy`
  * Windows (PowerShell): `.\install.ps1 -Type agy`
* **Claude Code (`claude`):**
  * Linux/macOS: `./install.sh claude`
  * Windows (PowerShell): `.\install.ps1 -Type claude`

### How do I start or reload the plugin after installation?
* **Antigravity:** Restart your Antigravity / `agy` session to load the new plugin.
* **Claude Code:** Run `/reload-plugins` in an active Claude Code session, or restart `claude`.

### How do I update the assistant or add client libraries?
Run the update script from the root directory of the repository:
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
Use the uninstallation command for your platform:
* **Antigravity:**
  * Linux/macOS:
    ```bash
    rm -rf ~/.gemini/config/plugins/google-ads-api-developer-assistant
    ```
  * Windows (PowerShell):
    ```powershell
    Remove-Item -Recurse -Force "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant"
    ```
  Then restart your Antigravity / `agy` session.
* **Claude Code:**
  * In an active session:
    ```text
    /plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  * Or in your terminal:
    ```bash
    claude plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  * *(Optional)* Remove the local marketplace registration:
    ```bash
    claude plugin marketplace remove google-ads-assistant-local
    ```
  * Delete the local marketplace plugin directory:
    * Linux/macOS:
      ```bash
      rm -rf ~/.claude/plugins/google-ads-assistant-local
      ```
    * Windows (PowerShell):
      ```powershell
      Remove-Item -Recurse -Force "$HOME\.claude\plugins\google-ads-assistant-local"
      ```

---

## Configuration & Credentials

### How do I configure my Google Ads API credentials?
At startup, the assistant looks for credential files in your home directory (`$HOME`). It copies them into an isolated `config/google-ads.yaml` file (with `0600` permissions):
* **Python:** `google-ads.yaml`
* **PHP:** `google_ads_php.ini`
* **Ruby:** `google_ads_config.rb`
* **Java:** `ads.properties`
* **.NET:** `App.config` / `appsettings.json`

All runtime API calls read `config/google-ads.yaml` directly instead of `$HOME`. See the Google Ads API documentation for the required fields in each file.

### What is `config/assistant_config` and which file has priority?
The `config/assistant_config` file stores runtime settings in TOML format:
```toml
api_version = "v26"
customer_id = "1234567890"
execute_mutates = false
```
The assistant checks two locations in this order and uses the first file it finds:
1. **Workspace configuration (First Priority):** `./config/assistant_config` in your current working directory.
2. **Installed plugin configuration (Fallback):**
   * **Antigravity (`agy`):** `~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config`
   * **Claude Code (`claude`):** `~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/assistant_config`

### How do I set a default customer ID?
Set `customer_id` in `config/assistant_config` (for example, `customer_id = "1234567890"`). When you enter a prompt such as *"Get my campaigns"*, the assistant uses this customer ID automatically.

### Where is the Google Ads API version configured?
The `config/assistant_config` file stores the active API version (`api_version = "v26"`). When you install, update, or run `get_latest_api_version.py` or `sync_client_libs.py`, the assistant finds the latest stable version. It updates `api_version` in `config/assistant_config` and keeps your `customer_id` and `execute_mutates` values.

### How do I use the assistant with my existing application code?
Install the plugin globally with `./install.sh agy` or `./install.sh claude`. Then start your Antigravity (`agy`) or Claude Code (`claude`) session inside your application directory, or include your file paths in your prompt. The `PreInvocation` and `PreToolUse` hooks find the global plugin skills and keep your local `./config/assistant_config` settings.

---

## Code Generation & Execution

### Which languages can generate and run code?
* **Default Execution Language:** The assistant uses **Python** to run Google Ads API code unless you ask for another language.
* **Python, PHP, and Ruby:** The assistant can generate and run code in these languages if you install their runtimes and configure their credentials.
* **Java and C# (.NET):** The assistant can generate code in these languages. You must compile and run the generated code yourself.

### Where does the assistant save generated code and exported data?
* **Generated Code:** `saved/code/` in your workspace.
* **CSV Data Exports:** `saved/data/` when you ask for CSV output.
* **Diagnostic Reports & Dry-Run Receipts:** `saved/data/` (including `saved/data/last_dry_run.json` for verified mutation dry-runs).
* **Mutation Audit Log:** `saved/logs/mutation_audit.jsonl` (an append-only JSONL log of all dry-runs and live mutations).

### Can I change data (create, update, or delete) with the Assistant?
Only **`create`** and **`update`** mutations are allowed. Delete (`remove`) operations are always blocked (`BLOCKED_PROHIBITED_DELETION`). To stop ad serving without deleting a resource, update its `status` to `PAUSED`.

By default, live mutations are **off** (`execute_mutates = false` in `config/assistant_config`). The assistant can generate mutation scripts and run safe `validate_only=True` dry-runs (`--dry-run`). However, the `PreToolUse` hook and the execution runner block any live `--execute` call.

To allow live `create` and `update` mutations, set `execute_mutates = true` in `config/assistant_config` (or run `python3 plugins/google-ads-api-developer-assistant/config/config_init.py --execute-mutates true`). Each mutation must complete this 4-step verification flow:
1. **Step 1 — GAQL Before-State Lookup:** Reads current resource settings and 30-day spend and conversions.
2. **Step 2 — Live API Dry-Run (`validate_only=True`):** Runs `--dry-run` with `run_mutation.py`, writes the script SHA-256 and protobuf RPC payload SHA-256 to `saved/data/last_dry_run.json`, and shows the **Mutation & Consequence Verification Card**.
3. **Step 3 — Consequence Disclosure & User Confirmation:** Shows the `Before -> After` state changes, reversibility, and financial or serving effects. Then it waits for your approval.
4. **Step 4 — Hook-Gated Live Execution & Audit Log:** The `PreToolUse` hook checks the receipt and SHA-256 hashes, shows a CLI confirmation prompt (`force_ask` in `agy`, `ask` in `claude`), runs the mutation with `ResponseContentType.MUTABLE_RESOURCE`, and writes the result to `saved/logs/mutation_audit.jsonl`.

---

## Commands & Skills

### How do I validate a GAQL query?
You can check GAQL queries against API metadata and compatibility rules:
* **Antigravity (Natural Language):** Put `validate:` before your query (for example, `validate: SELECT campaign.id FROM campaign WHERE ...`).
* **Claude Code:** Run `/validate-gaql`.

### How do I check Google Ads API resources, fields, or enums?
* **Antigravity (Natural Language):** Enter *"Inspect Campaign resource"* or *"Show fields for ConversionActionType enum"*.
* **Claude Code:** Run `/inspect-object <resource_or_enum>`.

### How do I list accounts under a Manager Account (MCC)?
* **Antigravity (Natural Language):** Enter *"Get all client customer IDs under manager 123-456-7890"*.
* **Claude Code:** Run `/get-cids <manager_cid>`.

### How do I troubleshoot offline conversion upload errors?
* **Antigravity (Natural Language):** Enter *"Troubleshoot my conversions for customer 123-456-7890"*.
* **Claude Code:** Run `/troubleshoot-conversions`.
The assistant checks upload summaries, validates CSV files, and writes diagnostic reports to `saved/data/`.

### How do I create Performance Max listing filters or URL exclusions?
* **Antigravity (Natural Language):** Enter *"Create webpage exclusion filters for my PMax campaign"*.
* **Claude Code:** Run `/pmax-filter`.

### How do I get explanations or step-by-step instructions?
In Claude Code, use these slash commands:
* `/explain <concept>`: Gives a 4-part explanation (Big Picture, Analogy, Interconnectedness, Simple Language).
* `/step-by-step <task>`: Gives a numbered list of implementation steps.
* `/assistant-tutorial`: Starts an interactive guide to the assistant features.

---

## Troubleshooting & Requirements

### What are the system requirements?
1. **Python:** Install Python >= 3.11 and add it to your system `PATH`.
2. **Platform CLI:** Install the Antigravity CLI (`agy` / `antigravity`) or the Claude Code CLI (`claude` with Node.js >= 18).
3. **Google Ads API Access:** Put your credential file in `$HOME`.

### Why does the assistant sometimes suggest old fields?
The language model may know older API versions. To prevent errors, the assistant checks your local client library files and uses the active API version from `config/assistant_config`. If an API error occurs, the assistant reads the local client library definitions and fixes the query or code.
