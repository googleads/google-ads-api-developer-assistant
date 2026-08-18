---
name: ext-version
description: Retrieves the current version of the Google Ads API Developer Assistant from plugin.json.
---

# Get Extension Version

Use this skill to retrieve the version of the Google Ads API Developer Assistant. This is useful when diagnosing issues, verifying the environment, or when the user explicitly asks for the version.

## Protocol

1. **Execution:** Run the version extraction script in python environment:

    ```bash
    python3 skills/ext-version/scripts/get_extension_version.py
    ```

2. **Output Handling:**
    * The script will print the version string (e.g., `4.0.0`) to `stdout`.
    * If `plugin.json` is missing or invalid, it will print an error to `stderr` and exit with code `1`.

## When to Use

* When the user asks "What version are you?" or "What is the assistant version?".
* Before generating diagnostic reports (to include the version in the report header as per rules).
* When troubleshooting environment-specific issues.
