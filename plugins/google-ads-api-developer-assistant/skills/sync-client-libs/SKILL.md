---
name: sync-client-libs
description: Discovers Google Ads client libraries under client_libs, verifies installed versions against GitHub latest releases, and automatically updates outdated codebases.
---

# Sync Client Libraries Skill

Use this skill to automatically discover, verify, and update all Google Ads client libraries located in `client_libs/` against their latest upstream releases on GitHub.

## Overview

The client library sync tool inspects each codebase under `client_libs/` (e.g., `google-ads-python`, `google-ads-php`, `google-ads-ruby`, `google-ads-java`, `google-ads-dotnet`), determines the locally installed release version, fetches the latest release tag from GitHub, and automatically synchronizes the codebase if the local installation is outdated.

## CLI Usage

### Check / Dry-Run (No modifications)
```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/sync-client-libs/scripts/sync_client_libs.py" --check_only
```

### Automated Update
```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/sync-client-libs/scripts/sync_client_libs.py"
```

### Output Structured JSON
```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/sync-client-libs/scripts/sync_client_libs.py" --json
```

### Options Reference

| Flag | Short | Description |
| :--- | :--- | :--- |
| `--check_only` | `--dry_run` | Check versions and report status without modifying any files. |
| `--force` | | Force re-syncing/updating codebases even if versions match. |
| `--client_libs_dir` | `-d` | Explicit path to `client_libs` directory (auto-detected if omitted). |
| `--library` | `-l` | Filter to target a specific library (e.g. `google-ads-python`). |
| `--upgrade_system` | | Upgrade `google-ads` in Python system site-packages if mismatched. |
| `--json` | | Output results in JSON format for automated ingestion. |

## 5-Step System Site-Directory & Client Library Upgrade Protocol

At session startup or when checking for client library updates, follow this exact 5-step workflow:
1. **Check Site-Directory Version:** Inspect the Python site-packages directory (`site.getsitepackages()` and `importlib.metadata.version("google-ads")`) to detect the installed runtime version of `google-ads`.
2. **Check Latest GitHub Version:** Fetch the latest release tag of the client library on GitHub (`googleads/google-ads-python/releases/latest`).
3. **Prompt User When Site Version `<` GitHub Version:** If the site directory (or `client_libs/google-ads-python`) has a version `<` the GitHub version, prompt the user and ask if they want to upgrade to the latest version on GitHub.
4. **If User Replies `Yes` (`--upgrade_system`):** Run `sync_client_libs.py --upgrade_system` to install the latest version of `google-ads` from `pypi.org` into the site directory, install the latest version of the client library into the site directory, update `client_libs/google-ads-python` in the Assistant directory structure, update `api_version` in `config/assistant_config` (and `config/api_version.txt` if present) to the latest version, and print the results table to the screen.
5. **If User Replies `No` (`--check_only`):** Run `sync_client_libs.py --check_only` and present a comparison table showing the latest versions on GitHub versus what the user has installed on the system.

## Supported Ecosystems

- **Python (`google-ads-python`)**: Reads `pyproject.toml` / `ChangeLog`, updates `api_version` in `config/assistant_config` on sync, and checks/upgrades system site-packages parity.
- **PHP (`google-ads-php`)**: Reads `composer.json` metadata.
- **Ruby (`google-ads-ruby`)**: Reads `*.gemspec` / `version.rb`.
- **Java (`google-ads-java`)**: Reads `pom.xml`.
- **.NET (`google-ads-dotnet`)**: Reads `*.csproj`.
- **Git Repositories**: Supports `git fetch` and checkout of latest release tags with automatic fallback to GitHub archive tarball extraction.
