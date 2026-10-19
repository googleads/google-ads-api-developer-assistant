"""Initializes config/google-ads.yaml from ~/google-ads.yaml and manages key-value pairs."""

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple


_CACHED_VERSION: Optional[str] = None


def get_version(ext_version_script: Optional[str] = None) -> str:
    """Retrieves the assistant/extension version automatically.

    Discovers the version by:
    1. Executing ext_version_script if explicitly specified.
    2. Reading plugin.json or agent.json manifest files directly (cached in-memory).
    3. Executing get_extension_version.py if found in candidate locations.
    4. Falling back to 'Unknown' if not found.

    Args:
        ext_version_script: Optional path to an extension version script.

    Returns:
        str: The detected version string or 'Unknown'.
    """
    global _CACHED_VERSION
    if ext_version_script is None and _CACHED_VERSION is not None:
        return _CACHED_VERSION

    this_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. If an explicit script path is given, execute it first
    if ext_version_script:
        script_path = os.path.normpath(ext_version_script)
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

    # 2. Check candidate plugin.json / agent.json files directly in-process (fast path)
    candidate_manifests = [
        os.path.join(this_dir, "../plugin.json"),
        os.path.join(this_dir, "plugin.json"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.json"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/plugin.json"
        ),
    ]

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
                        resolved = str(ver).strip()
                        if ext_version_script is None:
                            _CACHED_VERSION = resolved
                        return resolved
            except Exception:
                continue

    # 3. Fallback to candidate version scripts if manifest files were not found
    candidate_scripts = [
        os.path.join(
            this_dir,
            "../skills/ext-version/scripts/get_extension_version.py",
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/skills/ext-version/scripts/get_extension_version.py"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/skills/ext-version/scripts/get_extension_version.py"
        ),
    ]

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
                    if ext_version_script is None:
                        _CACHED_VERSION = ver
                    return ver
            except Exception:
                pass

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


