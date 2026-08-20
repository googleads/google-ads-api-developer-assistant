# Google Ads API Developer Assistant v4.0.0

v4.0.0 is a major release of the Google Ads API Developer Assistant transitioning to multi-platform plugin support for both **Antigravity** (`agy`) and **Claude Code** (`claude`).

If you are upgrading from a previous version (v2.x or v3.x), follow these steps:

## 1. Backup Custom Data
Copy any custom code or saved output to a secure location outside the repository:
* **v2.x legacy paths:** `saved_code/` and `saved_csv/`
* **v3.x paths:** `saved/code/` and `saved/csv/`

## 2. Remove Legacy Configuration
* Delete the legacy `.agents/settings.json` file if it exists. Configuration is now managed via the plugin system and `config/` directory.
* **Credentials Note:** Your API credential files in your home directory (e.g., `google-ads.yaml` for Python, `google_ads_php.ini` for PHP, `google_ads_config.rb` for Ruby) are preserved and do not need to be recreated.

## 3. Update the Repository
Pull the latest changes from git or re-clone the repository:
```bash
git pull origin main
```
*(As a best practice, a fresh clone is recommended to ensure a clean workspace.)*

## 4. Run the Platform Installation Script

By default, the **Python** client library is included in the plugin. You can also include additional client libraries (`--php`, `--ruby`, `--java`, `--dotnet`, or `--all`).

### Antigravity (`agy`)
* **Linux / macOS:**
  ```bash
  ./install.sh agy
  # Or include additional client libraries:
  ./install.sh agy --java --dotnet
  ```
* **Windows (PowerShell):**
  ```powershell
  .\install.ps1 -Type agy
  # Or include additional client libraries:
  .\install.ps1 -Type agy -Java -Dotnet
  ```
* **Activation:** Restart your Antigravity / `agy` host session to load the updated plugin.

### Claude Code (`claude`)
* **Linux / macOS:**
  ```bash
  ./install.sh claude
  # Or include additional client libraries:
  ./install.sh claude --php --dotnet
  ```
* **Windows (PowerShell):**
  ```powershell
  .\install.ps1 -Type claude
  # Or include additional client libraries:
  .\install.ps1 -Type claude -Php -Dotnet
  ```
* **Activation:** In an active Claude Code session, run `/reload-plugins` or restart `claude`.

## 5. Post-Installation: Updating and Adding Languages
Use the update script at any time to sync client libraries or add additional languages:
* **Linux / macOS:**
  ```bash
  ./update.sh agy --all          # Update Antigravity plugin with all client libraries
  ./update.sh claude --dotnet    # Add / update .NET client library for Claude Code
  ```
* **Windows (PowerShell):**
  ```powershell
  .\update.ps1 -Type agy -All
  .\update.ps1 -Type claude -Dotnet
  ```

## 6. Optional Configuration
* **Default Customer ID:** Specify your default customer ID in `config/customer_id` (e.g., `1234567890`).
* **API Version:** The latest stable API version is automatically detected and cached in `config/api_version.txt`. You can edit this file at any time to lock or override the target API version.