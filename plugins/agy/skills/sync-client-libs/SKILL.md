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
python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only
```

### Automated Update
```bash
python3 skills/sync-client-libs/scripts/sync_client_libs.py
```

### Output Structured JSON
```bash
python3 skills/sync-client-libs/scripts/sync_client_libs.py --json
```

### Options Reference

| Flag | Short | Description |
| :--- | :--- | :--- |
| `--check_only` | `--dry_run` | Check versions and report status without modifying any files. |
| `--force` | | Force re-syncing/updating codebases even if versions match. |
| `--client_libs_dir` | `-d` | Explicit path to `client_libs` directory (auto-detected if omitted). |
| `--library` | `-l` | Filter to target a specific library (e.g. `google-ads-python`). |
| `--json` | | Output results in JSON format for automated ingestion. |

## Supported Ecosystems

- **Python (`google-ads-python`)**: Reads `pyproject.toml` / `ChangeLog`, updates `config/api_version.txt` on sync.
- **PHP (`google-ads-php`)**: Reads `composer.json` metadata.
- **Ruby (`google-ads-ruby`)**: Reads `*.gemspec` / `version.rb`.
- **Java (`google-ads-java`)**: Reads `pom.xml`.
- **.NET (`google-ads-dotnet`)**: Reads `*.csproj`.
- **Git Repositories**: Supports `git fetch` and checkout of latest release tags with automatic fallback to GitHub archive tarball extraction.