def parse_dotnet_config(path: str) -> Dict[str, str]:
    """Parses a .NET config file (App.config XML or appsettings.json) for Google Ads."""
    data: Dict[str, str] = {}
    mapping = {
        "developertoken": "developer_token",
        "oauth2clientid": "client_id",
        "clientid": "client_id",
        "oauth2clientsecret": "client_secret",
        "clientsecret": "client_secret",
        "oauth2refreshtoken": "refresh_token",
        "refreshtoken": "refresh_token",
        "logincustomerid": "login_customer_id",
        "oauth2secretsjsonpath": "json_key_file_path",
        "jsonkeyfilepath": "json_key_file_path",
        "oauth2prnemail": "impersonated_email",
        "impersonatedemail": "impersonated_email",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        stripped = content.lstrip()
        # 1. Try JSON format (appsettings.json)
        if stripped.startswith("{"):
            try:
                parsed_json = json.loads(content)
                if isinstance(parsed_json, dict):
                    sections = [parsed_json]
                    for sec_key in ("GoogleAdsApi", "GoogleAds", "googleAdsApi"):
                        if isinstance(parsed_json.get(sec_key), dict):
                            sections.insert(0, parsed_json[sec_key])
                    for section in sections:
                        for k, v in section.items():
                            norm_k = str(k).strip().lower()
                            if norm_k in mapping and v is not None and not isinstance(v, (dict, list)):
                                data[mapping[norm_k]] = str(v).strip()
                    if data:
                        return data
            except Exception:
                pass

        # 2. Try XML format (App.config / Web.config <add key="..." value="..." />)
        add_tag_pattern = re.compile(
            r"<add\b[^>]*?\bkey\s*=\s*(['\"])(.*?)\1[^>]*?\bvalue\s*=\s*(['\"])(.*?)\3"
            r"|<add\b[^>]*?\bvalue\s*=\s*(['\"])(.*?)\5[^>]*?\bkey\s*=\s*(['\"])(.*?)\7",
            re.IGNORECASE | re.DOTALL,
        )
        for match in add_tag_pattern.finditer(content):
            if match.group(2) is not None:
                raw_k, raw_v = match.group(2), match.group(4)
            else:
                raw_k, raw_v = match.group(8), match.group(6)
            norm_k = raw_k.strip().lower()
            if norm_k in mapping:
                data[mapping[norm_k]] = raw_v.strip()

        # 3. Fallback to key: value / key = value lines if not XML/JSON
        if not data:
            for raw_line in content.splitlines():
                line = raw_line.split("#", 1)[0].strip()
                if not line:
                    continue
                kv_match = re.match(r"^([A-Za-z0-9_.]+)\s*[:=]\s*(.+)$", line)
                if kv_match:
                    norm_k = kv_match.group(1).strip().split(".")[-1].lower()
                    if norm_k in mapping:
                        data[mapping[norm_k]] = kv_match.group(2).strip(" \"'\n")
    except Exception as e:
        print(f"Error parsing .NET config: {e}", file=sys.stderr)
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
        elif lang in ("DotNet", ".NET"):
            stripped = content.lstrip()
            if stripped.startswith("{"):
                try:
                    parsed_json = json.loads(content)
                    if isinstance(parsed_json, dict):
                        if isinstance(parsed_json.get("GoogleAdsApi"), dict):
                            parsed_json["GoogleAdsApi"]["ads_assistant"] = version
                        else:
                            parsed_json["ads_assistant"] = version
                        new_content = json.dumps(parsed_json, indent=2) + "\n"
                    else:
                        new_content = content
                except Exception:
                    separator = "" if content.endswith("\n") else "\n"
                    new_content = f"{content}{separator}ads_assistant: {version}\n"
            elif "<" in content:
                xml_key_pattern = r'(<add\b[^>]*?\bkey\s*=\s*[\'"]ads_assistant[\'"][^>]*?\bvalue\s*=\s*[\'"])(.*?)([\'"])'
                if re.search(xml_key_pattern, content, flags=re.IGNORECASE):
                    new_content = re.sub(
                        xml_key_pattern,
                        rf"\g<1>{version}\g<3>",
                        content,
                        flags=re.IGNORECASE,
                    )
                else:
                    xml_entry = f'    <add key="ads_assistant" value="{version}"/>\n'
                    closing_tag_match = re.search(
                        r"(?i)(</(?:GoogleAdsApi|appSettings|configuration)>)",
                        content,
                    )
                    if closing_tag_match:
                        idx = closing_tag_match.start(1)
                        new_content = content[:idx] + xml_entry + content[idx:]
                    else:
                        separator = "" if content.endswith("\n") else "\n"
                        new_content = f"{content}{separator}{xml_entry}"
            else:
                separator = "" if content.endswith("\n") else "\n"
                new_content = f"{content}{separator}ads_assistant: {version}\n"
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
    using copy_and_append_version. Falls back to PHP, Ruby, Java, or .NET configuration
    files if source_yaml is not found.
    """
    if not config_dir:
        plugin_config_dir = os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
        )
        if os.path.isdir(plugin_config_dir) or os.path.isdir(os.path.dirname(plugin_config_dir)):
            config_dir = plugin_config_dir
        else:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            if os.path.basename(this_dir) == "config":
                config_dir = this_dir
            else:
                config_dir = os.path.join(this_dir, "config")

    os.makedirs(config_dir, exist_ok=True)
    target_yaml = os.path.join(config_dir, "google-ads.yaml")
    src = os.path.expanduser(source_yaml)

    # 1. Read source config and construct own copy in config directory
    if os.path.isfile(src):
        src_base = os.path.basename(src).lower()
        if src_base.endswith(".ini"):
            copy_and_append_version(
                src, os.path.join(config_dir, os.path.basename(src)), version=version, lang="PHP"
            )
            write_yaml_config(parse_ini_config(src), target_path=target_yaml, version=version)
        elif src_base.endswith(".rb"):
            copy_and_append_version(
                src, os.path.join(config_dir, os.path.basename(src)), version=version, lang="Ruby"
            )
            write_yaml_config(parse_ruby_config(src), target_path=target_yaml, version=version)
        elif src_base.endswith(".properties"):
            copy_and_append_version(
                src, os.path.join(config_dir, os.path.basename(src)), version=version, lang="Java"
            )
            write_yaml_config(parse_properties_config(src), target_path=target_yaml, version=version)
        elif src_base in ("app.config", "web.config", "appsettings.json") or src_base.endswith(
            (".config", ".xml", ".json")
        ):
            copy_and_append_version(
                src, os.path.join(config_dir, os.path.basename(src)), version=version, lang="DotNet"
            )
            write_yaml_config(parse_dotnet_config(src), target_path=target_yaml, version=version)
        else:
            copy_and_append_version(src, target_yaml, version=version, lang="YAML")
    elif not os.path.isfile(target_yaml):
        # Try fallbacks from the same directory as source_yaml
        home_dir = os.path.dirname(src)
        fallbacks = [
            ("PHP", "google_ads_php.ini", parse_ini_config),
            ("Ruby", "google_ads_config.rb", parse_ruby_config),
            ("Java", "ads.properties", parse_properties_config),
            ("DotNet", "App.config", parse_dotnet_config),
            ("DotNet", "appsettings.json", parse_dotnet_config),
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

    # 3b. Ensure config/assistant_config exists in TOML format (defaulting execute_mutates = false)
    target_assistant_cfg = os.path.join(config_dir, ASSISTANT_CONFIG_FILENAME)
    if key == "execute_mutates" and value is not None:
        parsed_bool = parse_execute_mutates_value(str(value))
        set_execute_mutates(bool(parsed_bool), config_dir=config_dir)
    elif key == "api_version":
        api_ver_val = str(value).strip() if value is not None else detect_latest_api_version()
        write_assistant_config({"api_version": api_ver_val}, config_dir=config_dir)
    elif key == "customer_id" and value is not None:
        write_assistant_config({"customer_id": str(value).strip()}, config_dir=config_dir)
    elif not os.path.isfile(target_assistant_cfg):
        seeded = False
        for candidate_cfg in get_assistant_config_paths():
            if (
                os.path.isfile(candidate_cfg)
                and os.path.abspath(candidate_cfg) != os.path.abspath(target_assistant_cfg)
            ):
                try:
                    shutil.copy2(candidate_cfg, target_assistant_cfg)
                    seeded = True
                    break
                except OSError:
                    continue
        if not seeded:
            write_assistant_config(
                {"api_version": detect_latest_api_version()},
                config_dir=config_dir,
            )

    # Automatically advance api_version in assistant_config when a newer API version is detected
    if key != "api_version":
        latest_ver = detect_latest_api_version()
        current_cfg = read_assistant_config(config_dir=config_dir)
        current_ver = str(current_cfg.get("api_version", "")).strip()
        if not current_ver or (
            re.match(r"^v\d+$", current_ver)
            and re.match(r"^v\d+$", latest_ver)
            and int(latest_ver[1:]) > int(current_ver[1:])
        ):
            write_assistant_config({"api_version": latest_ver}, config_dir=config_dir)

    # 4. Set environment variable for the Google Ads Python client
    os.environ["GOOGLE_ADS_CONFIGURATION_FILE_PATH"] = target_yaml

    # Mirror to local workspace config/google-ads.yaml if workspace config/ exists
    local_config_dir = os.path.abspath("config")
    if os.path.isdir(local_config_dir) and os.path.abspath(config_dir) != local_config_dir:
        try:
            local_target = os.path.join(local_config_dir, "google-ads.yaml")
            shutil.copy2(target_yaml, local_target)
            if sys.platform != "win32":
                try:
                    os.chmod(local_target, 0o600)
                except OSError:
                    pass
        except Exception:
            pass

    # Clean up any dummy google-ads.yaml in client_libs to avoid discovery ambiguity
    for root_dir in (
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs"),
        os.path.abspath("plugins/google-ads-api-developer-assistant/client_libs"),
        os.path.abspath("client_libs"),
    ):
        if os.path.isdir(root_dir):
            root_candidate = os.path.join(root_dir, "google-ads.yaml")
            if os.path.isfile(root_candidate):
                try:
                    os.remove(root_candidate)
                except OSError:
                    pass
            try:
                for entry in os.scandir(root_dir):
                    if entry.is_dir(follow_symlinks=False):
                        sub_candidate = os.path.join(entry.path, "google-ads.yaml")
                        if os.path.isfile(sub_candidate):
                            try:
                                os.remove(sub_candidate)
                            except OSError:
                                pass
            except OSError:
                pass

    return target_yaml


def get_config_file_path(config_dir: Optional[str] = None) -> str:
    """Returns the path to config/google-ads.yaml, ensuring it exists and is synced."""
    env_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    return sync_and_set_config_kv(config_dir=config_dir)


ASSISTANT_CONFIG_FILENAME = "assistant_config"
EXECUTE_MUTATES_FILENAME = ASSISTANT_CONFIG_FILENAME
DEFAULT_API_VERSION = "v25"
DEFAULT_CUSTOMER_ID = "12345678"
DEFAULT_EXECUTE_MUTATES = False


def _extract_version_dirs(base_dir: str) -> list[str]:
    """Returns sorted v<N> directory names inside base_dir."""
    if not base_dir or not os.path.isdir(base_dir):
        return []
    try:
        v_dirs = [
            d
            for d in os.listdir(base_dir)
            if os.path.isdir(os.path.join(base_dir, d)) and re.match(r"^v\d+$", d)
        ]
        v_dirs.sort(key=lambda x: int(x[1:]))
        return v_dirs
    except OSError:
        return []


def detect_latest_api_version() -> str:
    """Detects the latest Google Ads API version across local client_libs and installed google.ads.googleads."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_paths = [
        os.path.abspath("client_libs/google-ads-python/google/ads/googleads"),
        os.path.abspath(
            os.path.join(
                this_dir,
                "../client_libs/google-ads-python/google/ads/googleads",
            )
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python/google/ads/googleads"
        ),
    ]
    discovered_versions: list[str] = []
    for candidate in candidate_paths:
        v_dirs = _extract_version_dirs(candidate)
        if v_dirs:
            discovered_versions.append(v_dirs[-1])
            break

    try:
        import importlib

        gads_mod = importlib.import_module("google.ads.googleads")

        pkg_versions: list[str] = [
            attr for attr in dir(gads_mod) if re.match(r"^v\d+$", attr)
        ]
        pkg_paths: list[str] = []
        raw_path = getattr(gads_mod, "__path__", None)
        if raw_path:
            pkg_paths.extend(list(raw_path))
        pkg_file = getattr(gads_mod, "__file__", None)
        if pkg_file:
            pkg_paths.append(os.path.dirname(pkg_file))
        for pkg_dir in pkg_paths:
            pkg_versions.extend(_extract_version_dirs(pkg_dir))
        if pkg_versions:
            pkg_versions.sort(key=lambda x: int(x[1:]))
            discovered_versions.append(pkg_versions[-1])
    except Exception:
        pass

    if discovered_versions:
        discovered_versions.sort(key=lambda x: int(x[1:]))
        return discovered_versions[-1]

    return DEFAULT_API_VERSION


