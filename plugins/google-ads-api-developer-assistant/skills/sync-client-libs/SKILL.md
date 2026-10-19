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

When the user enters their first prompt in the `agy` session, or when checking for client library updates, follow this exact 5-step workflow:
1. **Check Site-Directory Version Against PyPI:** Inspect the Python site-packages directory (`site.getsitepackages()` and `importlib.metadata.version("google-ads")`) to detect the installed runtime version of `google-ads`, and check the latest release on `pypi.org` (`https://pypi.org/pypi/google-ads/json`).
2. **Check Latest GitHub Version:** Fetch the latest release tag of the client library on GitHub (`googleads/google-ads-python/releases/latest`).
3. **Determine Active API Version:** Determine the Google Ads API version to use based on what is found in steps 1 and 2.
4. **Present Results in a Table:** Present a formatted comparison table of (1), (2), and (3) to the user.
5. **Prompt User When Any Version Outdated:** If any component is not the latest version, ask the user if they want to update them before proceeding:
   - **If User Replies `Yes` (`--upgrade_system`):** Run `sync_client_libs.py --upgrade_system` to install the latest version of `google-ads` from `pypi.org` into the site directory, install the latest version of the client library into the site directory, update `client_libs/google-ads-python` in the Assistant directory structure, update `api_version` in `config/assistant_config` (and `config/api_version.txt` if present) to the latest version, and print the results table to the screen.
   - **If User Replies `No` (`--check_only`):** Run `sync_client_libs.py --check_only` and continue with currently installed versions.

## Supported Ecosystems

- **Python (`google-ads-python`)**: Reads `pyproject.toml` / `ChangeLog`, updates `api_version` in `config/assistant_config` on sync, and checks/upgrades system site-packages parity.
- **PHP (`google-ads-php`)**: Reads `composer.json` metadata.
- **Ruby (`google-ads-ruby`)**: Reads `*.gemspec` / `version.rb`.
- **Java (`google-ads-java`)**: Reads `pom.xml`.
- **.NET (`google-ads-dotnet`)**: Reads `*.csproj`.
- **Git Repositories**: Supports `git fetch` and checkout of latest release tags with automatic fallback to GitHub archive tarball extraction.
