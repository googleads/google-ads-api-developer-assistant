# Google Ads API Developer Assistant v4.0.0

v4.0.0 is a major release of the Google Ads API Developer Assistant transitioning to multi-platform plugin support (Antigravity and Claude Code).

If you are upgrading from a previous version:

1. **Backup custom data:** Copy any custom code or data from `saved/code/` and `saved/csv/` to a secure location.
2. **Remove legacy configuration:** Delete the legacy `.agents/settings.json` file if it exists, as configuration is now managed globally by `antigravity`.
3. **Update the repository:** Pull the latest changes or re-clone the repository.
4. **Run the installation script:** Run `./install.sh agy` or `./install.sh claude` (Linux/macOS) / `.\install.ps1 -Type agy` or `.\install.ps1 -Type claude` (Windows) to install the assistant plugin.
5. **Update and add languages:** Use `./update.sh <agy|claude>` or `.\update.ps1 -Type <agy|claude>` to update the plugin and client libraries (e.g. `./update.sh agy --java --dotnet`).