def _parse_semver_tuple(ver_str: Optional[str]) -> Tuple[int, ...]:
    """Parses a version string like '34.0.0' or 'v34.0.0' into an integer tuple."""
    if not ver_str:
        return (0,)
    clean = re.sub(r"^[^\d]*", "", str(ver_str).strip())
    parts: list[int] = []
    for token in re.split(r"[.\-_+]", clean):
        digits = re.findall(r"\d+", token)
        if digits:
            parts.append(int(digits[0]))
    return tuple(parts) if parts else (0,)


def _is_version_less_than(
    installed_ver: Optional[str], latest_ver: Optional[str]
) -> bool:
    """Returns True if installed_ver is missing or strictly older than latest_ver."""
    if not latest_ver:
        return False
    if not installed_ver:
        return True
    return _parse_semver_tuple(installed_ver) < _parse_semver_tuple(latest_ver)


def fetch_latest_github_python_version(
    ttl_seconds: int = 3600,
    force: bool = False,
) -> Optional[str]:
    """Fetches and caches the latest release version of googleads/google-ads-python on GitHub."""
    import tempfile
    import time
    import urllib.request

    cache_file = os.path.join(
        tempfile.gettempdir(), "gads_assistant_github_release.json"
    )
    now = time.time()
    if not force and os.path.isfile(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = float(cached.get("timestamp", 0.0))
            ver = str(cached.get("github_version") or "").strip().lstrip("v")
            if ver and (now - ts) < ttl_seconds:
                return ver
        except Exception:
            pass

    url = "https://api.github.com/repos/googleads/google-ads-python/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "google-ads-api-developer-assistant",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag_name = str(data.get("tag_name") or "").strip().lstrip("v")
        if tag_name:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": now, "github_version": tag_name}, f)
            except OSError:
                pass
            return tag_name
    except Exception:
        pass
    return None


def check_python_client_lib_parity(
    check_github: bool = False,
    force_github: bool = False,
) -> Dict[str, Any]:
    """Compares Python site-directory google-ads, local client_libs/google-ads-python, and GitHub latest version."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_libs = [
        os.path.abspath("client_libs/google-ads-python"),
        os.path.abspath(os.path.join(this_dir, "../client_libs/google-ads-python")),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
    ]

    local_version: Optional[str] = None
    local_path: Optional[str] = None
    for lib_dir in candidate_libs:
        pyproject = os.path.join(lib_dir, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                with open(pyproject, "r", encoding="utf-8") as f:
                    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', f.read())
                if m:
                    local_version = m.group(1).strip().lstrip("v")
                    local_path = lib_dir
                    break
            except OSError:
                continue

    site_directories: list[str] = []
    try:
        import site

        if hasattr(site, "getsitepackages"):
            site_directories.extend(site.getsitepackages())
        if hasattr(site, "getusersitepackages"):
            site_directories.append(site.getusersitepackages())
    except Exception:
        pass

    system_version: Optional[str] = None
    try:
        import importlib.metadata

        system_version = importlib.metadata.version("google-ads").strip().lstrip("v")
    except Exception:
        pass

    matches = bool(
        local_version and system_version and local_version == system_version
    )
    result: Dict[str, Any] = {
        "local_version": local_version,
        "local_path": local_path,
        "system_version": system_version,
        "site_directories": site_directories,
        "matches": matches,
    }
    if check_github:
        github_version = fetch_latest_github_python_version(force=force_github)
        site_lt_github = _is_version_less_than(system_version, github_version)
        local_lt_github = _is_version_less_than(local_version, github_version)
        result["github_version"] = github_version
        result["site_version_less_than_github"] = site_lt_github
        result["local_version_less_than_github"] = local_lt_github
        result["upgrade_prompt_required"] = bool(site_lt_github or local_lt_github)
    return result


def _find_sync_client_libs_script() -> Optional[str]:
    """Locates skills/sync-client-libs/scripts/sync_client_libs.py."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(this_dir, "../skills/sync-client-libs/scripts/sync_client_libs.py"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/sync_client_libs.py"
        ),
        os.path.abspath("skills/sync-client-libs/scripts/sync_client_libs.py"),
    ]
    for path in candidates:
        norm = os.path.normpath(path)
        if os.path.isfile(norm):
            return norm
    return None


