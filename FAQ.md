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
The Assistant looks for configuration files in your home directory (`$HOME`):
* **Python:** `google-ads.yaml`
* **PHP:** `google_ads_php.ini`
* **Ruby:** `google_ads_config.rb`
* **Java:** `ads.properties`
* **.NET:** `App.config` / `google-ads.json`

Refer to the official Google Ads API documentation for the specific structure and credential fields of each file.

### How do I set a default customer ID?
Enter your customer ID number directly into `config/customer_id` (e.g., `1234567890`). You can then use prompts like *"Get my campaigns"* and the Assistant will automatically use this CID for requests.

### Where is the Google Ads API version configured?
The active API version is cached in `config/api_version.txt`. On your first run in a session, the assistant automatically discovers the latest stable release and confirms it with you. If you need to refresh or lock a specific version, edit or delete `config/api_version.txt`.

### How do I provide context from my existing application codebase?
You can supply your project directory to the update script using the `--context_dir` flag:
* **Linux/macOS:**
  ```bash
  ./update.sh agy --context_dir /path/to/your/codebase
  ```
* **Windows (PowerShell):**
  ```powershell
  .\update.ps1 -Type agy -ContextPath "C:\path\to\your\codebase"
  ```
This allows the Assistant to include your application architecture and conventions in its reasoning when generating code examples in your chosen language.

---

## Code Generation & Execution

### Which languages are supported for code generation and execution?
* **Python, PHP, and Ruby:** Supported for code generation and direct execution (when respective runtimes and credentials are configured).
* **Java and C# (.NET):** Supported for code generation. Generated code must be compiled and executed separately due to environment execution and security policies.

### Where is generated code and exported data saved?
* **Generated Code:** Saved to `saved/code/` within your workspace.
* **CSV Data Exports:** Saved to `saved/csv/` when requesting CSV outputs.
* **Diagnostic & Troubleshooting Reports:** Saved to `saved/data/`.

### Can I mutate data (create/update/delete) using the Assistant?
The Assistant enforces a strict read-only execution policy. While it can generate code for mutate operations (e.g., creating campaigns, modifying ad groups, managing budgets), it will **not** execute mutate calls directly. Generated mutate code is saved to `saved/code/` for you to review and run manually outside the assistant.

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
1. **Python:** Python >= 3.10 installed and available on your system `PATH`.
2. **Platform CLI:** Antigravity CLI (`agy` / `antigravity`) or Claude Code CLI (`claude` with Node.js >= 18).
3. **Google Ads API Access:** A developer token and configured credentials in `$HOME`.

### Why does the assistant sometimes suggest deprecated fields?
The underlying language model may have been trained on older API versions. However, the Assistant automatically checks local client library definitions and locks the active API version via `config/api_version.txt`. If an API error occurs during execution, the assistant uses client library context to self-correct automatically.
