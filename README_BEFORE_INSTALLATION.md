# Google Ads API Developer Assistant v4.1.0

v4.1.0 is the latest release of the Google Ads API Developer Assistant featuring multi-platform plugin support for both **Antigravity** (`agy`) and **Claude Code** (`claude`), unified TOML configuration (`config/assistant_config`), and the 4-Step HITL Mutation Verification & Consequence Disclosure Protocol.

## Upgrade from 4.0.0 to 4.1.0

Upgrading from `v4.0.0` to `v4.1.0` is an in-place update. Your existing credentials (`~/google-ads.yaml`) and `v4.0.0` configuration files (`config/customer_id`, `config/customer_id.txt`, and `config/api_version.txt`) are preserved and automatically migrated into `config/assistant_config`.

1. **Run the Update Script for Your Platform:**
   From the root of your `google-ads-api-developer-assistant` repository, run:
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

2. **Verify Migrated Settings in `config/assistant_config`:**
   The update script automatically creates `config/assistant_config` (TOML), migrating any custom `customer_id` from `config/customer_id` (or `config/customer_id.txt`) and detecting the latest `api_version`:
   ```toml
   api_version = "v25"
   customer_id = "1234567890"
   execute_mutates = false
   ```
   *(Optional)* Once `config/assistant_config` is created, you may remove legacy `config/customer_id`, `config/customer_id.txt`, and `config/api_version.txt` files.

3. **Reload Your Host Session:**
   * **Antigravity (`agy`):** Restart your Antigravity session.
   * **Claude Code (`claude`):** Run `/reload-plugins` in your active session or restart `claude`.

---

If you are upgrading from an older version (v2.x or v3.x), follow these steps:

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

## 6. Optional Configuration (`config/assistant_config`)
All assistant settings are stored in a single TOML configuration file at `config/assistant_config`:
```toml
api_version = "v25"
customer_id = "12345678"
execute_mutates = false
```
* **Default Customer ID (`customer_id`):** Specify your default customer ID (e.g., `customer_id = "1234567890"`).
* **API Version (`api_version`):** The latest stable API version is automatically detected and stored in `config/assistant_config`. You can edit this value at any time to lock or override the target API version.
* **Live Mutations (`execute_mutates`):** Set `execute_mutates = true` or `false` (defaults to `false`) to control whether live Google Ads API mutations are permitted through the 4-Step HITL verification flow.