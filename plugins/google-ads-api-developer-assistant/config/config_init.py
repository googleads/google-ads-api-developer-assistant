"""Initializes config/google-ads.yaml from ~/google-ads.yaml and manages key-value pairs."""

import os
import re
import shutil
from typing import Any, Optional


def sync_and_set_config_kv(
    key: Optional[str] = None,
    value: Optional[Any] = None,
    source_yaml: str = "~/google-ads.yaml",
    config_dir: Optional[str] = None,
) -> str:
    """Copies ~/google-ads.yaml to config/google-ads.yaml and ensures key: value is set.

    Preserves existing comments and YAML formatting.
    """
    if not config_dir:
        this_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(this_dir) == "config":
            config_dir = this_dir
        else:
            config_dir = os.path.join(this_dir, "config")

    os.makedirs(config_dir, exist_ok=True)
    target_yaml = os.path.join(config_dir, "google-ads.yaml")
    src = os.path.expanduser(source_yaml)

    # 1. Copy source if target does not exist or source is available
    if os.path.isfile(src):
        if not os.path.isfile(target_yaml):
            shutil.copy2(src, target_yaml)
    elif not os.path.isfile(target_yaml):
        raise FileNotFoundError(
            f"Source '{src}' not found and target '{target_yaml}' does not exist."
        )

    # 2. If a key is provided, update or append it
    if key is not None and value is not None:
        with open(target_yaml, "r", encoding="utf-8") as f:
            content = f.read()

        # Format value (quote strings if not already quoted, lowercase booleans)
        if isinstance(value, str):
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                formatted_val = value
            else:
                formatted_val = f'"{value}"'
        elif isinstance(value, bool):
            formatted_val = "true" if value else "false"
        else:
            formatted_val = str(value)

        new_entry = f"{key}: {formatted_val}"

        # Update existing key or append new key
        pattern = rf"(?m)^(\s*{re.escape(key)}\s*:).*$"
        if re.search(pattern, content):
            updated_content = re.sub(pattern, new_entry, content)
        else:
            # Append to the end with a clean newline
            separator = "" if content.endswith("\n") else "\n"
            updated_content = f"{content}{separator}{new_entry}\n"

        with open(target_yaml, "w", encoding="utf-8") as f:
            f.write(updated_content)

    # 3. Enforce 0600 permissions
    if os.path.isfile(target_yaml):
        os.chmod(target_yaml, 0o600)

    # 4. Set environment variable for the Google Ads Python client
    os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = target_yaml

    return target_yaml
