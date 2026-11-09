# Google Ads API Developer Assistant v4.1.0

Version 4.1.0 of the Google Ads API Developer Assistant supports **Antigravity** (`agy`) and **Claude Code** (`claude`). It includes a unified TOML configuration file (`config/assistant_config`) and a 4-Step Human-in-the-Loop (HITL) mutation protocol. This protocol allows only `create` and `update` operations and blocks all delete (`remove`) operations.

## Upgrade from 4.0.0 to 4.1.0

You can upgrade from `v4.0.0` to `v4.1.0` in place. The update script keeps your credentials (`~/google-ads.yaml`) and moves your `v4.0.0` configuration files (`config/customer_id`, `config/customer_id.txt`, and `config/api_version.txt`) into `config/assistant_config`.

1. **Run the Update Script for Your Platform:**
   Go to the root directory of your `google-ads-api-developer-assistant` repository and run the command for your platform:
   * **Antigravity (`agy`) — Linux / macOS:**
     ```bash
     ./update.sh agy
     ```
   * **Claude Code (`claude`) — Linux / macOS:**
     ```bash
     ./update.sh claude
     ```
   * **Antigravity (`agy`) — Windows (PowerShell):**
     ```powershell
     .\update.ps1 -Type agy
     ```
   * **Claude Code (`claude`) — Windows (PowerShell):**
     ```powershell
     .\update.ps1 -Type claude
     ```
   *(Optional)* Add `--all` (or `-All` on Windows) to update all cloned client libraries at the same time.

2. **Check Your Settings in `config/assistant_config`:**
   The update script creates `config/assistant_config` (in TOML format). It copies your `customer_id` from `config/customer_id` (or `config/customer_id.txt`) and finds the latest `api_version`:
   ```toml
   api_version = "v26"
   customer_id = "1234567890"
   execute_mutates = false
   ```
   *(Optional)* After the script creates `config/assistant_config`, you can delete the old `config/customer_id`, `config/customer_id.txt`, and `config/api_version.txt` files.

3. **Restart Your Host Session:**
   * **Antigravity (`agy`):** Restart your Antigravity session.
   * **Claude Code (`claude`):** Run `/reload-plugins` in your active session, or restart `claude`.

---

If you upgrade from version 2.x or 3.x, follow the steps below.

## 1. Make a Backup of Your Custom Files
Copy your custom code and saved files to a safe directory outside the repository:
* **v2.x paths:** `saved_code/` and `saved_csv/`
* **v3.x paths:** `saved/code/` and `saved/csv/`

## 2. Delete Old Configuration Files
* If the `.agents/settings.json` file exists, delete it. The plugin system and the `config/` directory now control the configuration.
* **Credentials Note:** The update keeps the API credential files in your home directory (for example, `google-ads.yaml` for Python, `google_ads_php.ini` for PHP, and `google_ads_config.rb` for Ruby). You do not need to create them again.

## 3. Update the Repository
Get the latest changes from git, or clone the repository again:
```bash
git pull origin main
```
*(A new clone gives you a clean workspace.)*

## 4. Run the Installation Script for Your Platform

By default, the plugin includes the **Python** client library. Use optional flags (`--php`, `--ruby`, `--java`, `--dotnet`, or `--all`) to add other client libraries.

### Antigravity (`agy`)
* **Linux / macOS:**
  ```bash
  ./install.sh agy
  # Or include more client libraries:
  ./install.sh agy --java --dotnet
  ```
* **Windows (PowerShell):**
  ```powershell
  .\install.ps1 -Type agy
  # Or include more client libraries:
  .\install.ps1 -Type agy -Java -Dotnet
  ```
* **Start the Plugin:** Restart your Antigravity / `agy` session to load the updated plugin.

### Claude Code (`claude`)
* **Linux / macOS:**
  ```bash
  ./install.sh claude
  # Or include more client libraries:
  ./install.sh claude --php --dotnet
  ```
* **Windows (PowerShell):**
  ```powershell
  .\install.ps1 -Type claude
  # Or include more client libraries:
  .\install.ps1 -Type claude -Php -Dotnet
  ```
* **Start the Plugin:** Run `/reload-plugins` in your active Claude Code session, or restart `claude`.

## 5. Update and Add Languages After Installation
Run the update script at any time to update client libraries or add more languages:
* **Linux / macOS:**
  ```bash
  ./update.sh agy --all          # Update Antigravity plugin with all client libraries
  ./update.sh claude --dotnet    # Add or update the .NET client library for Claude Code
  ```
* **Windows (PowerShell):**
  ```powershell
  .\update.ps1 -Type agy -All
  .\update.ps1 -Type claude -Dotnet
  ```

## 6. Optional Configuration (`config/assistant_config`)
The `config/assistant_config` file stores all assistant settings in TOML format:
```toml
api_version = "v26"
customer_id = "12345678"
execute_mutates = false
```
* **Default Customer ID (`customer_id`):** Set your default customer ID (for example, `customer_id = "1234567890"`).
* **API Version (`api_version`):** The assistant finds the latest stable API version and writes it to `config/assistant_config`. Edit this value if you want to use a specific API version.
* **Live Mutations (`execute_mutates`):** Set `execute_mutates = true` or `false` (the default is `false`). This setting controls if the 4-Step HITL verification flow allows live Google Ads API `create` and `update` mutations. Delete (`remove`) operations are always blocked.