# Google Ads API Developer Assistant

**TL;DR:** This assistant lets you interact with the Google Ads API using natural language. Ask questions, generate GAQL and code in several languages, and execute API calls directly in your terminal.

## Overview

The Google Ads API Developer Assistant streamlines workflows for developers working with the Google Ads API. Use natural language prompts to:

*   Get answers to Google Ads API questions.
*   Construct Google Ads Query Language (GAQL) queries.
*   Generate executable code in several languages using our client libraries for context.
*   Retrieve and display data from the API.

This assistant is powered by the **Antigravity** (v4.0.0) and **Claude Code** agent frameworks and leverages `AGENTS.md` / `CLAUDE.md` files, native slash commands, and custom **Skills** to deliver persistent context, robust safety constraints, and automated execution pipelines.

## Agentic Design & Approach

The Assistant uses a structured hierarchy of instruction files, slash commands, and specialized domain tools to ensure safe, precise, and highly competent interactions with the Google Ads API across supported agent environments.

### 1. Unified Context via `AGENTS.md` & `CLAUDE.md`
The master configuration files act as the system contract for the assistant:
*   **Version Cache Protocol**: Automatically discovers and locks the latest active API version (cached in `config/api_version.txt`).
*   **Version Parity Enforcement**: Verifies parity between the runtime `google-ads` Python package and local `client_libs/google-ads-python` source-of-truth definitions, issuing warnings on discrepancies.
*   **Code Generation Pipeline**: Passes all generated Python code through strict `ruff` linting before saving or displaying it.
*   **Programmatic GAQL Validation**: Evaluates queries against field metadata and compatibility boundaries.
*   **Safety Constraints**: Strictly prohibits running unreviewed mutate operations directly.

### 2. Domain-Specific "Skills" & Native Commands
Rather than relying on generic AI completions, the assistant is empowered with specialized, test-backed tool directories under `plugins/google-ads-api-developer-assistant/skills/` and native slash commands under `plugins/google-ads-api-developer-assistant/commands/`.

Key capabilities support dual invocation (natural language prompts in Antigravity or dedicated slash commands in Claude Code):
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

By default, Python is used for code generation.  As of v2.3.0 you can provide context from your project files using the `context_dir` flag: `./update.sh --context_dir /path/to/your/codebase`. This allows Gemini to include your application logic in its reasoning when creating responses.  This feature enables the Assistant to produce saved code examples in your chosen language, providing support even when an official client library is unavailable.
   * Before requesting code output, tell the Assistant: `write saved code examples in <language of your application>`

## Prerequisites

1.  Familiarity with Google Ads API concepts and authentication.
2.  A Google Ads API developer token.
3.  A configured credentials file in your home directory if using Python (`google-ads.yaml`), PHP (`google_ads_php.ini`), or Ruby (`google_ads_config.rb`).
4.  Antigravity or Claude Code environment configured.
5.  A local clone of each client library for the languages you want to use. `install.sh` (Linux/macOS) or `install.ps1` (Windows) can set this up for you.
6.  Python >= 3.10 installed and available on your system PATH. This is required for executing the default generated Python code directly.

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
    *Installs plugin to `~/.gemini/config/plugins/google-ads-api-developer-assistant`.*
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
    *Installs plugin to `%USERPROFILE%\.gemini\config\plugins\google-ads-api-developer-assistant`.*
    *To include additional client libraries: `.\install.ps1 -Type agy -Php -Ruby -Dotnet`.*

*   **Claude Code (Windows - PowerShell):**
    ```powershell
    .\install.ps1 -Type claude
    ```
    *Registers the local marketplace and installs the plugin into Claude Code via Claude CLI.*
    *To include additional client libraries: `.\install.ps1 -Type claude -Php -Ruby -Dotnet`.*

---

