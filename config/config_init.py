"""Initializes config/google-ads.yaml from ~/google-ads.yaml and manages key-value pairs."""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional


def get_version(ext_version_script: Optional[str] = None) -> str:
    """Retrieves the assistant/extension version automatically.

    Discovers the version by:
    1. Executing get_extension_version.py if specified or found in candidate locations.
    2. Reading plugin.json or agent.json manifest files directly.
    3. Falling back to 'Unknown' if not found.

    Args:
        ext_version_script: Optional path to an extension version script.

    Returns:
        str: The detected version string or 'Unknown'.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. If an explicit script path is given or found, try executing it
    candidate_scripts = []
    if ext_version_script:
        candidate_scripts.append(ext_version_script)

    candidate_scripts.extend([
        os.path.join(
            this_dir,
            "../plugins/google-ads-api-developer-assistant/skills/ext-version/scripts/get_extension_version.py",
        ),
        os.path.join(
            this_dir,
            "../.gemini/skills/ext_version/scripts/get_extension_version.py",
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/skills/ext-version/scripts/get_extension_version.py"
        ),
    ])

    for script in candidate_scripts:
        script_path = os.path.normpath(script)
        if os.path.isfile(script_path):
            try:
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                ver = result.stdout.strip()
                if ver and ver not in ("Unknown", "Version not found"):
                    return ver
            except Exception:
                pass

    # 2. Check candidate plugin.json / agent.json files directly
    candidate_manifests = [
        os.path.join(
            this_dir,
            "../plugins/google-ads-api-developer-assistant/plugin.json",
        ),
        os.path.join(this_dir, "../plugin.json"),
        os.path.join(this_dir, "plugin.json"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.json"
        ),
    ]

    # Also search upwards for plugin.json or agent.json
    curr = this_dir
    while curr and curr != os.path.dirname(curr):
        for fname in ("plugin.json", "agent.json"):
            candidate_manifests.append(os.path.join(curr, fname))
        curr = os.path.dirname(curr)

    for manifest in candidate_manifests:
        manifest_path = os.path.normpath(manifest)
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    ver = data.get("version")
                    if ver:
                        return str(ver).strip()
            except Exception:
                continue

    return "Unknown"


def write_yaml_config(
    data: Optional[Dict[str, Any]] = None,
    target_path: Optional[str] = None,
    version: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> bool:
    """Writes a standard Google Ads YAML config.

    Duplicates the logic of write_yaml_config from custom_config.py:
    - Determines whether Service Account or OAuth credentials are used:
      - Service Account: writes 'json_key_file_path' and optional 'impersonated_email'.
      - OAuth: writes 'client_id', 'client_secret', and 'refresh_token'.
    - Writes 'developer_token' (default: 'INSERT_DEVELOPER_TOKEN_HERE').
    - Writes 'login_customer_id' if present in data.
    - Writes 'use_proto_plus: True'.
    - Writes 'ads_assistant: {version}'. If version is not provided, it is automatically
      determined by get_version().
    - Sets 0600 file permissions and updates GOOGLE_ADS_CONFIGURATION_FILE_PATH.

    Args:
        data: Dictionary of configuration keys and values.
        target_path: Target path for the google-ads.yaml file.
        version: Optional extension/assistant version string. If None, automatically determined.
        config_dir: Optional directory where google-ads.yaml will be created if target_path is not specified.

    Returns:
        bool: True if writing succeeded, False otherwise.
    """
    if data is None:
        data = {}

    if version is None:
        version = get_version()

    try:
        if not target_path:
            if not config_dir:
                this_dir = os.path.dirname(os.path.abspath(__file__))
                if os.path.basename(this_dir) == "config":
                    config_dir = this_dir
                else:
                    config_dir = os.path.join(this_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            target_path = os.path.join(config_dir, "google-ads.yaml")
        else:
            target_dir = os.path.dirname(os.path.abspath(target_path))
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

        service_account = "json_key_file_path" in data
        with open(target_path, "w", encoding="utf-8") as f:
            f.write("# Generated by Google Ads API Developer Assistant\n")
            f.write(
                "developer_token: "
                + str(data.get("developer_token", "INSERT_DEVELOPER_TOKEN_HERE"))
                + "\n"
            )

            if service_account:
                f.write(f"json_key_file_path: {data['json_key_file_path']}\n")
                if "impersonated_email" in data:
                    f.write(f"impersonated_email: {data['impersonated_email']}\n")
            else:
                f.write(
                    "client_id: "
                    + str(data.get("client_id", "INSERT_CLIENT_ID_HERE"))
                    + "\n"
                )
                f.write(
                    "client_secret: "
                    + str(data.get("client_secret", "INSERT_CLIENT_SECRET_HERE"))
                    + "\n"
                )
                f.write(
                    "refresh_token: "
                    + str(data.get("refresh_token", "INSERT_REFRESH_TOKEN_HERE"))
                    + "\n"
                )

            if "login_customer_id" in data:
                f.write(f"login_customer_id: {data['login_customer_id']}\n")
            f.write("use_proto_plus: True\n")
            if version:
                f.write(f"ads_assistant: {version}\n")

        # Enforce 0600 permissions where supported (POSIX)
        if os.path.isfile(target_path):
            try:
                os.chmod(target_path, 0o600)
            except OSError:
                pass

        # Set environment variable for the Google Ads Python client
        os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = target_path
        return True
    except Exception as e:
        print(f"Error writing YAML config: {e}", file=sys.stderr)
        return False


def parse_ruby_config(path: str) -> Dict[str, str]:
    """Parses a Ruby config file for Google Ads."""
    data: Dict[str, str] = {}
    patterns = {
        "developer_token": r"c\.developer_token\s*=\s*['\"](.*?)['\"]",
        "client_id": r"c\.client_id\s*=\s*['\"](.*?)['\"]",
        "client_secret": r"c\.client_secret\s*=\s*['\"](.*?)['\"]",
        "refresh_token": r"c\.refresh_token\s*=\s*['\"](.*?)['\"]",
        "login_customer_id": r"c\.login_customer_id\s*=\s*['\"](.*?)['\"]",
        "json_key_file_path": r"c\.json_key_file_path\s*=\s*['\"](.*?)['\"]",
        "impersonated_email": r"c\.impersonated_email\s*=\s*['\"](.*?)['\"]",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                if match:
                    data[key] = match.group(1)
    except Exception as e:
        print(f"Error parsing Ruby config: {e}", file=sys.stderr)
    return data


def parse_ini_config(path: str) -> Dict[str, str]:
    """Parses a PHP INI config file for Google Ads."""
    data: Dict[str, str] = {}
    patterns = {
        "developer_token": r"developerToken\s*=\s*(.*)$",
        "client_id": r"clientId\s*=\s*(.*)$",
        "client_secret": r"clientSecret\s*=\s*(.*)$",
        "refresh_token": r"refreshToken\s*=\s*(.*)$",
        "login_customer_id": r"loginCustomerId\s*=\s*(.*)$",
        "json_key_file_path": r"jsonKeyFilePath\s*=\s*(.*)$",
        "impersonated_email": r"impersonatedEmail\s*=\s*(.*)$",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                for key, pattern in patterns.items():
                    match = re.search(pattern, line)
                    if match:
                        data[key] = match.group(1).strip(" \"'\n")
    except Exception as e:
        print(f"Error parsing INI config: {e}", file=sys.stderr)
    return data


def parse_properties_config(path: str) -> Dict[str, str]:
    """Parses a Java properties config file for Google Ads."""
    data: Dict[str, str] = {}
    mapping = {
        "api.googleads.developerToken": "developer_token",
        "api.googleads.clientId": "client_id",
        "api.googleads.clientSecret": "client_secret",
        "api.googleads.refreshToken": "refresh_token",
        "api.googleads.loginCustomerId": "login_customer_id",
        "api.googleads.oAuth2SecretsJsonPath": "json_key_file_path",
        "api.googleads.oAuth2PrnEmail": "impersonated_email",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    if k in mapping:
                        data[mapping[k]] = v.strip()
    except Exception as e:
        print(f"Error parsing properties config: {e}", file=sys.stderr)
    return data


def copy_and_append_version(
    home_config: str,
    target_config: str,
    version: Optional[str] = None,
    lang: str = "YAML",
) -> bool:
    """Copies a configuration file and appends the extension version to it idiomatically."""
    if not os.path.exists(home_config):
        return False

    if version is None:
        version = get_version()

    try:
        target_dir = os.path.dirname(os.path.abspath(target_config))
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        shutil.copy2(home_config, target_config)
        with open(target_config, "r", encoding="utf-8") as f:
            content = f.read()

        if lang == "YAML":
            pattern = r"(?m)^\s*ads_assistant\s*:.*$"
            line = f"ads_assistant: {version}"
            if re.search(pattern, content):
                new_content = re.sub(pattern, line, content)
            else:
                separator = "" if content.endswith("\n") else "\n"
                new_content = f"{content}{separator}{line}\n"
        elif lang == "PHP":
            pattern = r'(?m)^\s*ads_assistant\s*=.*$'
            line = f'ads_assistant = "{version}"'
            if re.search(pattern, content):
                new_content = re.sub(pattern, line, content)
            else:
                separator = "" if content.endswith("\n") else "\n"
                new_content = f"{content}{separator}{line}\n"
        elif lang == "Ruby":
            pattern = r"(?m)^\s*ENV\['ADS_ASSISTANT'\]\s*=.*$"
            line = f"ENV['ADS_ASSISTANT'] = '{version}'"
            if re.search(pattern, content):
                new_content = re.sub(pattern, line, content)
            else:
                separator = "" if content.endswith("\n") else "\n"
                new_content = f"{content}{separator}{line}\n"
        elif lang == "Java":
            pattern = r"(?m)^\s*api\.googleads\.ads_assistant\s*=.*$"
            line = f"api.googleads.ads_assistant={version}"
            if re.search(pattern, content):
                new_content = re.sub(pattern, line, content)
            else:
                separator = "" if content.endswith("\n") else "\n"
                new_content = f"{content}{separator}{line}\n"
        else:
            separator = "" if content.endswith("\n") else "\n"
            new_content = f"{content}{separator}ads_assistant: {version}\n"

        with open(target_config, "w", encoding="utf-8") as f:
            f.write(new_content)

        if os.path.isfile(target_config):
            os.chmod(target_config, 0o600)

        return True
    except Exception as e:
        print(f"Error copying config {home_config}: {e}", file=sys.stderr)
        return False


def sync_and_set_config_kv(
    key: Optional[str] = None,
    value: Optional[Any] = None,
    source_yaml: str = "~/google-ads.yaml",
    config_dir: Optional[str] = None,
    version: Optional[str] = None,
) -> str:
    """Copies ~/google-ads.yaml to config/google-ads.yaml and ensures key: value is set.

    Preserves existing comments and YAML formatting. Appends the extension version
    using copy_and_append_version. Falls back to PHP, Ruby, or Java configuration
    files if source_yaml is not found.
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

    # 1. Read source YAML and construct own copy in config directory
    if os.path.isfile(src):
        copy_and_append_version(src, target_yaml, version=version, lang="YAML")
    elif not os.path.isfile(target_yaml):
        # Try fallbacks from the same directory as source_yaml
        home_dir = os.path.dirname(src)
        fallbacks = [
            ("PHP", "google_ads_php.ini", parse_ini_config),
            ("Ruby", "google_ads_config.rb", parse_ruby_config),
            ("Java", "ads.properties", parse_properties_config),
        ]
        found_fallback = False
        for lang_name, filename, parser in fallbacks:
            fallback_src = os.path.join(home_dir, filename)
            if os.path.isfile(fallback_src):
                fallback_target = os.path.join(config_dir, filename)
                copy_and_append_version(fallback_src, fallback_target, version=version, lang=lang_name)
                data = parser(fallback_src)
                if write_yaml_config(data, target_path=target_yaml, version=version):
                    found_fallback = True
                    break

        if not found_fallback:
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

    # 3. Enforce 0600 permissions where supported (POSIX)
    if os.path.isfile(target_yaml):
        try:
            os.chmod(target_yaml, 0o600)
        except OSError:
            pass

    # 4. Set environment variable for the Google Ads Python client
    os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = target_yaml

    return target_yaml


def get_config_file_path(config_dir: Optional[str] = None) -> str:
    """Returns the path to config/google-ads.yaml, ensuring it exists and is synced."""
    env_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    return sync_and_set_config_kv(config_dir=config_dir)

