# FAQ

## How do I configure my Google Ads API credentials?
The Assistant looks for configuration files in your home directory (`$HOME`). 
- **Python**: `google-ads.yaml`
- **PHP**: `google_ads_php.ini`
- **Ruby**: `google_ads_config.rb`
- **Java**: `ads.properties`
- **.NET**: `App.config` / `google-ads.json`

Refer to the official Google Ads API documentation for the specific structure of each file.

## How do I set a default customer ID?
Enter your customer ID number directly into `config/customer_id` (e.g., `1234567890`). You can then use prompts like *"Get my campaigns"* and the Assistant will automatically use this CID for requests.

## How do I install the assistant plugin?
The Assistant installs as a plugin for Antigravity or Claude Code:
- **Antigravity**:
  - Linux/macOS: `./install.sh agy`
  - Windows: `.\install.ps1 -Type agy`
- **Claude Code**:
  - Linux/macOS: `./install.sh claude`
  - Windows: `.\install.ps1 -Type claude`

## Which languages are supported for code generation and execution?
- **Python**: Supported for code generation and direct execution.
- **PHP and Ruby**: Supported for code generation.
- **Java and C# (.NET)**: Supported for code generation.

## How do I update the assistant or add client libraries?
Use the platform update scripts from within the repository root:
- **Linux/macOS**:
  ```bash
  ./update.sh agy                   # Update Antigravity plugin
  ./update.sh claude                # Update Claude Code plugin
  ./update.sh agy --java --dotnet   # Add or update specific client libraries
  ```
- **Windows**:
  ```powershell
  .\update.ps1 -Type agy
  .\update.ps1 -Type claude
  .\update.ps1 -Type agy -Java -Dotnet
  ```

## How do I uninstall the plugin?
Use the native platform uninstallation mechanisms:
- **Antigravity**:
  - Linux/macOS:
    ```bash
    rm -rf ~/.gemini/config/plugins/google-ads-api-developer-assistant
    ```
  - Windows (PowerShell):
    ```powershell
    Remove-Item -Recurse -Force "$HOME\.gemini\config\plugins\google-ads-api-developer-assistant"
    ```
  Then restart your Antigravity / agy host to apply changes.
- **Claude Code**:
  - Within an active session:
    ```
    /plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  - Or from the terminal:
    ```bash
    claude plugin uninstall google-ads-api-developer-assistant@google-ads-assistant-local
    ```
  - *(Optional)* To remove the local marketplace registration:
    ```bash
    claude plugin marketplace remove google-ads-assistant-local
    ```

## Can I mutate data (create/update/delete) using the Assistant?
The Assistant enforces a strict read-only execution policy. While it can generate code for mutate operations, it will not execute mutate calls directly for safety reasons. Generated code is saved in `~/saved/code/` for you to review and execute manually.

## How do I create a report for conversion upload issues that I can share with Google Support?
You can use the `troubleshoot-conversions` skill (or `/troubleshoot-conversions` slash command in Claude Code) to investigate offline conversion upload failures, validate CSV formats, and generate a structured diagnostic report. Diagnostic reports are saved in `~/saved/data/`.

## Where is the Google Ads API version configured?
The active API version is cached in `config/api_version.txt`. On your first run in a session, the assistant automatically discovers the latest stable release and confirms it with you. If you need to refresh or force a specific version, simply edit or delete `config/api_version.txt`.