4.  **Configure Credentials:** Make sure your API credentials configuration files are in your `$HOME` directory. Each language has its own configuration file naming convention and structure. 
5.  **Optional: Default Customer ID:** To set a default customer ID, enter your customer ID in `config/customer_id` (e.g., `1234567890`). You can then use prompts like *"Get my campaigns"* and the Assistant will use the CID for the request.
6.  **Google Ads API Version Validation:** On your first run in a session, the assistant will automatically identify the latest stable Google Ads API version and ask you to confirm it. Once confirmed, this version is cached in [api_version.txt](file:///usr/local/google/home/rwh/google-ads-api-developer-assistant/config/api_version.txt) and used for all subsequent prompts. If you need to force a version change or refresh the cache, simply delete or edit the `config/api_version.txt` file.

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

The Assistant includes automated synchronization tools to ensure your local client libraries, protobuf definitions, and API version metadata remain aligned with upstream releases on GitHub.

### 1. Update Check & Confirmation at Session Startup
Whenever an assistant session starts in Antigravity or Claude Code, the assistant executes an automated **"Validate Before Act & Interactive Sync"** directive:
* It checks both the **Assistant repository itself** and local **client libraries** (`client_libs/`) against the latest upstream GitHub releases in check-only mode (`--check_only`).
* If newer assistant releases or client library updates are detected, the assistant prompts you with the available updates and asks for confirmation before downloading:
  > *"New updates are available on GitHub (e.g., google-ads-api-developer-assistant 4.0.0, google-ads-python 25.1.0 -> 26.0.0). Would you like to upgrade now?"*
* If you confirm, it automatically synchronizes the codebases and refreshes `config/api_version.txt`. If you decline, it proceeds with your currently installed versions.

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
* **Automated Parity Checks:** Tool scripts (such as `inspect_object.py`) automatically compare the installed environment package version (`importlib.metadata.version('google-ads')`) against the local `client_libs/google-ads-python` version metadata (`pyproject.toml` / `ChangeLog`).
* **Warning Directives:** If a version mismatch is detected, the Assistant and inspection tools output an explicit warning banner:
  ```text
  WARNING: Installed google-ads package version (<installed_version>) does not match client_libs/google-ads-python version (<client_libs_version>) used for protobuf inspection. Schema inspection or API calls may encounter field discrepancies.
  ```
* **Resolving Mismatches:**
  * Synchronize client libraries to latest: `/sync-client-libs` (or prompt *"Sync client libraries"*).
  * Upgrade the runtime Python package: `pip install --upgrade google-ads` (or within virtualenv: `source .venv/bin/activate && pip install --upgrade google-ads`).
  * Perform a complete update: `./update.sh agy --all` or `./update.sh claude --all`.


## Directory Structure

*   `plugins/google-ads-api-developer-assistant/`: Source directory for the assistant plugin.
*   `plugins/google-ads-api-developer-assistant/commands/`: Native slash commands for Claude Code.
*   `plugins/google-ads-api-developer-assistant/skills/`: Assistant skills (GAQL analyzer, proto inspect, etc.).
*   `plugins/google-ads-api-developer-assistant/rules/`: Agent behavioral rules and protocols.
*   `plugins/google-ads-api-developer-assistant/sidecars/`: Background sidecar microservices.
*   `plugins/google-ads-api-developer-assistant/client_libs/`: Cloned client libraries.
*   `plugins/google-ads-api-developer-assistant/mcp_config.json`: Model Context Protocol configuration.
*   `config/`: Configuration files (e.g. `api_version.txt`, `customer_id`).

## Plugin Architecture

To learn more about how Antigravity and Claude define plugins, see the [Antigravity plugin specification](https://antigravity.google/docs/cli/plugins/) and the [Claude plugin specification](https://github.com/anthropics/knowledge-work-plugins).

## Mutate Operations

The Assistant is designed to generate code for mutate operations (e.g., creating campaigns, adding users) but will **not** execute them. This execution policy ensures you have full control over any changes to your Google Ads account. You must review the generated code for accuracy and execute it manually outside of the Assistant.

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
