# Google Ads API Developer Assistant v3.0.0

v3.0.0 is a major release of the Google Ads API Developer Assistant transitioning to the **antigravity** agent framework.

If you are upgrading from a previous version (v2.x):

1. **Backup custom data:** Copy any custom code or data from `saved/code/` and `saved/csv/` to a secure location.
2. **Remove legacy configuration:** Delete the legacy `.agents/settings.json` file if it exists, as configuration is now managed globally by `antigravity`.
3. **Update the repository:** Pull the latest changes or re-clone the repository. As a best practice, we suggest re-cloning.
4. **Run the installation script:** Run `./install.sh agy` or `./install.sh claudecode` (Linux/macOS) / `.\install.ps1 -Target agy` or `.\install.ps1 -Target claudecode` (Windows) to install the assistant plugin.
5. **Update and add languages:** Use `./update.sh <agy|claudecode>` or `.\update.ps1 -Target <agy|claudecode>` to update the plugin and client libraries (e.g. `./update.sh agy --java --dotnet`).