def ensure_client_libs_synced(
    async_in_background: bool = True,
    force: bool = False,
    ttl_seconds: int = 3600,
    config_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Ensures client_libs and api_version are synchronized at session startup.

    Triggers sync_client_libs.py when:
    - force is True,
    - local client_libs/google-ads-python version does not match system google-ads version, or
    - the startup sync stamp in tempdir is missing or older than ttl_seconds.
    """
    import tempfile
    import time

    parity = check_python_client_lib_parity()
    script_path = _find_sync_client_libs_script()
    if not script_path:
        return {
            "triggered": False,
            "reason": "sync_client_libs.py not found",
            "parity": parity,
        }

    stamp_file = os.path.join(tempfile.gettempdir(), "gads_assistant_last_sync.json")
    now = time.time()
    stamp_expired = True
    if not force and os.path.isfile(stamp_file):
        try:
            with open(stamp_file, "r", encoding="utf-8") as f:
                stamp_data = json.load(f)
            last_ts = float(stamp_data.get("timestamp", 0.0))
            if (now - last_ts) < ttl_seconds:
                stamp_expired = False
        except Exception:
            stamp_expired = True

    mismatch = bool(
        parity.get("local_version")
        and parity.get("system_version")
        and not parity.get("matches")
    )
    if not force and not mismatch and not stamp_expired:
        return {
            "triggered": False,
            "reason": "up_to_date_within_ttl",
            "parity": parity,
        }

    try:
        with open(stamp_file, "w", encoding="utf-8") as f:
            json.dump({"timestamp": now, "mismatch": mismatch}, f)
    except OSError:
        pass

    cmd = [sys.executable, script_path, "--json"]
    if async_in_background:
        try:
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {
                "triggered": True,
                "mode": "background",
                "reason": "version_mismatch" if mismatch else "startup_ttl_sync",
                "parity": parity,
            }
        except Exception as exc:
            return {
                "triggered": False,
                "reason": f"background_spawn_error: {exc}",
                "parity": parity,
            }

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=120)
        latest_ver = sync_api_version(config_dir=config_dir)
        return {
            "triggered": True,
            "mode": "synchronous",
            "returncode": res.returncode,
            "api_version": latest_ver,
            "parity": check_python_client_lib_parity(),
        }
    except Exception as exc:
        return {
            "triggered": False,
            "reason": f"sync_run_error: {exc}",
            "parity": parity,
        }


def sync_api_version(config_dir: Optional[str] = None) -> str:
    """Detects the latest API version and updates api_version in config/assistant_config."""
    latest_v = detect_latest_api_version()
    write_assistant_config({"api_version": latest_v}, config_dir=config_dir)
    return latest_v


def parse_assistant_config(raw_text: str) -> Dict[str, Any]:
    """Parses a TOML-formatted assistant_config string into a dictionary."""
    data: Dict[str, Any] = {}
    if not raw_text or not raw_text.strip():
        return data

    # 1. Try standard library tomllib when available (Python 3.11+)
    try:
        import tomllib  # type: ignore

        parsed_toml = tomllib.loads(raw_text)
        if isinstance(parsed_toml, dict):
            data.update(parsed_toml)
    except Exception:
        pass

    # 2. Line-by-line fallback parser for loose key=value syntax
    if not data:
        for raw_line in raw_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("["):
                continue
            m = re.match(r"^([A-Za-z0-9_]+)\s*[=:]\s*(.+)$", line)
            if not m:
                continue
            k = m.group(1).strip()
            v_raw = m.group(2).strip()
            if (v_raw.startswith('"') and v_raw.endswith('"')) or (
                v_raw.startswith("'") and v_raw.endswith("'")
            ):
                data[k] = v_raw[1:-1]
            elif v_raw.lower() in ("true", "false"):
                data[k] = v_raw.lower() == "true"
            else:
                data[k] = v_raw

    # Normalize known keys
    if "api_version" in data and data["api_version"] is not None:
        ver_str = str(data["api_version"]).strip().strip("'\"")
        if ver_str and not ver_str.startswith("v") and ver_str.isdigit():
            ver_str = f"v{ver_str}"
        data["api_version"] = ver_str

    if "customer_id" in data and data["customer_id"] is not None:
        data["customer_id"] = str(data["customer_id"]).strip().strip("'\"")

    if "execute_mutates" in data and data["execute_mutates"] is not None:
        em_val = data["execute_mutates"]
        if isinstance(em_val, bool):
            data["execute_mutates"] = em_val
        else:
            em_str = str(em_val).strip().strip("'\"").lower()
            if em_str in ("true", "false"):
                data["execute_mutates"] = em_str == "true"
            else:
                del data["execute_mutates"]

    return data


def format_assistant_config(data: Dict[str, Any]) -> str:
    """Formats assistant configuration dictionary as a canonical TOML string."""
    api_ver = str(
        data.get("api_version") or detect_latest_api_version() or DEFAULT_API_VERSION
    ).strip().strip("'\"")
    if api_ver and not api_ver.startswith("v") and api_ver.isdigit():
        api_ver = f"v{api_ver}"
    cid = str(
        data.get("customer_id")
        if data.get("customer_id") is not None
        else DEFAULT_CUSTOMER_ID
    ).strip().strip("'\"")
    exec_mutates = bool(data.get("execute_mutates", DEFAULT_EXECUTE_MUTATES))
    exec_str = "true" if exec_mutates else "false"

    lines = [
        f'api_version = "{api_ver}"',
        f'customer_id = "{cid}"',
        f"execute_mutates = {exec_str}",
    ]
    for k, v in data.items():
        if k in ("api_version", "customer_id", "execute_mutates"):
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{v}"')
    return "\n".join(lines) + "\n"


def get_assistant_config_paths(config_dir: Optional[str] = None) -> list[str]:
    """Returns candidate paths for reading/writing config/assistant_config."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates: list[str] = []
    if config_dir:
        candidates.append(
            os.path.join(os.path.abspath(config_dir), ASSISTANT_CONFIG_FILENAME)
        )
    candidates.extend([
        os.path.abspath(os.path.join("config", ASSISTANT_CONFIG_FILENAME)),
        os.path.join(this_dir, ASSISTANT_CONFIG_FILENAME),
        os.path.expanduser(
            f"~/.gemini/config/plugins/google-ads-api-developer-assistant/config/{ASSISTANT_CONFIG_FILENAME}"
        ),
        os.path.expanduser(
            f"~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/{ASSISTANT_CONFIG_FILENAME}"
        ),
    ])
    deduped: list[str] = []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def read_assistant_config(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """Reads and parses the highest-precedence config/assistant_config file."""
    for candidate in get_assistant_config_paths(config_dir=config_dir):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    parsed = parse_assistant_config(f.read())
                if parsed:
                    return parsed
            except OSError:
                continue
    return {}


def _read_legacy_config_dir(d: str) -> Dict[str, str]:
    """Reads legacy v4.0.0 single-value config files (customer_id, customer_id.txt, api_version.txt)."""
    legacy: Dict[str, str] = {}
    for legacy_name in ("customer_id", "customer_id.txt"):
        legacy_file = os.path.join(d, legacy_name)
        if os.path.isfile(legacy_file):
            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    content = f.read().strip().strip("'\"")
                if content:
                    legacy["customer_id"] = content
                    break
            except OSError:
                pass

    legacy_ver_file = os.path.join(d, "api_version.txt")
    if os.path.isfile(legacy_ver_file):
        try:
            with open(legacy_ver_file, "r", encoding="utf-8") as f:
                ver_content = f.read().strip().strip("'\"")
            if ver_content:
                if not ver_content.startswith("v") and ver_content.isdigit():
                    ver_content = f"v{ver_content}"
                legacy["api_version"] = ver_content
        except OSError:
            pass
    return legacy


def write_assistant_config(
    updates: Optional[Dict[str, Any]] = None,
    config_dir: Optional[str] = None,
) -> str:
    """Updates keys in config/assistant_config (TOML), preserving existing settings."""
    if not config_dir:
        this_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(this_dir) == "config":
            config_dir = this_dir
        else:
            config_dir = os.path.join(this_dir, "config")

    os.makedirs(config_dir, exist_ok=True)
    target_path = os.path.join(config_dir, ASSISTANT_CONFIG_FILENAME)

    current_data: Dict[str, Any] = {}
    if os.path.isfile(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                current_data = parse_assistant_config(f.read())
        except OSError:
            current_data = {}
    else:
        for candidate in get_assistant_config_paths():
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        current_data = parse_assistant_config(f.read())
                    if current_data:
                        break
                except OSError:
                    continue

    # Migrate legacy v4.0.0 customer_id / api_version.txt if not yet customized
    legacy_dirs = [os.path.abspath(config_dir)] + [
        os.path.dirname(p) for p in get_assistant_config_paths(config_dir=config_dir)
    ]
    for ldir in legacy_dirs:
        legacy_vals = _read_legacy_config_dir(ldir)
        if (
            "customer_id" in legacy_vals
            and legacy_vals["customer_id"] != DEFAULT_CUSTOMER_ID
            and current_data.get("customer_id", DEFAULT_CUSTOMER_ID) == DEFAULT_CUSTOMER_ID
        ):
            current_data["customer_id"] = legacy_vals["customer_id"]
        if "api_version" in legacy_vals and not current_data.get("api_version"):
            current_data["api_version"] = legacy_vals["api_version"]

    if updates:
        current_data.update(updates)

    toml_content = format_assistant_config(current_data)
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(toml_content)

    if sys.platform != "win32" and os.path.isfile(target_path):
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass

    return target_path


def parse_execute_mutates_value(raw_text: str) -> Optional[bool]:
    """Parses 'execute_mutates = <true, false>' from TOML or key=value text and returns a boolean."""
    parsed_cfg = parse_assistant_config(raw_text)
    if "execute_mutates" in parsed_cfg and isinstance(parsed_cfg["execute_mutates"], bool):
        return parsed_cfg["execute_mutates"]

    for raw_line in raw_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(
            r"^execute_mutates\s*[=:]\s*['\"]?(true|false)['\"]?\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower() == "true"
        bare = line.strip("'\"").lower()
        if bare in ("true", "false"):
            return bare == "true"
    return None


def get_execute_mutates_paths(config_dir: Optional[str] = None) -> list[str]:
    """Returns candidate paths for reading/writing the execute_mutates setting in assistant_config."""
    return get_assistant_config_paths(config_dir=config_dir)


def is_execute_mutates_enabled(config_dir: Optional[str] = None) -> bool:
    """Returns whether the plugin is configured to support mutations (defaults to False)."""
    env_override = os.environ.get("GOOGLE_ADS_EXECUTE_MUTATES", "").strip()
    if env_override:
        parsed_env = parse_execute_mutates_value(env_override)
        if parsed_env is not None:
            return parsed_env
        return False

    for candidate in get_assistant_config_paths(config_dir=config_dir):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    parsed = parse_execute_mutates_value(f.read())
                if parsed is not None:
                    return parsed
                return False
            except OSError:
                continue

    return False


def set_execute_mutates(
    enabled: bool,
    config_dir: Optional[str] = None,
) -> str:
    """Updates 'execute_mutates = <true|false>' in config/assistant_config (TOML)."""
    return write_assistant_config(
        {"execute_mutates": bool(enabled)},
        config_dir=config_dir,
    )


def get_configured_customer_id(config_dir: Optional[str] = None) -> Optional[str]:
    """Reads customer_id from config/assistant_config (with fallback to legacy customer_id files)."""
    search_dirs: list[str] = []
    if config_dir:
        search_dirs.append(os.path.abspath(config_dir))
    search_dirs.extend([
        os.path.abspath("config"),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.abspath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "../plugins/google-ads-api-developer-assistant/config",
            )
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
        ),
    ])

    seen_dirs: list[str] = []
    for d in search_dirs:
        norm_d = os.path.normpath(d)
        if norm_d not in seen_dirs:
            seen_dirs.append(norm_d)

    fallback_default_cid: Optional[str] = None
    for d in seen_dirs:
        toml_cid = ""
        cfg_file = os.path.join(d, ASSISTANT_CONFIG_FILENAME)
        if os.path.isfile(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg = parse_assistant_config(f.read())
                toml_cid = str(cfg.get("customer_id", "")).strip()
            except OSError:
                pass

        if toml_cid and toml_cid != DEFAULT_CUSTOMER_ID:
            return toml_cid

        legacy_vals = _read_legacy_config_dir(d)
        legacy_cid = legacy_vals.get("customer_id", "")
        if legacy_cid and legacy_cid != DEFAULT_CUSTOMER_ID:
            return legacy_cid

        if toml_cid and fallback_default_cid is None:
            fallback_default_cid = toml_cid
        elif legacy_cid and fallback_default_cid is None:
            fallback_default_cid = legacy_cid

    return fallback_default_cid


def get_configured_api_version(config_dir: Optional[str] = None) -> Optional[str]:
    """Reads api_version from config/assistant_config (with fallback to legacy api_version.txt)."""
    for candidate in get_assistant_config_paths(config_dir=config_dir):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    cfg = parse_assistant_config(f.read())
                ver = str(cfg.get("api_version", "")).strip()
                if ver:
                    return ver
            except OSError:
                continue
        legacy_vals = _read_legacy_config_dir(os.path.dirname(candidate))
        if "api_version" in legacy_vals:
            return legacy_vals["api_version"]
    return None


READONLY_SKILL_SCRIPTS = (
    "validate_gaql.py",
    "inspect_object.py",
    "get_cids_under_mcc.py",
    "get_extension_version.py",
    "get_latest_api_version.py",
    "sync_client_libs.py",
    "build_version_delta.py",
    "scan_customer_codebase.py",
    "run_migration_verification.py",
    "troubleshoot_conversions.py",
    "get_recent_gclids.py",
    "validate_conversion_upload.py",
    "config_init.py",
    "benchmark_suite.py",
)

MUTATION_CALL_PATTERN = re.compile(
    r"\.\s*(?:mutate(?:_[a-z0-9_]+)?|apply_recommendation|upload_click_conversions|"
    r"upload_call_conversions|add_batch_job_operations|run_batch_job)\s*\("
)


def _normalize_request_for_hash(obj: Any) -> Any:
    """Normalizes a serialized RPC request payload by recursively stripping validate_only."""
    if isinstance(obj, dict):
        return {
            str(k): _normalize_request_for_hash(v)
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
            if str(k) != "validate_only"
        }
    if isinstance(obj, list):
        return [_normalize_request_for_hash(item) for item in obj]
    return obj


def _compute_canonical_request_sha256(
    service_name: str,
    method_name: str,
    req_payload: Any,
) -> str:
    """Computes a canonical SHA-256 hex digest of a serialized mutate request payload."""
    import hashlib

    normalized = _normalize_request_for_hash(req_payload)
    canonical_envelope = {
        "service": str(service_name).strip(),
        "method": str(method_name).strip(),
        "request": normalized,
    }
    canonical_json = json.dumps(
        canonical_envelope,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _verify_dry_run_receipt_for_hook(
    script_path: Optional[str] = None,
    max_age_seconds: int = 1800,
    hook_context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Checks saved/data/last_dry_run.json for a valid, recent dry-run receipt."""
    from datetime import datetime, timezone
    import hashlib
    import time

    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, ".."))
    candidate_receipts = [
        os.path.abspath(os.path.join("saved", "data", "last_dry_run.json")),
        os.path.join(plugin_root, "saved", "data", "last_dry_run.json"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/data/last_dry_run.json"
        ),
    ]

    receipt: Optional[Dict[str, Any]] = None
    for candidate in candidate_receipts:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    receipt = data
                    break
            except Exception:
                continue

    if not receipt:
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Live Google Ads API mutation attempted without a "
            "validate_only=True dry-run receipt in saved/data/last_dry_run.json. "
            "Run with --dry-run via skills/execute-mutation/scripts/run_mutation.py first, "
            "present the Consequence Summary to the user, and obtain confirmation.",
            {},
        )

    status = str(receipt.get("status", ""))
    if status != "DRY_RUN_PASSED":
        return (
            False,
            f"BLOCKED BY HITL MUTATION GUARD: Dry-run receipt status is '{status}' "
            "(expected 'DRY_RUN_PASSED'). Run a fresh validate_only=True dry-run and re-confirm with the user.",
            receipt,
        )

    ts = float(receipt.get("timestamp", 0.0))
    age = time.time() - ts
    if age > max_age_seconds:
        return (
            False,
            f"BLOCKED BY HITL MUTATION GUARD: Dry-run receipt expired ({int(age)}s old > {max_age_seconds}s limit). "
            "Re-run validate_only=True dry-run and re-verify consequences with the user.",
            receipt,
        )

    consequences = receipt.get("consequences", [])
    if not consequences or not any(str(c).strip() for c in consequences):
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt in saved/data/last_dry_run.json is missing "
            "mandatory consequence disclosures.",
            receipt,
        )

    if script_path:
        resolved_script = os.path.abspath(script_path)
        expected_hash = str(receipt.get("script_sha256", ""))
        if expected_hash and os.path.isfile(resolved_script):
            hasher = hashlib.sha256()
            with open(resolved_script, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            if hasher.hexdigest() != expected_hash:
                return (
                    False,
                    f"BLOCKED BY HITL MUTATION GUARD: Mutation script '{script_path}' was modified after "
                    "the validate_only=True dry-run (SHA-256 mismatch). Re-run --dry-run first.",
                    receipt,
                )

    # Verify canonical mutate request SHA-256 integrity on the receipt before allowing live execution
    recorded_req_sha = str(receipt.get("request_sha256", "")).strip()
    dry_run_calls = receipt.get("dry_run_rpc_calls")
    recorded_sha_list = receipt.get("request_sha256_list")
    if isinstance(dry_run_calls, list) and dry_run_calls:
        recomputed_list: list[str] = []
        for idx, call in enumerate(dry_run_calls):
            if not isinstance(call, dict):
                return (
                    False,
                    f"BLOCKED BY HITL MUTATION GUARD: Dry-run receipt RPC call #{idx + 1} is malformed. "
                    "Re-run --dry-run first.",
                    receipt,
                )
            recomputed_sha = _compute_canonical_request_sha256(
                str(call.get("service", "")),
                str(call.get("method", "")),
                call.get("request_payload"),
            )
            call_sha = str(call.get("request_sha256", "")).strip()
            if call_sha and call_sha != recomputed_sha:
                return (
                    False,
                    f"BLOCKED BY HITL MUTATION GUARD: Mutate request SHA-256 mismatch on dry-run RPC call #{idx + 1} "
                    "(SHA-256 mismatch). Re-run --dry-run first.",
                    receipt,
                )
            recomputed_list.append(recomputed_sha)

        if isinstance(recorded_sha_list, list) and recorded_sha_list != recomputed_list:
            return (
                False,
                "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt request_sha256_list mismatch "
                "(SHA-256 mismatch). Re-run --dry-run first.",
                receipt,
            )
        recomputed_agg = (
            recomputed_list[0]
            if len(recomputed_list) == 1
            else hashlib.sha256(
                json.dumps(recomputed_list, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )
        if recorded_req_sha and recorded_req_sha != recomputed_agg:
            return (
                False,
                "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt request_sha256 mismatch "
                "(SHA-256 mismatch). Re-run --dry-run first.",
                receipt,
            )
    elif recorded_req_sha:
        fallback_meta = {
            "customer_id": str(receipt.get("customer_id", "")).strip(),
            "operation_summary": str(receipt.get("operation_summary", "")).strip(),
            "before_state": str(receipt.get("before_state", "")).strip(),
            "after_state": str(receipt.get("after_state", "")).strip(),
            "script_path": str(receipt.get("script_path", "")),
            "script_sha256": str(receipt.get("script_sha256", "")),
        }
        recomputed_fallback_sha = _compute_canonical_request_sha256(
            "ScriptExecution", "mutate", fallback_meta
        )
        if recorded_req_sha != recomputed_fallback_sha:
            return (
                False,
                "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt request_sha256 mismatch "
                "(SHA-256 mismatch). Re-run --dry-run first.",
                receipt,
            )

    receipt["hook_prompted_at_iso"] = datetime.now(timezone.utc).isoformat()
    if isinstance(hook_context, dict):
        conv_id = hook_context.get("conversationId") or hook_context.get("session_id")
        transcript_path = (
            hook_context.get("transcriptPath") or hook_context.get("transcript_path")
        )
        model_name = hook_context.get("modelName") or hook_context.get("model")
        if conv_id:
            receipt["cli_conversation_id"] = str(conv_id)
        if transcript_path:
            receipt["cli_transcript_path"] = str(transcript_path)
        if model_name:
            receipt["model_name"] = str(model_name)

    for candidate in candidate_receipts:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "w", encoding="utf-8") as f:
                    json.dump(receipt, f, indent=2)
                if sys.platform != "win32":
                    try:
                        os.chmod(candidate, 0o600)
                    except OSError:
                        pass
            except OSError:
                continue

    consequences_formatted = "; ".join(str(c).strip() for c in consequences if str(c).strip())
    req_sha_display = str(receipt.get("request_sha256", "N/A"))
    prompt_reason = (
        f"⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION [Customer ID: {receipt.get('customer_id', 'Unknown')}]\n"
        f"• Operation: {receipt.get('operation_summary', 'Unknown')}\n"
        f"• Change: {receipt.get('before_state', 'N/A')} -> {receipt.get('after_state', 'N/A')}\n"
        f"• Request SHA256: {req_sha_display}\n"
        f"• Reversibility: {receipt.get('reversibility', 'UNKNOWN')}\n"
        f"• Consequences: {consequences_formatted}\n"
        f"Confirm execution of this live Google Ads API mutation?"
    )
    return True, prompt_reason, receipt


_TEST_OR_LINTER_CMD_RE = re.compile(
    r"(?:^|&&|\|\||;)\s*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*(?:[\w./-]+/)?(?:pytest|ruff|mypy|flake8)(?=\s|$)|"
    r"\bpython3?\s+-m\s+(?:pytest|ruff|mypy|flake8)(?=\s|$)"
)
_SCRIPT_ARG_RE = re.compile(
    r"--script(?:=|\s+)(?:'([^']+)'|\"([^\"]+)\"|([^\s'\"]+))"
)
_PY_FILE_ARG_RE = re.compile(
    r"(?:'([^']+\.py)'|\"([^\"]+\.py)\"|([^\s'\"]+\.py))"
)
_COMMENT_LINE_RE = re.compile(r"(?m)^\s*#.*$")
_VALIDATE_ONLY_TRUE_RE = re.compile(r"validate_only\s*=\s*True")
_VALIDATE_ONLY_FALSE_RE = re.compile(r"validate_only\s*=\s*False")
_LOAD_FROM_STORAGE_EMPTY_RE = re.compile(
    r"GoogleAdsClient\.load_from_storage\(\s*(?:None)?\s*\)"
)
_LOAD_FROM_STORAGE_VER_RE = re.compile(
    r"GoogleAdsClient\.load_from_storage\(\s*(?!path\s*=)(version\s*=[^)]+)\)"
)
_EXPANDUSER_YAML_RE = re.compile(
    r"os\.path\.expanduser\(\s*['\"][^'\"]*google-ads\.yaml['\"]\s*\)"
)
_QUOTED_HOME_YAML_RE = re.compile(
    r"(['\"])(?:~|/home/[^/'\"]+|client_libs/[^/'\"]+)/google-ads\.yaml\1"
)
_BARE_HOME_YAML_RE = re.compile(
    r"(?:~/google-ads\.yaml|/home/[^/\s'\"]+/google-ads\.yaml|client_libs/[^/\s'\"]+/google-ads\.yaml)"
)
_SKILL_REL_PATH_RE = re.compile(
    r"\bskills/[a-zA-Z0-9_\-]+/(?:scripts|references)/[a-zA-Z0-9_\-\.]+"
)


def evaluate_mutation_guard(
    cmd: str,
    hook_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Inspects a shell command for Google Ads API mutations and returns (decision, reason)."""
    if not cmd or not any(tok in cmd for tok in ("python", "python3", "run_mutation.py", ".py")):
        return "allow", None

    # Ignore test suites and linters when invoked as the runner command or module
    if _TEST_OR_LINTER_CMD_RE.search(cmd):
        return "allow", None

    # 1. Explicit invocation of skills/execute-mutation/scripts/run_mutation.py
    if "run_mutation.py" in cmd:
        if "--dry-run" in cmd and "--execute" not in cmd:
            return "allow", None
        if "--execute" in cmd:
            if not is_execute_mutates_enabled():
                return (
                    "deny",
                    "BLOCKED BY HITL MUTATION GUARD: Mutate support is disabled by configuration "
                    "(execute_mutates = false in config/assistant_config). Set 'execute_mutates = true' in "
                    "config/assistant_config to enable live Google Ads API mutations.",
                )
            script_match = _SCRIPT_ARG_RE.search(cmd)
            target_script = None
            if script_match:
                target_script = (
                    script_match.group(1)
                    or script_match.group(2)
                    or script_match.group(3)
                )
            ok, message, _ = _verify_dry_run_receipt_for_hook(
                script_path=target_script,
                hook_context=hook_context,
            )
            return ("force_ask", message) if ok else ("deny", message)

    # 2. Direct execution of a .py script or python -c snippet
    script_candidates = _PY_FILE_ARG_RE.findall(cmd)
    py_files: list[str] = []
    for grp in script_candidates:
        candidate = grp[0] or grp[1] or grp[2]
        if candidate and not any(ro in candidate for ro in READONLY_SKILL_SCRIPTS):
            py_files.append(candidate)

    code_blobs: list[str] = [cmd]
    resolved_target_script: Optional[str] = None
    for py_file in py_files:
        if os.path.isfile(py_file):
            resolved_target_script = py_file
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    code_blobs.append(f.read())
            except OSError:
                pass

    combined_code = "\n".join(code_blobs)
    uncommented_code = _COMMENT_LINE_RE.sub("", combined_code)

    if not MUTATION_CALL_PATTERN.search(uncommented_code):
        return "allow", None

    # A Google Ads mutation method is present in the executed code.
    # For direct script or inline execution (outside run_mutation.py), require an explicit
    # static validate_only=True and no validate_only=False or --execute flag; never trust
    # a bare --dry-run CLI flag alone if the script itself lacks validate_only=True.
    explicit_execute_flag = "--execute" in cmd

    has_validate_only_true = bool(_VALIDATE_ONLY_TRUE_RE.search(uncommented_code))
    has_validate_only_false = bool(_VALIDATE_ONLY_FALSE_RE.search(uncommented_code))

    if (
        has_validate_only_true
        and not has_validate_only_false
        and not explicit_execute_flag
    ):
        return "allow", None

    if not is_execute_mutates_enabled():
        return (
            "deny",
            "BLOCKED BY HITL MUTATION GUARD: Mutate support is disabled by configuration "
            "(execute_mutates = false in config/assistant_config). Set 'execute_mutates = true' in "
            "config/assistant_config to enable live Google Ads API mutations.",
        )

    # Live mutation detected -> require verified dry-run receipt & consequence disclosure
    ok, message, _ = _verify_dry_run_receipt_for_hook(
        script_path=resolved_target_script,
        hook_context=hook_context,
    )
    return ("force_ask", message) if ok else ("deny", message)


def handle_hook() -> None:
    """Handles Jetski and Claude Code CLI lifecycle hook execution (PreInvocation and PreToolUse)."""
    input_data: Dict[str, Any] = {}
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read()
            if raw.strip():
                input_data = json.loads(raw)
        except Exception:
            pass

    try:
        config_path = sync_and_set_config_kv()
    except Exception:
        config_path = os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        )

    # 1. PreToolUse hook (matcher: run_command, Bash, bash)
    if "toolCall" in input_data or "tool_input" in input_data:
        tool_call = input_data.get("toolCall", {})
        if isinstance(tool_call, dict) and "args" in tool_call:
            args = tool_call.get("args", {})
        else:
            args = input_data.get("tool_input", {})
        if not isinstance(args, dict):
            args = {}
        cmd = args.get("CommandLine") or args.get("command") or ""

        is_claude = "tool_input" in input_data or bool(os.environ.get("CLAUDE_CODE"))
        decision, reason = evaluate_mutation_guard(cmd, hook_context=input_data)
        if decision == "deny":
            deny_payload: Dict[str, Any] = {
                "decision": "deny",
                "reason": reason,
            }
            if is_claude:
                deny_payload["permissionDecision"] = "deny"
                deny_payload["permissionDecisionReason"] = reason
            print(json.dumps(deny_payload))
            return

        needs_interception = any(
            token in cmd
            for token in (
                "python",
                "pytest",
                "googleads",
                "GoogleAdsClient",
                "google-ads",
                "skills/",
                ".py",
            )
        )
        overwrite: Dict[str, Any] = {}
        if needs_interception:
            updated_cmd = cmd

            # Resolve assistant plugin root directory
            this_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.abspath(os.path.join(this_dir, ".."))
            global_plugin_dir = os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant"
            )
            if not os.path.isdir(os.path.join(plugin_root, "skills")) and os.path.isdir(global_plugin_dir):
                plugin_root = global_plugin_dir

            env_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_DIR")
            if env_dir and os.path.isdir(env_dir):
                plugin_root = os.path.abspath(env_dir)

            # Case A: load_from_storage() or load_from_storage(None)
            updated_cmd = _LOAD_FROM_STORAGE_EMPTY_RE.sub(
                'GoogleAdsClient.load_from_storage(path="config/google-ads.yaml")',
                updated_cmd,
            )
            # Case B: load_from_storage(version=...) where path is not provided
            updated_cmd = _LOAD_FROM_STORAGE_VER_RE.sub(
                r'GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", \1)',
                updated_cmd,
            )
            # Case C: os.path.expanduser('~/google-ads.yaml') or similar
            updated_cmd = _EXPANDUSER_YAML_RE.sub(
                r'"config/google-ads.yaml"',
                updated_cmd,
            )
            # Case D: Any string literal pointing to ~/google-ads.yaml, /home/.../google-ads.yaml, or client_libs/.../google-ads.yaml
            updated_cmd = _QUOTED_HOME_YAML_RE.sub(
                r'"config/google-ads.yaml"',
                updated_cmd,
            )
            # Case E: General fallback for any remaining ~/google-ads.yaml or /home/.../google-ads.yaml
            updated_cmd = _BARE_HOME_YAML_RE.sub(
                "config/google-ads.yaml",
                updated_cmd,
            )

            # Case F: skills/<skill_name>/(scripts|references)/<file> path resolution
            # When invoked in workspaces outside the repository, resolve relative skills/ paths to plugin_root
            def _resolve_skill_path(match: re.Match) -> str:
                rel_path = match.group(0)
                if os.path.exists(rel_path):
                    return rel_path
                target = os.path.join(plugin_root, rel_path)
                if os.path.exists(target):
                    return target
                alt_target = os.path.join(global_plugin_dir, rel_path)
                if os.path.exists(alt_target):
                    return alt_target
                return rel_path

            updated_cmd = _SKILL_REL_PATH_RE.sub(
                _resolve_skill_path,
                updated_cmd,
            )

            # Ensure GOOGLE_ADS_CONFIGURATION_FILE_PATH is exported in the subshell
            if "GOOGLE_ADS_CONFIGURATION_FILE_PATH" not in updated_cmd:
                updated_cmd = (
                    f'export GOOGLE_ADS_CONFIGURATION_FILE_PATH="{config_path}" && {updated_cmd}'
                )

            # Ensure GOOGLE_ADS_ASSISTANT_DIR is exported in the subshell
            if "GOOGLE_ADS_ASSISTANT_DIR" not in updated_cmd:
                updated_cmd = (
                    f'export GOOGLE_ADS_ASSISTANT_DIR="{plugin_root}" && {updated_cmd}'
                )

            # Ensure PYTHONPATH includes the plugin config directory so sitecustomize.py resolves config/ paths
            plugin_config_dir = os.path.join(plugin_root, "config")
            if "PYTHONPATH" not in updated_cmd and os.path.isdir(plugin_config_dir):
                updated_cmd = (
                    f'export PYTHONPATH="{plugin_config_dir}${{PYTHONPATH:+:$PYTHONPATH}}" && {updated_cmd}'
                )

            if "command" in args:
                overwrite["command"] = updated_cmd
            if "CommandLine" in args or not overwrite:
                overwrite["CommandLine"] = updated_cmd

        response_payload: Dict[str, Any] = {"decision": decision}
        if decision == "force_ask":
            if is_claude:
                response_payload["permissionDecision"] = "ask"
                if reason:
                    response_payload["permissionDecisionReason"] = reason
            if reason:
                response_payload["reason"] = reason
        if overwrite:
            response_payload["overwrite"] = overwrite

        print(json.dumps(response_payload))
        return

    # 2. PreInvocation hook (model prompt injection & 5-step startup client_libs version check)
    parity_info: Dict[str, Any] = check_python_client_lib_parity(
        check_github=not bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )

    active_api_version = get_configured_api_version() or detect_latest_api_version()
    mutates_enabled = is_execute_mutates_enabled()
    mutates_state_str = "execute_mutates = true" if mutates_enabled else "execute_mutates = false"
    msg = (
        f"CRITICAL GOOGLE ADS CONFIGURATION & HITL MUTATION NOTICE:\n"
        f"1. The active Google Ads API configuration file is at: {config_path} (or config/google-ads.yaml), with active api_version = \"{active_api_version}\".\n"
        f"   All Python client initializations MUST explicitly pass path='config/google-ads.yaml' to GoogleAdsClient.load_from_storage(path='config/google-ads.yaml').\n"
        f"2. HITL MUTATION VERIFICATION & AUDIT MANDATE ({mutates_state_str} in config/assistant_config): "
        f"Live mutations are currently {'ENABLED' if mutates_enabled else 'DISABLED (set execute_mutates = true in config/assistant_config to enable)'}. "
        f"Before executing ANY live Google Ads mutation, you MUST:\n"
        f"   (a) Ensure execute_mutates = true is configured in config/assistant_config,\n"
        f"   (b) Query current resource state via GAQL,\n"
        f"   (c) Execute a validate_only=True dry-run via skills/execute-mutation/scripts/run_mutation.py --dry-run to generate saved/data/last_dry_run.json,\n"
        f"   (d) Disclose the exact financial/serving/structural consequences to the user and wait for explicit confirmation before calling --execute (which appends to saved/logs/mutation_audit.jsonl).\n"
        f"3. RUNNABLE CODE STORAGE MANDATE: When asked to save code that can be run later, it MUST strictly be saved in the current working directory in a sub-directory called 'saved' (e.g., ./saved/ or ./saved/code/)."
    )
    if parity_info.get("upgrade_prompt_required"):
        sys_ver = parity_info.get("system_version") or "NOT INSTALLED"
        loc_ver = parity_info.get("local_version") or "NOT INSTALLED"
        gh_ver = parity_info.get("github_version") or "UNKNOWN"
        site_dirs = parity_info.get("site_directories") or []
        primary_site = site_dirs[0] if site_dirs else "system site-packages"
        msg += (
            f"\n4. CLIENT LIBRARY & SITE-DIRECTORY UPGRADE PROMPT REQUIRED:\n"
            f"   - Installed google-ads version in Python site directory ({primary_site}): {sys_ver}\n"
            f"   - Installed client_libs/google-ads-python version in Assistant directory: {loc_ver}\n"
            f"   - Latest release on GitHub (googleads/google-ads-python): {gh_ver}\n"
            f"   Because the installed version is older than the latest version on GitHub ({gh_ver}), you MUST prompt the user and ask if they want to upgrade to the latest version on GitHub ({gh_ver}):\n"
            f"   - If the user replies YES: run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system` to install the latest version of google-ads from pypi.org into the site directory, install the latest version of the client library into the site directory, update client_libs/google-ads-python in the Assistant directory structure, update api_version in config/assistant_config (and config/api_version.txt if present) to the latest version, and print the results to the screen.\n"
            f"   - If the user replies NO: run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only` and present a comparison table of the latest versions on GitHub versus what the user has installed on the system."
        )
    print(
        json.dumps(
            {
                "injectSteps": [
                    {
                        "ephemeralMessage": msg,
                    }
                ]
            }
        )
    )


def main() -> None:
    """Initializes config/google-ads.yaml from ~/google-ads.yaml at session start."""
    import argparse

    if "--hook" in sys.argv or (not sys.stdin.isatty() and len(sys.argv) == 1):
        handle_hook()
        return

    parser = argparse.ArgumentParser(
        description="Initialize config/google-ads.yaml from ~/google-ads.yaml and ensure required settings."
    )
    parser.add_argument("--key", default="login_customer_id", help="Config key to set or verify")
    parser.add_argument("--value", default=None, help="Config value to set")
    parser.add_argument(
        "--execute-mutates",
        default=None,
        choices=["true", "false"],
        help="Configure whether the plugin supports live mutations (execute_mutates = <true, false> in config/assistant_config)",
    )
    parser.add_argument("--config-dir", default=None, help="Target directory for config")
    parser.add_argument("--source-yaml", default="~/google-ads.yaml", help="Source configuration file")
    parser.add_argument("--hook", action="store_true", help="Run in Jetski lifecycle hook mode")
    parser.add_argument(
        "--sync-client-libs",
        action="store_true",
        help="Synchronize client_libs and api_version synchronously during initialization",
    )

    args = parser.parse_args()

    if args.execute_mutates is not None:
        set_execute_mutates(args.execute_mutates.lower() == "true", config_dir=args.config_dir)

    val = args.value
    if not val:
        val = os.environ.get("GOOGLE_ADS_CONFIG_VALUE")
    if not val:
        val = get_configured_customer_id(config_dir=args.config_dir)

    try:
        config_path = sync_and_set_config_kv(
            key=args.key,
            value=val,
            config_dir=args.config_dir,
            source_yaml=args.source_yaml,
        )
        if args.sync_client_libs:
            ensure_client_libs_synced(
                async_in_background=False,
                force=True,
                config_dir=args.config_dir,
            )
        print(f'export GOOGLE_ADS_CONFIGURATION_FILE_PATH="{config_path}"', file=sys.stdout)
        print(f"[config_init] Successfully initialized {config_path}", file=sys.stderr)
    except Exception as e:
        print(f"[config_init] Initialization error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
