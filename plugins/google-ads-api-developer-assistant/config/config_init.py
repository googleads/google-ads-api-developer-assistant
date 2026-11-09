"""Initializes config/google-ads.yaml from ~/google-ads.yaml and manages key-value pairs."""

import html
import json
import math
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
        os.path.join(this_dir, "../plugin.json.disabled"),
        os.path.join(this_dir, "plugin.json"),
        os.path.join(this_dir, "plugin.json.disabled"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.json"
        ),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/plugin.json.disabled"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/plugin.json"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/plugin.json.disabled"
        ),
    ]

    curr = this_dir
    while curr and curr != os.path.dirname(curr):
        for fname in ("plugin.json", "plugin.json.disabled", "agent.json"):
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


def _format_yaml_scalar(val: Any) -> str:
    """Safely formats a YAML string scalar, escaping backslashes/quotes and stripping newlines."""
    s = str(val).replace("\r", "").replace("\n", "")
    if (
        not s
        or s != s.strip()
        or s.lower() in ("true", "false", "null", "yes", "no", "on", "off", "~")
        or s[0]
        in (
            "-",
            "?",
            ":",
            ",",
            "[",
            "]",
            "{",
            "}",
            "#",
            "&",
            "*",
            "!",
            "|",
            ">",
            "'",
            '"',
            "%",
            "@",
            "`",
        )
        or any(ch in s for ch in ("\\", '"', "'", "#", "\t", "{", "}", "[", "]"))
        or ": " in s
        or s.endswith(":")
    ):
        escaped = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return s


def _strip_inline_comment(line: str, comment_chars: str = "#") -> str:
    """Strips inline comments outside single or double quotes."""
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and (in_single or in_double):
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch in comment_chars and not in_single and not in_double:
            return line[:idx]
    return line


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
        fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("# Generated by Google Ads API Developer Assistant\n")

            if service_account:
                f.write(
                    f"json_key_file_path: {_format_yaml_scalar(data['json_key_file_path'])}\n"
                )
                if "impersonated_email" in data:
                    f.write(
                        f"impersonated_email: {_format_yaml_scalar(data['impersonated_email'])}\n"
                    )
            else:
                f.write(
                    "client_id: "
                    + _format_yaml_scalar(
                        data.get("client_id", "INSERT_CLIENT_ID_HERE")
                    )
                    + "\n"
                )
                f.write(
                    "client_secret: "
                    + _format_yaml_scalar(
                        data.get("client_secret", "INSERT_CLIENT_SECRET_HERE")
                    )
                    + "\n"
                )
                f.write(
                    "refresh_token: "
                    + _format_yaml_scalar(
                        data.get("refresh_token", "INSERT_REFRESH_TOKEN_HERE")
                    )
                    + "\n"
                )

            if "login_customer_id" in data:
                f.write(
                    f"login_customer_id: {_format_yaml_scalar(data['login_customer_id'])}\n"
                )
            f.write("use_proto_plus: True\n")
            if version:
                f.write(f"ads_assistant: {_format_yaml_scalar(version)}\n")

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
        "client_id": r"c\.client_id\s*=\s*['\"](.*?)['\"]",
        "client_secret": r"c\.client_secret\s*=\s*['\"](.*?)['\"]",
        "refresh_token": r"c\.refresh_token\s*=\s*['\"](.*?)['\"]",
        "json_key_file_path": r"c\.json_key_file_path\s*=\s*['\"](.*?)['\"]",
        "impersonated_email": r"c\.impersonated_email\s*=\s*['\"](.*?)['\"]",
    }
    login_cid_re = re.compile(
        r"c\.login_customer_id\s*=\s*(?:['\"](.*?)['\"]|([0-9][0-9_]*))"
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            uncommented_lines = [
                _strip_inline_comment(raw_line, "#") for raw_line in f
            ]
        content = "\n".join(uncommented_lines)
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                data[key] = match.group(1)
        cid_match = login_cid_re.search(content)
        if cid_match:
            if cid_match.group(1) is not None:
                data["login_customer_id"] = cid_match.group(1)
            elif cid_match.group(2) is not None:
                data["login_customer_id"] = cid_match.group(2).replace("_", "")
    except Exception as e:
        print(f"Error parsing Ruby config: {e}", file=sys.stderr)
    return data


def parse_ini_config(path: str) -> Dict[str, str]:
    """Parses a PHP INI config file for Google Ads."""
    data: Dict[str, str] = {}
    patterns = {
        "client_id": r"^\s*clientId\s*=\s*(.*)$",
        "client_secret": r"^\s*clientSecret\s*=\s*(.*)$",
        "refresh_token": r"^\s*refreshToken\s*=\s*(.*)$",
        "login_customer_id": r"^\s*loginCustomerId\s*=\s*(.*)$",
        "json_key_file_path": r"^\s*jsonKeyFilePath\s*=\s*(.*)$",
        "impersonated_email": r"^\s*impersonatedEmail\s*=\s*(.*)$",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.lstrip()
                if not stripped or stripped.startswith((";", "#")):
                    continue
                line = _strip_inline_comment(raw_line, ";#").strip()
                if not line:
                    continue
                for key, pattern in patterns.items():
                    match = re.search(pattern, line)
                    if match:
                        val = match.group(1).strip()
                        if len(val) >= 2 and (
                            (val[0] == '"' and val[-1] == '"')
                            or (val[0] == "'" and val[-1] == "'")
                        ):
                            val = val[1:-1]
                        data[key] = val
    except Exception as e:
        print(f"Error parsing INI config: {e}", file=sys.stderr)
    return data


def parse_properties_config(path: str) -> Dict[str, str]:
    """Parses a Java properties config file for Google Ads."""
    data: Dict[str, str] = {}
    mapping = {
        "api.googleads.clientId": "client_id",
        "api.googleads.clientSecret": "client_secret",
        "api.googleads.refreshToken": "refresh_token",
        "api.googleads.loginCustomerId": "login_customer_id",
        "api.googleads.oAuth2SecretsJsonPath": "json_key_file_path",
        "api.googleads.oAuth2PrnEmail": "impersonated_email",
    }
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                stripped = raw_line.lstrip()
                if not stripped or stripped.startswith(("#", "!")):
                    continue
                m = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*[=:]\s*(.*?)\s*$", raw_line)
                if m:
                    k = m.group(1).strip()
                    if k in mapping:
                        val = m.group(2).strip()
                        if len(val) >= 2 and (
                            (val[0] == '"' and val[-1] == '"')
                            or (val[0] == "'" and val[-1] == "'")
                        ):
                            val = val[1:-1]
                        data[mapping[k]] = val
    except Exception as e:
        print(f"Error parsing properties config: {e}", file=sys.stderr)
    return data


def parse_dotnet_config(path: str) -> Dict[str, str]:
    """Parses a .NET config file (App.config XML or appsettings.json) for Google Ads."""
    data: Dict[str, str] = {}
    mapping = {
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
        with open(path, "r", encoding="utf-8-sig") as f:
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
        xml_uncommented = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        add_tag_pattern = re.compile(
            r"<add\b[^>]*?\bkey\s*=\s*(['\"])(.*?)\1[^>]*?\bvalue\s*=\s*(['\"])(.*?)\3"
            r"|<add\b[^>]*?\bvalue\s*=\s*(['\"])(.*?)\5[^>]*?\bkey\s*=\s*(['\"])(.*?)\7",
            re.IGNORECASE | re.DOTALL,
        )
        for match in add_tag_pattern.finditer(xml_uncommented):
            if match.group(2) is not None:
                raw_k, raw_v = match.group(2), match.group(4)
            else:
                raw_k, raw_v = match.group(8), match.group(6)
            norm_k = html.unescape(raw_k).strip().lower()
            if norm_k in mapping:
                data[mapping[norm_k]] = html.unescape(raw_v).strip()

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

        with open(home_config, "r", encoding="utf-8-sig") as f:
            content = f.read()

        if lang == "YAML":
            # Strip legacy sunset developer_token lines so sunset tokens are not propagated
            content = re.sub(r"(?m)^[ \t]*developer_token\s*:.*\r?\n?", "", content)
            pattern = r"(?m)^ads_assistant\s*:.*$"
            line = f"ads_assistant: {version}"
            if re.search(pattern, content):
                new_content = re.sub(pattern, line, content)
            else:
                separator = "" if (not content or content.endswith("\n")) else "\n"
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
            content = re.sub(r"(?m)^[ \t]*developer_token\s*:.*\r?\n?", "", content)
            separator = "" if (not content or content.endswith("\n")) else "\n"
            new_content = f"{content}{separator}ads_assistant: {version}\n"

        fd = os.open(target_config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)

        if os.path.isfile(target_config):
            try:
                os.chmod(target_config, 0o600)
            except OSError:
                pass

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
        env_cfg_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip()
        if env_cfg_dir:
            config_dir = os.path.abspath(env_cfg_dir)
        else:
            for cand_plugin_cfg in (
                os.path.expanduser(
                    "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
                ),
                os.path.expanduser(
                    "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
                ),
            ):
                if os.path.isdir(cand_plugin_cfg) or os.path.isdir(
                    os.path.dirname(cand_plugin_cfg)
                ):
                    config_dir = cand_plugin_cfg
                    break
            if not config_dir:
                this_dir = os.path.dirname(os.path.abspath(__file__))
                if os.path.basename(this_dir) == "config":
                    config_dir = this_dir
                else:
                    config_dir = os.path.join(this_dir, "config")

    os.makedirs(config_dir, exist_ok=True)
    target_yaml = os.path.join(config_dir, "google-ads.yaml")
    src = os.path.expanduser(source_yaml)

    preserved_login_cid_line: Optional[str] = None
    if os.path.isfile(target_yaml):
        try:
            with open(target_yaml, "r", encoding="utf-8") as f:
                prev_yaml_text = f.read()
            m_prev_lcid = re.search(r"(?m)^login_customer_id\s*:.*$", prev_yaml_text)
            if m_prev_lcid:
                preserved_login_cid_line = m_prev_lcid.group(0).strip()
        except OSError:
            preserved_login_cid_line = None

    if os.path.isfile(src):
        # 1. Read source config and construct own copy in config directory
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

        if preserved_login_cid_line and key != "login_customer_id" and os.path.isfile(target_yaml):
            try:
                with open(target_yaml, "r", encoding="utf-8") as f:
                    synced_text = f.read()
                if not re.search(r"(?m)^login_customer_id\s*:", synced_text):
                    sep = "" if (not synced_text or synced_text.endswith("\n")) else "\n"
                    fd = os.open(target_yaml, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as f_out:
                        f_out.write(f"{synced_text}{sep}{preserved_login_cid_line}\n")
            except OSError:
                pass
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

        # Format value (quote strings safely, lowercase booleans)
        if isinstance(value, str):
            clean_val = value.replace("\r", "").replace("\n", "")
            if len(clean_val) >= 2 and (
                (clean_val.startswith('"') and clean_val.endswith('"'))
                or (clean_val.startswith("'") and clean_val.endswith("'"))
            ):
                formatted_val = clean_val
            else:
                escaped_val = clean_val.replace("\\", "\\\\").replace('"', '\\"')
                formatted_val = f'"{escaped_val}"'
        elif isinstance(value, bool):
            formatted_val = "true" if value else "false"
        else:
            formatted_val = str(value)

        new_entry = f"{key}: {formatted_val}"

        # Anchor replacement at column 0 so indented nested keys (e.g. under logging:) are preserved
        pattern = rf"(?m)^{re.escape(key)}\s*:.*$"
        if re.search(pattern, content):
            updated_content = re.sub(pattern, lambda _m: new_entry, content)
        else:
            separator = "" if content.endswith("\n") else "\n"
            updated_content = f"{content}{separator}{new_entry}\n"

        fd = os.open(target_yaml, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
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
    elif key in ("enabled", "plugin_enabled") and value is not None:
        parsed_en = parse_plugin_enabled_value(str(value))
        set_plugin_enabled(
            bool(parsed_en) if parsed_en is not None else True,
            config_dir=config_dir,
        )
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

    # 3c. Ensure config/financial_limits exists in config_dir
    target_fin_limits = os.path.join(config_dir, "financial_limits")
    if not os.path.isfile(target_fin_limits):
        this_cfg_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_fin_files = [
            os.path.join(this_cfg_dir, "financial_limits"),
            os.path.abspath(os.path.join("config", "financial_limits")),
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/financial_limits"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/financial_limits"
            ),
        ]
        for cand_fin in candidate_fin_files:
            if (
                os.path.isfile(cand_fin)
                and os.path.abspath(cand_fin) != os.path.abspath(target_fin_limits)
            ):
                try:
                    shutil.copy2(cand_fin, target_fin_limits)
                    if sys.platform != "win32" and os.path.isfile(target_fin_limits):
                        try:
                            os.chmod(target_fin_limits, 0o600)
                        except OSError:
                            pass
                    break
                except OSError:
                    continue

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
        os.path.expanduser("~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs"),
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
DEFAULT_API_VERSION = "v26"
DEFAULT_CUSTOMER_ID = "12345678"
DEFAULT_EXECUTE_MUTATES = False
DEFAULT_PLUGIN_ENABLED = True


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
    """Parses a version string into a comparable integer tuple ranking pre-releases below stable releases."""
    if not ver_str:
        return (0,)
    clean = re.sub(r"^[^\d]*", "", str(ver_str).strip())
    if not clean:
        return (0,)
    # Strip build metadata (+...) per SemVer
    clean = clean.split("+", 1)[0]
    m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", clean)
    if not m:
        return (0,)

    core = [int(p) for p in m.group(1).split(".")]
    while len(core) < 3:
        core.append(0)

    suffix = m.group(2).strip().lower()
    if not suffix:
        # Stable release: rank 1 above pre-releases (0)
        return (*core, 1, 0)

    if "post" in suffix:
        post_nums = [int(d) for d in re.findall(r"\d+", suffix)] or [0]
        return (*core, 2, *post_nums)

    # Pre-release (dev < alpha/a < beta/b < rc/c/pre)
    pre_nums = [int(d) for d in re.findall(r"\d+", suffix)] or [0]
    if "dev" in suffix:
        stage = 1
    elif "alpha" in suffix or re.search(r"(?:^|[.\-_])a\d*", suffix):
        stage = 2
    elif "beta" in suffix or re.search(r"(?:^|[.\-_])b\d*", suffix):
        stage = 3
    elif "rc" in suffix or "pre" in suffix or re.search(r"(?:^|[.\-_])c\d*", suffix):
        stage = 4
    else:
        stage = 0
    return (*core, 0, stage, *pre_nums)


def _is_version_less_than(
    installed_ver: Optional[str], latest_ver: Optional[str]
) -> bool:
    """Returns True if installed_ver is missing or strictly older than latest_ver."""
    if not latest_ver:
        return False
    if not installed_ver:
        return True
    return _parse_semver_tuple(installed_ver) < _parse_semver_tuple(latest_ver)


_PYPI_CACHE_FILE: Optional[str] = None
_GITHUB_CACHE_FILE: Optional[str] = None
_SYNC_STAMP_FILE: Optional[str] = None


def _resolve_temp_cache_paths(
    stem: str, override_path: Optional[str] = None
) -> Tuple[str, list[str]]:
    """Returns (write_path, candidate_read_paths) using UID-scoped filenames on POSIX unless monkeypatched."""
    import tempfile

    if override_path:
        return override_path, [override_path]

    temp_dir = tempfile.gettempdir()
    legacy_path = os.path.join(temp_dir, f"{stem}.json")
    if hasattr(os, "getuid"):
        uid = os.getuid()
        uid_path = os.path.join(temp_dir, f"{stem}_{uid}.json")
        read_candidates = [uid_path]
        # Preserve test monkeypatches where tempfile.gettempdir() points to a private non-sticky tmp_path
        try:
            st_dir = os.stat(temp_dir)
            is_sticky = bool(st_dir.st_mode & 0o1000)
        except OSError:
            is_sticky = True
        if (
            not is_sticky
            and os.path.normpath(temp_dir) not in ("/tmp", "/var/tmp", "/usr/tmp")
            and os.path.isfile(legacy_path)
            and not os.path.islink(legacy_path)
        ):
            read_candidates.append(legacy_path)
        return uid_path, read_candidates
    return legacy_path, [legacy_path]


def _write_secure_temp_json(path: str, payload: Dict[str, Any]) -> None:
    """Safely writes a JSON cache file with mode 0o600, refusing symlinks where supported."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    if sys.platform != "win32" and os.path.isfile(path):
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


def fetch_latest_pypi_python_version(
    package_name: str = "google-ads",
    ttl_seconds: int = 3600,
    force: bool = False,
) -> Optional[str]:
    """Fetches and caches the latest release version of a package from pypi.org."""
    import time
    import urllib.request

    stem = f"gads_assistant_pypi_{package_name.replace('-', '_')}_release"
    cache_file, read_candidates = _resolve_temp_cache_paths(stem, _PYPI_CACHE_FILE)
    now = time.time()
    if not force:
        for cand in read_candidates:
            if os.path.isfile(cand) and not os.path.islink(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    ts = float(cached.get("timestamp", 0.0))
                    ver = str(cached.get("pypi_version") or "").strip().lstrip("v")
                    if ver and 0 <= (now - ts) < ttl_seconds:
                        return ver
                except Exception:
                    continue

    url = f"https://pypi.org/pypi/{package_name}/json"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "google-ads-api-developer-assistant",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ver = str(data.get("info", {}).get("version") or "").strip().lstrip("v")
        if ver:
            try:
                _write_secure_temp_json(
                    cache_file, {"timestamp": now, "pypi_version": ver}
                )
            except OSError:
                pass
            return ver
    except Exception:
        pass
    return None


def fetch_latest_github_python_version(
    ttl_seconds: int = 3600,
    force: bool = False,
) -> Optional[str]:
    """Fetches and caches the latest release version of googleads/google-ads-python on GitHub."""
    import time
    import urllib.request

    cache_file, read_candidates = _resolve_temp_cache_paths(
        "gads_assistant_github_release", _GITHUB_CACHE_FILE
    )
    now = time.time()
    if not force:
        for cand in read_candidates:
            if os.path.isfile(cand) and not os.path.islink(cand):
                try:
                    with open(cand, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                    ts = float(cached.get("timestamp", 0.0))
                    ver = str(cached.get("github_version") or "").strip().lstrip("v")
                    if ver and 0 <= (now - ts) < ttl_seconds:
                        return ver
                except Exception:
                    continue

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
                _write_secure_temp_json(
                    cache_file, {"timestamp": now, "github_version": tag_name}
                )
            except OSError:
                pass
            return tag_name
    except Exception:
        pass
    return None


def determine_api_version(
    system_version: Optional[str] = None,
    local_version: Optional[str] = None,
    config_dir: Optional[str] = None,
) -> str:
    """Determines the Google Ads API version to use based on site-directory (1) and client_libs (2)."""
    configured_ver = get_configured_api_version(config_dir=config_dir)
    if configured_ver:
        return configured_ver
    detected_ver = detect_latest_api_version()
    for candidate_ver in (local_version, system_version):
        if candidate_ver:
            m = re.match(r"^[vV](\d+)$", str(candidate_ver).strip())
            if m:
                return f"v{m.group(1)}"
    return detected_ver or DEFAULT_API_VERSION


def format_parity_table_markdown(
    parity_info: Dict[str, Any], api_version: str
) -> str:
    """Formats 3-component Google Ads version comparison table in GitHub Markdown."""
    sys_ver = parity_info.get("system_version") or "NOT INSTALLED"
    pypi_ver = (
        parity_info.get("pypi_version")
        or parity_info.get("github_version")
        or "UNKNOWN"
    )
    loc_ver = parity_info.get("local_version") or "NOT INSTALLED"
    gh_ver = parity_info.get("github_version") or "UNKNOWN"

    sys_status = (
        "UP_TO_DATE"
        if not parity_info.get("site_version_less_than_pypi")
        and sys_ver != "NOT INSTALLED"
        else ("OUTDATED" if sys_ver != "NOT INSTALLED" else "NOT INSTALLED")
    )
    loc_status = (
        "UP_TO_DATE"
        if not parity_info.get("local_version_less_than_github")
        and loc_ver != "NOT INSTALLED"
        else ("OUTDATED" if loc_ver != "NOT INSTALLED" else "NOT INSTALLED")
    )

    lines = [
        "| Component / Library | Installed / Local Version | Upstream Source | Upstream Release Version | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
        f"| `google-ads` (Python Site-Directory) | `{sys_ver}` | `pypi.org/project/google-ads` | `{pypi_ver}` | **{sys_status}** |",
        f"| `google-ads-python` (`client_libs/`) | `{loc_ver}` | `github.com/googleads/google-ads-python` | `{gh_ver}` | **{loc_status}** |",
        f"| Google Ads API Version (Selected) | `{api_version}` | Determined from (1) & (2) | `{api_version}` | **ACTIVE** |",
    ]
    return "\n".join(lines)


def format_parity_table_text(
    parity_info: Dict[str, Any], api_version: str
) -> str:
    """Formats 3-component Google Ads version comparison report for terminal display."""
    sys_ver = parity_info.get("system_version") or "NOT INSTALLED"
    pypi_ver = (
        parity_info.get("pypi_version")
        or parity_info.get("github_version")
        or "UNKNOWN"
    )
    loc_ver = parity_info.get("local_version") or "NOT INSTALLED"
    gh_ver = parity_info.get("github_version") or "UNKNOWN"

    sys_status = (
        "UP_TO_DATE"
        if not parity_info.get("site_version_less_than_pypi")
        and sys_ver != "NOT INSTALLED"
        else ("OUTDATED" if sys_ver != "NOT INSTALLED" else "NOT INSTALLED")
    )
    loc_status = (
        "UP_TO_DATE"
        if not parity_info.get("local_version_less_than_github")
        and loc_ver != "NOT INSTALLED"
        else ("OUTDATED" if loc_ver != "NOT INSTALLED" else "NOT INSTALLED")
    )

    fmt = "{:<36} {:<18} {:<38} {:<16} {:<12}"
    header = fmt.format(
        "Component / Library",
        "Installed / Local",
        "Upstream Source",
        "Latest Release",
        "Status",
    )
    div = "-" * len(header)
    eq_div = "=" * len(header)

    lines = [
        "",
        eq_div,
        "Google Ads API Version & Parity Verification Report",
        eq_div,
        header,
        div,
        fmt.format(
            "google-ads (site-packages)",
            sys_ver,
            "pypi.org/project/google-ads",
            pypi_ver,
            sys_status,
        ),
        fmt.format(
            "google-ads-python (client_libs)",
            loc_ver,
            "googleads/google-ads-python",
            gh_ver,
            loc_status,
        ),
        fmt.format(
            "Google Ads API Version",
            api_version,
            "Determined from (1) & (2)",
            api_version,
            "ACTIVE",
        ),
        eq_div,
    ]
    if parity_info.get("upgrade_prompt_required"):
        lines.extend([
            "",
            "ALERT: One or more Google Ads components are not the latest version!",
            "Would you like to update them?",
            "  - To update: run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system`",
            "  - To skip:   continue with currently installed versions.",
            "",
        ])
    return "\n".join(lines)


def check_python_client_lib_parity(
    check_github: bool = False,
    force_github: bool = False,
    check_pypi: Optional[bool] = None,
    force_pypi: bool = False,
    config_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Compares Python site-directory google-ads vs pypi.org, client_libs vs GitHub, and determines API version."""
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

    if check_pypi is None:
        check_pypi = check_github

    github_version: Optional[str] = None
    if check_github:
        github_version = fetch_latest_github_python_version(force=force_github)
        result["github_version"] = github_version

    pypi_version: Optional[str] = None
    if check_pypi:
        pypi_version = fetch_latest_pypi_python_version(force=force_pypi)
        if not pypi_version and github_version:
            pypi_version = github_version
        result["pypi_version"] = pypi_version

    site_lt_pypi = _is_version_less_than(system_version, pypi_version)
    site_lt_github = _is_version_less_than(system_version, github_version)
    local_lt_github = _is_version_less_than(local_version, github_version)

    result["site_version_less_than_pypi"] = site_lt_pypi
    result["site_version_less_than_github"] = site_lt_github
    result["local_version_less_than_github"] = local_lt_github

    api_version = determine_api_version(
        system_version=system_version,
        local_version=local_version,
        config_dir=config_dir,
    )
    result["api_version"] = api_version

    if check_github or check_pypi:
        result["upgrade_prompt_required"] = bool(
            site_lt_pypi or local_lt_github or site_lt_github
        )
    else:
        result["upgrade_prompt_required"] = False

    result["table_markdown"] = format_parity_table_markdown(result, api_version)
    result["table_text"] = format_parity_table_text(result, api_version)
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
    import time

    parity = check_python_client_lib_parity()
    script_path = _find_sync_client_libs_script()
    if not script_path:
        return {
            "triggered": False,
            "reason": "sync_client_libs.py not found",
            "parity": parity,
        }

    stamp_file, read_stamps = _resolve_temp_cache_paths(
        "gads_assistant_last_sync", _SYNC_STAMP_FILE
    )
    now = time.time()
    stamp_expired = True
    if not force:
        for cand_stamp in read_stamps:
            if os.path.isfile(cand_stamp) and not os.path.islink(cand_stamp):
                try:
                    with open(cand_stamp, "r", encoding="utf-8") as f:
                        stamp_data = json.load(f)
                    last_ts = float(stamp_data.get("timestamp", 0.0))
                    if 0 <= (now - last_ts) < ttl_seconds:
                        stamp_expired = False
                        break
                except Exception:
                    continue

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
        _write_secure_temp_json(
            stamp_file, {"timestamp": now, "mismatch": mismatch}
        )
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

    for enabled_key in ("enabled", "plugin_enabled"):
        if enabled_key in data and data[enabled_key] is not None:
            en_val = data[enabled_key]
            if isinstance(en_val, bool):
                data[enabled_key] = en_val
            else:
                en_str = str(en_val).strip().strip("'\"").lower()
                if en_str in ("true", "1", "yes", "on", "enabled"):
                    data[enabled_key] = True
                elif en_str in ("false", "0", "no", "off", "disabled"):
                    data[enabled_key] = False
                else:
                    del data[enabled_key]

    return data


def _escape_toml_basic_string(val: str) -> str:
    """Escapes backslashes, quotes, and control newlines for a TOML basic string."""
    return (
        val.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def format_assistant_config(data: Dict[str, Any]) -> str:
    """Formats assistant configuration dictionary as a canonical TOML string."""
    api_ver = str(
        data.get("api_version") or detect_latest_api_version() or DEFAULT_API_VERSION
    ).strip().strip("'\"")
    if api_ver and not api_ver.startswith("v") and ver_str_is_digit(api_ver):
        api_ver = f"v{api_ver}"
    cid = str(
        data.get("customer_id")
        if data.get("customer_id") is not None
        else DEFAULT_CUSTOMER_ID
    ).strip().strip("'\"")
    exec_mutates = bool(data.get("execute_mutates", DEFAULT_EXECUTE_MUTATES))
    exec_str = "true" if exec_mutates else "false"

    lines = [
        f'api_version = "{_escape_toml_basic_string(api_ver)}"',
        f'customer_id = "{_escape_toml_basic_string(cid)}"',
        f"execute_mutates = {exec_str}",
    ]
    for k, v in data.items():
        if k in ("api_version", "customer_id", "execute_mutates"):
            continue
        if v is None or isinstance(v, dict):
            continue
        if isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        elif isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                continue
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{_escape_toml_basic_string(str(v))}"')
    return "\n".join(lines) + "\n"


def ver_str_is_digit(s: str) -> bool:
    """Returns True if string s consists solely of digits."""
    return s.isdigit()


def get_assistant_config_paths(config_dir: Optional[str] = None) -> list[str]:
    """Returns candidate paths for reading/writing config/assistant_config."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates: list[str] = []
    if config_dir:
        candidates.append(
            os.path.join(os.path.abspath(config_dir), ASSISTANT_CONFIG_FILENAME)
        )
    else:
        env_cfg_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip()
        if env_cfg_dir:
            candidates.append(
                os.path.join(os.path.abspath(env_cfg_dir), ASSISTANT_CONFIG_FILENAME)
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


def _write_assistant_config_to_dir(
    target_cfg_dir: str,
    updates: Optional[Dict[str, Any]] = None,
) -> str:
    """Writes merged TOML configuration to a specific config directory with 0o600 permissions."""
    os.makedirs(target_cfg_dir, exist_ok=True)
    target_path = os.path.join(target_cfg_dir, ASSISTANT_CONFIG_FILENAME)

    current_data: Dict[str, Any] = {}
    if os.path.isfile(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                current_data = parse_assistant_config(f.read())
        except OSError:
            current_data = {}
    else:
        for candidate in get_assistant_config_paths(config_dir=target_cfg_dir):
            if os.path.isfile(candidate):
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        current_data = parse_assistant_config(f.read())
                    if current_data:
                        break
                except OSError:
                    continue

    # Migrate legacy v4.0.0 customer_id / api_version.txt if not yet customized
    legacy_dirs = [os.path.abspath(target_cfg_dir)] + [
        os.path.dirname(p) for p in get_assistant_config_paths(config_dir=target_cfg_dir)
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
    fd = os.open(target_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(toml_content)

    if sys.platform != "win32" and os.path.isfile(target_path):
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass

    return target_path


def write_assistant_config(
    updates: Optional[Dict[str, Any]] = None,
    config_dir: Optional[str] = None,
) -> str:
    """Updates keys in config/assistant_config (TOML), preserving existing settings."""
    if config_dir is not None:
        return _write_assistant_config_to_dir(config_dir, updates)

    env_cfg_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip()
    if env_cfg_dir:
        return _write_assistant_config_to_dir(os.path.abspath(env_cfg_dir), updates)

    this_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(this_dir) == "config":
        repo_cfg_dir = this_dir
        repo_plugin_dir = os.path.dirname(this_dir)
    else:
        repo_cfg_dir = os.path.join(this_dir, "config")
        repo_plugin_dir = this_dir

    if _is_repo_source_plugin_dir(repo_plugin_dir):
        global_cfg_candidates = [
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
            ),
        ]
        existing_global_dirs = [
            g
            for g in global_cfg_candidates
            if os.path.isdir(g) or os.path.isdir(os.path.dirname(g))
        ]
        if existing_global_dirs:
            primary_written: Optional[str] = None
            for g_cfg in existing_global_dirs:
                written = _write_assistant_config_to_dir(g_cfg, updates)
                if primary_written is None:
                    primary_written = written
            assert primary_written is not None
            return primary_written

    return _write_assistant_config_to_dir(repo_cfg_dir, updates)


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
                continue
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


def parse_plugin_enabled_value(raw_text: str) -> Optional[bool]:
    """Parses 'enabled = <true, false>' (or bare true/false/on/off/1/0) and returns a boolean."""
    parsed_cfg = parse_assistant_config(raw_text)
    for key in ("enabled", "plugin_enabled"):
        if key in parsed_cfg and isinstance(parsed_cfg[key], bool):
            return parsed_cfg[key]

    for raw_line in raw_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(
            r"^(?:enabled|plugin_enabled)\s*[=:]\s*['\"]?(true|false|1|0|yes|no|on|off|enabled|disabled)['\"]?\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower() in ("true", "1", "yes", "on", "enabled")
        bare = line.strip("'\"").lower()
        if bare in ("true", "1", "yes", "on", "enabled"):
            return True
        if bare in ("false", "0", "no", "off", "disabled"):
            return False
    return None


_HOOK_LIFECYCLE_EVENTS = ("PreToolUse", "PostToolUse", "PreInvocation", "SessionStart")


def _collect_hook_array_enabled_flags(container: Dict[str, Any]) -> list[bool]:
    """Collects explicit 'enabled' booleans from lifecycle hook arrays inside container."""
    flags: list[bool] = []
    for event_name, event_list in container.items():
        if event_name not in _HOOK_LIFECYCLE_EVENTS and not isinstance(event_list, list):
            continue
        if not isinstance(event_list, list):
            continue
        for entry in event_list:
            if not isinstance(entry, dict):
                continue
            if "enabled" in entry and (
                "config_init.py" in str(entry.get("command", ""))
                or isinstance(entry.get("hooks"), list)
            ):
                flags.append(bool(entry["enabled"]))
            if isinstance(entry.get("hooks"), list):
                for h in entry["hooks"]:
                    if (
                        isinstance(h, dict)
                        and "config_init.py" in str(h.get("command", ""))
                        and "enabled" in h
                    ):
                        flags.append(bool(h["enabled"]))
    return flags


def _is_hooks_json_disabled(hooks_path: str) -> Optional[bool]:
    """Returns True if hooks.json explicitly disables config-init hooks, False if enabled, None if unreadable."""
    if not os.path.isfile(hooks_path):
        return None
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    # 1. Top-level data["config-init"] schema (Jetski hooks.json)
    cfg_top = data.get("config-init")
    if isinstance(cfg_top, dict) and "enabled" in cfg_top:
        if not bool(cfg_top["enabled"]):
            return True

    # 2. Nested data["hooks"]["config-init"] schema (unit tests & dual-host wrappers)
    hooks_section = data.get("hooks")
    if isinstance(hooks_section, dict) and "config-init" in hooks_section:
        cfg_hook = hooks_section["config-init"]
        if isinstance(cfg_hook, dict) and "enabled" in cfg_hook:
            if not bool(cfg_hook["enabled"]):
                return True

    # 3. Check nested enabled booleans inside PreToolUse/PostToolUse/PreInvocation/SessionStart arrays
    nested_flags: list[bool] = []
    nested_flags.extend(_collect_hook_array_enabled_flags(data))
    if isinstance(cfg_top, dict):
        nested_flags.extend(_collect_hook_array_enabled_flags(cfg_top))
    if isinstance(hooks_section, dict):
        nested_flags.extend(_collect_hook_array_enabled_flags(hooks_section))
    if nested_flags and not any(nested_flags):
        return True

    return False


def _toggle_hook_event_arrays(
    container: Dict[str, Any],
    enabled: bool,
    force_command_flag: bool = False,
) -> bool:
    """Toggles nested 'enabled' booleans inside PreToolUse/PostToolUse/PreInvocation/SessionStart arrays."""
    changed = False
    for event_name, event_list in container.items():
        if event_name not in _HOOK_LIFECYCLE_EVENTS and not isinstance(event_list, list):
            continue
        if not isinstance(event_list, list):
            continue
        for entry in event_list:
            if not isinstance(entry, dict):
                continue
            if "enabled" in entry or (
                force_command_flag and "config_init.py" in str(entry.get("command", ""))
            ):
                if entry.get("enabled") != bool(enabled):
                    changed = True
                entry["enabled"] = bool(enabled)
                changed = True
            if isinstance(entry.get("hooks"), list):
                for h in entry["hooks"]:
                    if not isinstance(h, dict):
                        continue
                    is_cfg_cmd = "config_init.py" in str(h.get("command", ""))
                    if "enabled" in h or (force_command_flag and is_cfg_cmd):
                        h["enabled"] = bool(enabled)
                        changed = True
    return changed


def _set_hooks_json_enabled(hooks_path: str, enabled: bool) -> bool:
    """Updates 'enabled' flag on hooks in a hooks.json file (supporting both top-level and nested schemas)."""
    if not os.path.isfile(hooks_path):
        return False
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False

        changed = False
        has_config_init_block = False

        # 1. Top-level data["config-init"] schema
        cfg_top = data.get("config-init")
        if isinstance(cfg_top, dict):
            has_config_init_block = True
            cfg_top["enabled"] = bool(enabled)
            changed = True
            if _toggle_hook_event_arrays(cfg_top, enabled, force_command_flag=False):
                changed = True

        # 2. Nested data["hooks"] schema
        hooks_section = data.get("hooks")
        if isinstance(hooks_section, dict):
            if "config-init" in hooks_section and isinstance(hooks_section["config-init"], dict):
                has_config_init_block = True
                hooks_section["config-init"]["enabled"] = bool(enabled)
                changed = True
                if _toggle_hook_event_arrays(
                    hooks_section["config-init"], enabled, force_command_flag=False
                ):
                    changed = True
            if _toggle_hook_event_arrays(
                hooks_section,
                enabled,
                force_command_flag=not has_config_init_block,
            ):
                changed = True

        # 3. Direct top-level lifecycle event arrays (if any)
        if _toggle_hook_event_arrays(
            data,
            enabled,
            force_command_flag=not has_config_init_block,
        ):
            changed = True

        if changed:
            with open(hooks_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        return changed
    except Exception:
        return False


def _is_repo_source_plugin_dir(plugin_dir: str) -> bool:
    """Returns True if plugin_dir is inside a git repository working tree (source checkout)."""
    norm_dir = os.path.abspath(plugin_dir)
    parent = os.path.dirname(norm_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(parent) == "plugins" and (
        os.path.exists(os.path.join(grandparent, ".git"))
        or os.path.isfile(os.path.join(grandparent, "install.sh"))
    ):
        return True
    return False


def _toggle_installed_plugin_manifests(
    plugin_dir: str,
    enabled: bool,
    is_repo_source: Optional[bool] = None,
) -> Dict[str, Any]:
    """Toggles plugin manifests and hooks.json in an installed plugin directory."""
    result: Dict[str, Any] = {
        "plugin_dir": plugin_dir,
        "exists": os.path.isdir(plugin_dir),
        "updated_files": [],
    }
    if not os.path.isdir(plugin_dir):
        return result

    if is_repo_source is None:
        is_repo_source = _is_repo_source_plugin_dir(plugin_dir)

    for hooks_rel in ("hooks.json", os.path.join("hooks", "hooks.json")):
        hooks_path = os.path.join(plugin_dir, hooks_rel)
        if _set_hooks_json_enabled(hooks_path, enabled):
            result["updated_files"].append(hooks_path)

    # Only rename plugin.json / mcp_config.json / sidecar.json in installed plugin directories,
    # never in the git repository source tree.
    if not is_repo_source:
        manifest_rels = [
            "plugin.json",
            os.path.join(".claude-plugin", "plugin.json"),
            "mcp_config.json",
            os.path.join("sidecars", "google-ads-a2a-service", "sidecar.json"),
        ]
        for rel in manifest_rels:
            active_path = os.path.join(plugin_dir, rel)
            disabled_path = f"{active_path}.disabled"
            try:
                if enabled:
                    if os.path.isfile(disabled_path):
                        if not os.path.isfile(active_path):
                            os.replace(disabled_path, active_path)
                        else:
                            os.remove(disabled_path)
                        result["updated_files"].append(active_path)
                else:
                    if os.path.isfile(active_path):
                        os.replace(active_path, disabled_path)
                        result["updated_files"].append(disabled_path)
            except OSError:
                pass

    return result


def is_plugin_enabled(config_dir: Optional[str] = None) -> bool:
    """Returns whether the plugin is enabled (defaults to True).

    Checks in precedence order:
    1. GOOGLE_ADS_ASSISTANT_ENABLED environment variable override.
    2. Highest-precedence config/assistant_config (`enabled = true|false`).
    3. Installed plugin manifest state (`plugin.json.disabled` or `hooks.json` `enabled: false`).
    """
    env_override = os.environ.get("GOOGLE_ADS_ASSISTANT_ENABLED", "").strip()
    if env_override:
        parsed_env = parse_plugin_enabled_value(env_override)
        if parsed_env is not None:
            return parsed_env
        return DEFAULT_PLUGIN_ENABLED

    for candidate in get_assistant_config_paths(config_dir=config_dir):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    parsed = parse_plugin_enabled_value(f.read())
                if parsed is not None:
                    return parsed
            except OSError:
                continue

    # Check if the plugin directory associated with config_dir or installed plugin dirs has hooks/manifests disabled
    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_plugin_dirs: list[str] = []
    if config_dir:
        abs_cfg = os.path.abspath(config_dir)
        if os.path.basename(abs_cfg) == "config":
            candidate_plugin_dirs.append(os.path.dirname(abs_cfg))
        else:
            candidate_plugin_dirs.append(abs_cfg)
    if os.path.basename(this_dir) == "config":
        candidate_plugin_dirs.append(os.path.dirname(this_dir))
    candidate_plugin_dirs.append(
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant")
    )
    candidate_plugin_dirs.append(
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
        )
    )

    for pdir in candidate_plugin_dirs:
        if not os.path.isdir(pdir):
            continue
        if (
            os.path.isfile(os.path.join(pdir, "plugin.json.disabled"))
            and not os.path.isfile(os.path.join(pdir, "plugin.json"))
        ) or (
            os.path.isfile(os.path.join(pdir, ".claude-plugin", "plugin.json.disabled"))
            and not os.path.isfile(os.path.join(pdir, ".claude-plugin", "plugin.json"))
        ):
            return False
        hooks_disabled = _is_hooks_json_disabled(os.path.join(pdir, "hooks.json"))
        if hooks_disabled is None:
            hooks_disabled = _is_hooks_json_disabled(os.path.join(pdir, "hooks", "hooks.json"))
        if hooks_disabled is True:
            return False
        if config_dir is not None or not _is_repo_source_plugin_dir(pdir):
            break

    return DEFAULT_PLUGIN_ENABLED


def set_plugin_enabled(
    enabled: bool,
    config_dir: Optional[str] = None,
    sync_global: bool = True,
    target_type: str = "all",
) -> str:
    """Enables or disables the plugin in config/assistant_config and installed plugin directories."""
    enabled_bool = bool(enabled)

    # 1. Explicit config_dir passed (e.g. unit tests or --config-dir CLI)
    if config_dir is not None:
        target_path = _write_assistant_config_to_dir(
            config_dir,
            {"enabled": enabled_bool},
        )
        cfg_dir = os.path.dirname(os.path.abspath(target_path))
        local_plugin_dir = (
            os.path.dirname(cfg_dir) if os.path.basename(cfg_dir) == "config" else cfg_dir
        )
        _toggle_installed_plugin_manifests(local_plugin_dir, enabled_bool)
        return target_path

    agy_dir = os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant")
    claude_dir = os.path.expanduser(
        "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
    )
    claude_mkt = os.path.expanduser("~/.claude/plugins/google-ads-assistant-local")

    # 2. Platform-specific target ("agy" or "claude"): never fall back to mutating this_dir
    if target_type in ("agy", "claude"):
        selected_dir = agy_dir if target_type == "agy" else claude_dir
        if target_type == "claude" and os.path.isdir(claude_mkt):
            _toggle_installed_plugin_manifests(
                os.path.join(claude_mkt, ".claude-plugin"),
                enabled_bool,
                is_repo_source=False,
            )
        if os.path.isdir(selected_dir):
            g_cfg = os.path.join(selected_dir, "config")
            written = _write_assistant_config_to_dir(g_cfg, {"enabled": enabled_bool})
            _toggle_installed_plugin_manifests(selected_dir, enabled_bool, is_repo_source=False)
            return written
        return os.path.join(selected_dir, "config", ASSISTANT_CONFIG_FILENAME)

    # 3. target_type == "all" with config_dir is None
    target_path_all: Optional[str] = None
    env_cfg_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip()
    if env_cfg_dir:
        abs_env_cfg = os.path.abspath(env_cfg_dir)
        target_path_all = _write_assistant_config_to_dir(abs_env_cfg, {"enabled": enabled_bool})
        env_plugin_dir = (
            os.path.dirname(abs_env_cfg)
            if os.path.basename(abs_env_cfg) == "config"
            else abs_env_cfg
        )
        _toggle_installed_plugin_manifests(env_plugin_dir, enabled_bool)

    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_cfg_dir = this_dir if os.path.basename(this_dir) == "config" else os.path.join(this_dir, "config")
    repo_plugin_dir = os.path.dirname(repo_cfg_dir) if os.path.basename(repo_cfg_dir) == "config" else this_dir
    is_repo_src = _is_repo_source_plugin_dir(repo_plugin_dir)

    if not is_repo_src:
        try:
            written_local = _write_assistant_config_to_dir(repo_cfg_dir, {"enabled": enabled_bool})
            if target_path_all is None:
                target_path_all = written_local
        except OSError:
            pass
        _toggle_installed_plugin_manifests(repo_plugin_dir, enabled_bool, is_repo_source=False)

    if sync_global:
        if os.path.isdir(claude_mkt):
            _toggle_installed_plugin_manifests(
                os.path.join(claude_mkt, ".claude-plugin"),
                enabled_bool,
                is_repo_source=False,
            )
        for g_dir in (agy_dir, claude_dir):
            if os.path.isdir(g_dir):
                g_cfg = os.path.join(g_dir, "config")
                try:
                    written = _write_assistant_config_to_dir(g_cfg, {"enabled": enabled_bool})
                    if target_path_all is None:
                        target_path_all = written
                except OSError:
                    pass
                _toggle_installed_plugin_manifests(g_dir, enabled_bool, is_repo_source=False)

    if target_path_all is not None:
        return target_path_all

    return os.path.join(repo_cfg_dir, ASSISTANT_CONFIG_FILENAME)


def get_plugin_status(config_dir: Optional[str] = None) -> Dict[str, Any]:
    """Inspects and returns comprehensive plugin status and live hook behavior."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_plugin_dir = (
        os.path.dirname(this_dir) if os.path.basename(this_dir) == "config" else this_dir
    )
    agy_plugin_dir = os.path.expanduser(
        "~/.gemini/config/plugins/google-ads-api-developer-assistant"
    )
    claude_plugin_dir = os.path.expanduser(
        "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
    )

    enabled = is_plugin_enabled(config_dir=config_dir)
    env_override = os.environ.get("GOOGLE_ADS_ASSISTANT_ENABLED", "").strip() or None

    active_cfg_path: Optional[str] = None
    active_cfg_enabled: Optional[bool] = None
    for candidate in get_assistant_config_paths(config_dir=config_dir):
        if os.path.isfile(candidate):
            active_cfg_path = candidate
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    active_cfg_enabled = parse_plugin_enabled_value(f.read())
            except OSError:
                active_cfg_enabled = None
            break

    def _inspect_dir(pdir: str) -> Dict[str, Any]:
        exists = os.path.isdir(pdir)
        if not exists:
            return {"path": pdir, "installed": False}
        has_active_manifest = os.path.isfile(os.path.join(pdir, "plugin.json")) or os.path.isfile(
            os.path.join(pdir, ".claude-plugin", "plugin.json")
        )
        has_disabled_manifest = os.path.isfile(
            os.path.join(pdir, "plugin.json.disabled")
        ) or os.path.isfile(os.path.join(pdir, ".claude-plugin", "plugin.json.disabled"))
        hooks_path = os.path.join(pdir, "hooks.json")
        if not os.path.isfile(hooks_path):
            hooks_path = os.path.join(pdir, "hooks", "hooks.json")
        hooks_disabled = _is_hooks_json_disabled(hooks_path)
        cfg_file = os.path.join(pdir, "config", ASSISTANT_CONFIG_FILENAME)
        cfg_enabled = None
        if os.path.isfile(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_enabled = parse_plugin_enabled_value(f.read())
            except OSError:
                pass
        return {
            "path": pdir,
            "installed": True,
            "manifest_active": has_active_manifest,
            "manifest_disabled": has_disabled_manifest,
            "hooks_enabled": (not hooks_disabled) if hooks_disabled is not None else None,
            "config_enabled": cfg_enabled if cfg_enabled is not None else DEFAULT_PLUGIN_ENABLED,
        }

    return {
        "enabled": enabled,
        "status": "enabled" if enabled else "disabled",
        "env_override": env_override,
        "active_config_path": active_cfg_path,
        "config_enabled": active_cfg_enabled if active_cfg_enabled is not None else DEFAULT_PLUGIN_ENABLED,
        "api_version": get_configured_api_version(config_dir=config_dir) or DEFAULT_API_VERSION,
        "execute_mutates": is_execute_mutates_enabled(config_dir=config_dir),
        "installations": {
            "agy": _inspect_dir(agy_plugin_dir),
            "claude": _inspect_dir(claude_plugin_dir),
            "local": _inspect_dir(repo_plugin_dir),
        },
    }


def format_plugin_status_text(status_info: Dict[str, Any]) -> str:
    """Formats the plugin status dictionary as human-readable text."""
    state_label = "ENABLED" if status_info.get("enabled") else "DISABLED"
    lines = [
        f"Google Ads API Developer Assistant Status: {state_label}",
        f"  Effective State   : {status_info.get('status')}",
        f"  Active Config     : {status_info.get('active_config_path') or 'default'}",
        f"  Config 'enabled'  : {'true' if status_info.get('config_enabled') else 'false'}",
    ]
    if status_info.get("env_override") is not None:
        lines.append(f"  Env Override      : GOOGLE_ADS_ASSISTANT_ENABLED={status_info['env_override']}")
    lines.append(f"  API Version       : {status_info.get('api_version')}")
    lines.append(
        f"  Execute Mutates   : {'true' if status_info.get('execute_mutates') else 'false'}"
    )

    installations = status_info.get("installations", {})
    for label, key in (
        ("Jetski / Antigravity (~/.gemini)", "agy"),
        ("Claude Code (~/.claude)", "claude"),
        ("Local Workspace", "local"),
    ):
        info = installations.get(key, {})
        if not info.get("installed"):
            lines.append(f"  {label}: not installed ({info.get('path')})")
        else:
            manifest_state = (
                "active (plugin.json)"
                if info.get("manifest_active")
                else (
                    "disabled (plugin.json.disabled)"
                    if info.get("manifest_disabled")
                    else "not found"
                )
            )
            hooks_state = (
                "enabled"
                if info.get("hooks_enabled") is True
                else ("disabled" if info.get("hooks_enabled") is False else "n/a")
            )
            cfg_state = "true" if info.get("config_enabled") else "false"
            lines.append(
                f"  {label}: manifest={manifest_state}, hooks={hooks_state}, config.enabled={cfg_state}"
            )
    return "\n".join(lines)


def get_configured_customer_id(config_dir: Optional[str] = None) -> Optional[str]:
    """Reads customer_id from config/assistant_config (with fallback to legacy customer_id files)."""
    search_dirs: list[str] = []
    if config_dir:
        search_dirs.append(os.path.abspath(config_dir))
    else:
        env_cfg_dir = os.environ.get("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "").strip()
        if env_cfg_dir:
            search_dirs.append(os.path.abspath(env_cfg_dir))
    search_dirs.extend([
        os.path.abspath("config"),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
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
    "set_financial_limits.py",
)

_READONLY_SKILL_SCRIPTS_SET = frozenset(READONLY_SKILL_SCRIPTS)

MUTATION_CALL_PATTERN = re.compile(
    r"(?:\.\s*(?:mutate(?:_[a-z0-9_]+)?|(?:remove|delete)_[a-z0-9_]+|"
    r"apply_recommendation|dismiss_recommendation|"
    r"upload_click_conversions|upload_call_conversions|upload_conversion_adjustments|"
    r"upload_user_data|create_offline_user_data_job|add_offline_user_data_job_operations|"
    r"run_offline_user_data_job|add_batch_job_operations|run_batch_job|book_campaigns|"
    r"apply_incentive|provide_lead_feedback|create_customer_client|"
    r"create_data_link|update_data_link|create_product_link|"
    r"create_product_link_invitation|update_product_link_invitation|"
    r"create_you_tube_video_upload|update_you_tube_video_upload|"
    r"move_manager_link|append_lead_conversation|generate_p_max_draft_campaign|"
    r"promote_campaign_draft|graduate_experiment|promote_experiment|"
    r"schedule_experiment|end_experiment)\s*\("
    r"|\b(?:op|operation|[a-zA-Z0-9_]*_op|[a-zA-Z0-9_]*_operation)\s*\.\s*remove(?:_all)?\s*=(?!=)"
    r"|\b[A-Za-z0-9_]*Operation\s*\([^)]*\bremove(?:_all)?\s*=)"
)

_NON_VALIDATE_ONLY_CALL_RE = re.compile(
    r"\.\s*(?:mutate_billing_setup|book_campaigns|apply_incentive|"
    r"provide_lead_feedback|apply_recommendation|dismiss_recommendation|"
    r"mutate_batch_job|add_batch_job_operations|run_batch_job|"
    r"create_offline_user_data_job|add_offline_user_data_job_operations|run_offline_user_data_job|"
    r"mutate_customer_user_access|mutate_customer_user_access_invitation|"
    r"upload_user_data)\s*\("
)

_HOOK_FINANCIAL_SERVICES = frozenset({
    "billingsetupservice",
    "accountbudgetproposalservice",
    "campaignbudgetservice",
    "biddingstrategyservice",
    "biddingseasonalityadjustmentservice",
    "biddingdataexclusionservice",
    "campaignbidmodifierservice",
    "adgroupbidmodifierservice",
    "conversionvalueruleservice",
    "conversionvaluerulesetservice",
    "conversionadjustmentuploadservice",
    "conversionuploadservice",
    "goalservice",
    "campaigngoalconfigservice",
    "customerlifecyclegoalservice",
    "campaignlifecyclegoalservice",
    "offlineuserdatajobservice",
    "userdataservice",
    "assetservice",
    "recommendationservice",
    "reservationservice",
    "incentiveservice",
    "localservicesleadservice",
})

_HOOK_FINANCIAL_METHODS = frozenset({
    "mutate_billing_setup",
    "mutate_account_budget_proposal",
    "mutate_campaign_budgets",
    "mutate_bidding_strategies",
    "mutate_bidding_seasonality_adjustments",
    "mutate_bidding_data_exclusions",
    "mutate_campaign_bid_modifiers",
    "mutate_ad_group_bid_modifiers",
    "mutate_conversion_value_rules",
    "mutate_conversion_value_rule_sets",
    "mutate_goals",
    "mutate_campaign_goal_configs",
    "configure_customer_lifecycle_goals",
    "configure_campaign_lifecycle_goals",
    "upload_conversion_adjustments",
    "book_campaigns",
    "apply_incentive",
    "provide_lead_feedback",
    "create_customer_client",
    "graduate_experiment",
    "promote_experiment",
    "schedule_experiment",
    "promote_campaign_draft",
})

_HOOK_FINANCIAL_PAYLOAD_KEYS = frozenset({
    "amount_micros",
    "total_amount_micros",
    "recommended_budget_amount_micros",
    "new_budget_amount_micros",
    "recommended_cpa_opt_in_micros",
    "spending_limit_micros",
    "proposed_spending_limit_micros",
    "approved_spending_limit_micros",
    "campaign_budget",
    "campaign_budget_operation",
    "account_budget_proposal",
    "billing_setup",
    "payments_account",
    "payments_account_info",
    "purchase_order_number",
    "cpc_bid_micros",
    "cpm_bid_micros",
    "cpv_bid_micros",
    "target_cpa_micros",
    "target_cpm_micros",
    "target_roas",
    "cpc_bid_ceiling_micros",
    "cpc_bid_floor_micros",
    "percent_cpc_bid_micros",
    "fixed_cpm_micros",
    "target_spend_micros",
    "commission_rate_micros",
    "bid_modifier",
    "target_cpa_multiplier",
    "target_roas_multiplier",
    "high_lifetime_value_multiplier",
    "bidding_strategy",
    "bidding_strategy_operation",
    "campaign_bid_modifier_operation",
    "ad_group_bid_modifier_operation",
    "bidding_seasonality_adjustment_operation",
    "bidding_data_exclusion_operation",
    "seasonality_modifier",
    "manual_cpc",
    "manual_cpm",
    "manual_cpv",
    "maximize_conversions",
    "maximize_conversion_value",
    "target_cpa",
    "target_impression_share",
    "target_spend",
    "conversion_value",
    "adjusted_value",
    "restatement_value",
    "default_value",
    "additional_value",
    "additional_high_lifetime_value",
    "lifetime_value_micros",
    "high_lifetime_value_micros",
    "transaction_amount_micros",
    "unit_price",
    "local_transaction_cost",
    "money_amount_off",
    "orders_over_amount",
    "up_to_amount",
    "conversion_value_rule_operation",
    "conversion_value_rule_set_operation",
    "selected_incentive_id",
    "credit_issuance_decision",
    "report_charged_lead",
})

_HOOK_FINANCIAL_SUMMARY_RE = re.compile(
    r"(?i)(?:"
    r"billing[_\s]*setup|payments[_\s]*account|account[_\s]*budget|"
    r"campaign[_\s]*budget|\bbudget(?:s|ing)?\b|"
    r"bidding[_\s]*(?:strategy|strategies|seasonality|data[_\s]*exclusion)|"
    r"bid[_\s]*modifier|\b(?:cpc|cpm|cpv|cpa)[_\s]*bid|target[_\s]*(?:cpa|roas|cpm|spend)|"
    r"maximize[_\s]*conversion[_\s]*value|"
    r"book[_\s]*campaigns|\breservation(?:s|service)?\b|"
    r"apply[_\s]*incentive|\bincentive(?:s|service)?\b|"
    r"provide[_\s]*lead[_\s]*feedback|lead[_\s]*credit|"
    r"conversion[_\s]*value[_\s]*rule|upload[_\s]*conversion[_\s]*adjustments|"
    r"restatement[_\s]*value|adjusted[_\s]*value|"
    r"create[_\s]*customer[_\s]*client|"
    r"(?:graduate|promote|schedule)[_\s]*experiment|promote[_\s]*campaign[_\s]*draft|"
    r"(?:amount|bid|cpa|cpm|cpv|spend|spending_limit)[_\s]*micros|\bmicros\b|"
    r"[$€£¥₹]\s*\d|\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|INR|BRL|MXN)\s*\d"
    r")"
)

_HOOK_FINANCIAL_CONSEQUENCE_RE = re.compile(
    r"(?i)(?:"
    r"[$€£¥₹]\s*\d|"
    r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|micros|/(?:day|mo|month|wk|week|yr|year))\b|"
    r"\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|INR|BRL|MXN)\b|"
    r"\b(?:spend|spending|budget|budgets|billing|billable|billed|payment|payments|"
    r"invoice|invoices|charge|charges|charged|cost|costs|monetary|financial|currency|"
    r"price|pricing|fee|fees|credit|credits|credited|refund|incentive|coupon|voucher|"
    r"promotional|booking|booked|guaranteed|reservation|commitment|"
    r"bid|bids|bidding|cpc|cpm|cpv|cpa|roas|modifier|"
    r"conversion\s+value|restatement|retraction|revenue)\b"
    r")"
)


def _hook_payload_has_financial_fields(obj: Any, _depth: int = 0) -> bool:
    """Recursively checks whether a serialized RPC payload contains financial fields."""
    if _depth > 12:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).strip().lower() in _HOOK_FINANCIAL_PAYLOAD_KEYS and v not in (
                None,
                "",
                [],
                {},
            ):
                return True
            if _hook_payload_has_financial_fields(v, _depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _hook_payload_has_financial_fields(item, _depth + 1):
                return True
    return False


def _is_financial_receipt_for_hook(receipt: Dict[str, Any]) -> bool:
    """Returns True if a dry-run receipt represents a financial Google Ads API mutation."""
    if receipt.get("is_financial_transaction") is True:
        return True
    dry_run_calls = receipt.get("dry_run_rpc_calls")
    if isinstance(dry_run_calls, list):
        for call in dry_run_calls:
            if not isinstance(call, dict):
                continue
            svc = str(call.get("service", "")).strip().lower()
            method = str(call.get("method", "")).strip().lower()
            if svc in _HOOK_FINANCIAL_SERVICES or method in _HOOK_FINANCIAL_METHODS:
                return True
            if _hook_payload_has_financial_fields(call.get("request_payload")):
                return True
    combined_text = " | ".join(
        str(receipt.get(field, "")).strip()
        for field in ("operation_summary", "before_state", "after_state")
        if str(receipt.get(field, "")).strip()
    )
    if combined_text and _HOOK_FINANCIAL_SUMMARY_RE.search(combined_text):
        return True
    return False


def _has_financial_consequence_for_hook(consequences: Any) -> bool:
    """Returns True if consequences include explicit financial/monetary impact disclosures."""
    if not isinstance(consequences, list):
        return False
    for item in consequences:
        text = str(item).strip()
        if text and _HOOK_FINANCIAL_CONSEQUENCE_RE.search(text):
            return True
    return False


def _normalize_request_for_hash(obj: Any) -> Any:
    """Normalizes a serialized RPC request payload by recursively stripping validate_only and response_content_type."""
    if isinstance(obj, dict):
        return {
            str(k): _normalize_request_for_hash(v)
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
            if str(k) not in ("validate_only", "response_content_type")
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


_CACHED_RUN_MUTATION_MOD: Any = None


def _load_run_mutation_for_hook() -> Any:
    """Lazily loads and caches the run_mutation module for hook checks."""
    global _CACHED_RUN_MUTATION_MOD
    if _CACHED_RUN_MUTATION_MOD is None:
        import importlib.util

        this_dir = os.path.dirname(os.path.abspath(__file__))
        plugin_root = os.path.abspath(os.path.join(this_dir, ".."))
        rm_path = os.path.join(
            plugin_root, "skills", "execute-mutation", "scripts", "run_mutation.py"
        )
        if os.path.isfile(rm_path):
            spec = importlib.util.spec_from_file_location("_hook_run_mutation", rm_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _CACHED_RUN_MUTATION_MOD = mod
    return _CACHED_RUN_MUTATION_MOD


def _check_prohibited_deletion_for_hook(
    receipt: Optional[Dict[str, Any]] = None,
    script_path: Optional[str] = None,
    code_text: Optional[str] = None,
    operation_summary: str = "",
    after_state: str = "",
) -> Tuple[bool, str, list[Dict[str, Any]]]:
    """Checks for prohibited deletion/remove operations via run_mutation.py."""
    rm_mod = _load_run_mutation_for_hook()
    if rm_mod is not None and hasattr(rm_mod, "check_prohibited_deletion_mutation"):
        ok, err_msg, violations = rm_mod.check_prohibited_deletion_mutation(
            operation_summary=operation_summary,
            after_state=after_state,
            receipt=receipt,
            script_path=script_path,
            code_text=code_text,
        )
        if not ok and err_msg:
            return (
                False,
                f"BLOCKED BY HITL MUTATION GUARD (DELETION PROHIBITED): {err_msg}",
                violations,
            )
    return True, "", []


def _check_financial_limits_for_hook(
    receipt: Optional[Dict[str, Any]] = None,
    script_path: Optional[str] = None,
    code_text: Optional[str] = None,
) -> Tuple[bool, str, list[Dict[str, Any]]]:
    """Checks configured financial transaction upper limits via run_mutation.py."""
    rm_mod = _load_run_mutation_for_hook()
    if rm_mod is not None and hasattr(rm_mod, "check_financial_transaction_limits"):
        ok, err_msg, violations = rm_mod.check_financial_transaction_limits(
            receipt=receipt,
            script_path=script_path,
            code_text=code_text,
        )
        if not ok:
            return (
                False,
                f"BLOCKED BY HITL MUTATION GUARD (FINANCIAL UPPER LIMIT EXCEEDED): {err_msg}",
                violations,
            )
    return True, "", []


def _extract_workspace_cwd(hook_context: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extracts the active workspace directory from hook JSON context if available."""
    if not isinstance(hook_context, dict):
        return None
    tool_call = hook_context.get("toolCall")
    if isinstance(tool_call, dict):
        tc_args = tool_call.get("args")
        if isinstance(tc_args, dict):
            cwd_val = tc_args.get("Cwd") or tc_args.get("cwd")
            if isinstance(cwd_val, str) and cwd_val.strip():
                return cwd_val.strip()
    cwd_top = hook_context.get("cwd")
    if isinstance(cwd_top, str) and cwd_top.strip():
        return cwd_top.strip()
    ws_paths = hook_context.get("workspacePaths")
    if isinstance(ws_paths, list) and ws_paths:
        first_ws = ws_paths[0]
        if isinstance(first_ws, str) and first_ws.strip():
            return first_ws.strip()
    return None


def _resolve_candidate_script_path(
    script_path: Optional[str],
    workspace_cwd: Optional[str] = None,
) -> Optional[str]:
    """Resolves a potentially relative script path against CWD or workspace_cwd."""
    if not script_path:
        return None
    if os.path.isfile(script_path):
        return script_path
    if workspace_cwd and not os.path.isabs(script_path):
        ws_candidate = os.path.join(workspace_cwd, script_path)
        if os.path.isfile(ws_candidate):
            return ws_candidate
    return script_path


def _verify_dry_run_receipt_for_hook(
    script_path: Optional[str] = None,
    max_age_seconds: int = 1800,
    hook_context: Optional[Dict[str, Any]] = None,
    workspace_cwd: Optional[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Checks saved/data/last_dry_run.json for a valid, recent dry-run receipt."""
    from datetime import datetime, timezone
    import hashlib
    import time

    effective_ws = workspace_cwd or _extract_workspace_cwd(hook_context)
    resolved_script_arg = _resolve_candidate_script_path(script_path, effective_ws)

    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, ".."))
    candidate_receipts: list[str] = []
    if effective_ws:
        ws_receipt = os.path.abspath(
            os.path.join(effective_ws, "saved", "data", "last_dry_run.json")
        )
        candidate_receipts.append(ws_receipt)
    for cand in (
        os.path.abspath(os.path.join("saved", "data", "last_dry_run.json")),
        os.path.join(plugin_root, "saved", "data", "last_dry_run.json"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/data/last_dry_run.json"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/saved/data/last_dry_run.json"
        ),
    ):
        if cand not in candidate_receipts:
            candidate_receipts.append(cand)

    receipt: Optional[Dict[str, Any]] = None
    fallback_receipt: Optional[Dict[str, Any]] = None
    matched_receipt_path: Optional[str] = None
    for candidate in candidate_receipts:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data:
                    if str(data.get("status", "")) == "DRY_RUN_PASSED":
                        receipt = data
                        matched_receipt_path = candidate
                        break
                    if fallback_receipt is None:
                        fallback_receipt = data
            except Exception:
                continue

    if receipt is None:
        receipt = fallback_receipt

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

    try:
        ts = float(receipt.get("timestamp", 0.0))
    except (TypeError, ValueError):
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt has a malformed timestamp. "
            "Run a fresh validate_only=True dry-run first.",
            receipt,
        )
    if math.isnan(ts) or math.isinf(ts) or ts <= 0:
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt has an invalid timestamp. "
            "Run a fresh validate_only=True dry-run first.",
            receipt,
        )

    age = time.time() - ts
    if age < -5:
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt timestamp is in the future. "
            "Run a fresh validate_only=True dry-run first.",
            receipt,
        )
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

    del_ok, del_err, _ = _check_prohibited_deletion_for_hook(
        receipt=receipt,
        script_path=resolved_script_arg,
    )
    if not del_ok:
        return (
            False,
            del_err,
            receipt,
        )

    is_financial_txn = _is_financial_receipt_for_hook(receipt)
    if is_financial_txn and not _has_financial_consequence_for_hook(consequences):
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Dry-run receipt for financial mutation in "
            "saved/data/last_dry_run.json is missing explicit monetary, currency, spend, "
            "budget, billing, credit, or bidding impact disclosure in consequences.",
            receipt,
        )

    limits_ok, limits_err, _ = _check_financial_limits_for_hook(
        receipt=receipt,
        script_path=resolved_script_arg,
    )
    if not limits_ok:
        return (
            False,
            limits_err,
            receipt,
        )

    if not resolved_script_arg:
        return (
            False,
            "BLOCKED BY HITL MUTATION GUARD: Direct inline 'python -c' live mutations are prohibited. "
            "Save the mutation script under saved/code/ and run it via skills/execute-mutation/scripts/run_mutation.py.",
            receipt,
        )

    resolved_script = os.path.abspath(resolved_script_arg)
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

    targets_to_update = (
        [matched_receipt_path]
        if matched_receipt_path
        else [c for c in candidate_receipts if os.path.isfile(c)]
    )
    for candidate in targets_to_update:
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
    fin_badge = " [FINANCIAL TRANSACTION]" if is_financial_txn else ""
    prompt_reason = (
        f"⚠️ GOOGLE ADS LIVE MUTATION VERIFICATION{fin_badge} [Customer ID: {receipt.get('customer_id', 'Unknown')}]\n"
        f"• Operation: {receipt.get('operation_summary', 'Unknown')}\n"
        f"• Change: {receipt.get('before_state', 'N/A')} -> {receipt.get('after_state', 'N/A')}\n"
        f"• Request SHA256: {req_sha_display}\n"
        f"• Reversibility: {receipt.get('reversibility', 'UNKNOWN')}\n"
        f"• Consequences: {consequences_formatted}\n"
        f"Confirm execution of this live Google Ads API mutation?"
    )
    return True, prompt_reason, receipt


_TEST_OR_LINTER_CMD_RE = re.compile(
    r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=[^\s]+\s+)*(?:(?:[\w./-]+/)?(?:pytest|ruff|mypy|flake8)(?=\s|$)|"
    r"python3?\s+-m\s+(?:pytest|ruff|mypy|flake8)(?=\s|$))"
)
_CHAIN_SPLIT_RE = re.compile(r"(?:&&|\|\||;|\||\n)")
_DIRECT_REST_MUTATE_RE = re.compile(
    r"(?i)googleads\.googleapis\.com/[^\s'\"]*:(?:mutate[A-Za-z]*|createCustomerClient|"
    r"bookCampaigns|applyIncentive|applyRecommendation|dismissRecommendation|"
    r"uploadClickConversions|uploadCallConversions|uploadConversionAdjustments|"
    r"uploadUserData|createOfflineUserDataJob|addOfflineUserDataJobOperations|"
    r"runOfflineUserDataJob)\b"
)
_SCRIPT_ARG_RE = re.compile(
    r"--script(?:=|\s+)(?:'([^']+)'|\"([^\"]+)\"|([^\s'\"]+))"
)
_OPERATION_ARG_RE = re.compile(
    r"--operation(?:=|\s+)(?:'([^']+)'|\"([^\"]+)\"|([^\s'\"]+))"
)
_AFTER_ARG_RE = re.compile(
    r"--after(?:=|\s+)(?:'([^']+)'|\"([^\"]+)\"|([^\s'\"]+))"
)
_PY_FILE_ARG_RE = re.compile(
    r"(?:'([^']+\.py)'|\"([^\"]+\.py)\"|([^\s'\"]+\.py))"
)
_SH_FILE_ARG_RE = re.compile(
    r"(?:'([^']+\.(?:sh|bash))'|\"([^\"]+\.(?:sh|bash))\"|([^\s'\"]+\.(?:sh|bash)))"
)
_PY_MODULE_ARG_RE = re.compile(r"\bpython3?(?:\.\d+)?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
_SET_EXEC_MUTATES_TRUE_RE = re.compile(
    r"--set-execute-mutates(?:=|\s+)(?:true|1|yes|on)\b", re.IGNORECASE
)
_COMMENT_LINE_RE = re.compile(r"(?m)^\s*#.*$")
_HELP_KW_RE = re.compile(r"\bhelp\s*=\s*(?:'[^']*'|\"[^\"]*\")")
_VALIDATE_ONLY_TRUE_RE = re.compile(
    r"validate_only\s*(?::\s*bool\s*)?=\s*(?:True\b|not\s+args\.execute\b)"
)
_VALIDATE_ONLY_FALSE_RE = re.compile(r"validate_only\s*(?::\s*bool\s*)?=\s*False\b")
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
    r"(['\"])(?:~|/(?:home|Users)/[^/'\"]+|/usr/local/google/home/[^/'\"]+|client_libs/[^/'\"]+)/google-ads\.yaml\1"
)
_BARE_HOME_YAML_RE = re.compile(
    r"(?:~/google-ads\.yaml|/(?:home|Users)/[^/\s'\"]+/google-ads\.yaml|/usr/local/google/home/[^/\s'\"]+/google-ads\.yaml|client_libs/[^/\s'\"]+/google-ads\.yaml)"
)
_SKILL_REL_PATH_RE = re.compile(
    r"\b(?:skills/[a-zA-Z0-9_\-]+/(?:scripts|references)/[a-zA-Z0-9_\-\.]+|config/(?:config_init|set_financial_limits)\.py|set_financial_limits\.py)\b"
)
_LEADING_SHELL_COMMENTS_RE = re.compile(r"\A(?:\s*#[^\n]*\n)+")

_PROTECTED_DENY_FILES = frozenset({"last_dry_run.json", "mutation_audit.jsonl"})
_PROTECTED_ASK_FILES = frozenset({
    "assistant_config",
    "financial_limits",
    "google-ads.yaml",
    "hooks.json",
})
_FILE_WRITE_TOOLS = frozenset({
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
    "Write",
    "Edit",
    "MultiEdit",
})


def evaluate_mutation_guard(
    cmd: str,
    hook_context: Optional[Dict[str, Any]] = None,
    workspace_cwd: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Inspects a shell command for Google Ads API mutations and returns (decision, reason)."""
    if not cmd:
        return "allow", None

    if "googleads.googleapis.com" in cmd and _DIRECT_REST_MUTATE_RE.search(cmd):
        return (
            "deny",
            "BLOCKED BY HITL MUTATION GUARD: Direct REST/HTTP Google Ads API mutations via shell tools "
            "are prohibited. Use skills/execute-mutation/scripts/run_mutation.py with the mandatory "
            "4-Step HITL protocol.",
        )

    effective_ws = workspace_cwd or _extract_workspace_cwd(hook_context)

    # Gate CLI self-modification enabling live mutations via config_init.py
    if "config_init.py" in cmd and _SET_EXEC_MUTATES_TRUE_RE.search(cmd):
        return (
            "force_ask",
            "⚠️ ENABLE LIVE MUTATIONS: Confirm setting 'execute_mutates = true' in config/assistant_config?",
        )

    # Inspect referenced .sh / .bash wrapper scripts (excluding official lifecycle scripts)
    sh_blobs: list[str] = []
    for sh_grp in _SH_FILE_ARG_RE.findall(cmd):
        sh_cand = sh_grp[0] or sh_grp[1] or sh_grp[2]
        if sh_cand and os.path.basename(sh_cand) not in (
            "install.sh",
            "update.sh",
            "plugin.sh",
            "test_plugin_scripts.sh",
        ):
            resolved_sh = _resolve_candidate_script_path(sh_cand, effective_ws)
            if resolved_sh and os.path.isfile(resolved_sh):
                try:
                    with open(resolved_sh, "r", encoding="utf-8") as sf:
                        sh_text = sf.read()
                    if "googleads.googleapis.com" in sh_text and _DIRECT_REST_MUTATE_RE.search(
                        sh_text
                    ):
                        return (
                            "deny",
                            "BLOCKED BY HITL MUTATION GUARD: Direct REST/HTTP Google Ads API mutations "
                            "inside shell scripts are prohibited.",
                        )
                    sh_blobs.append(sh_text)
                except OSError:
                    pass

    effective_cmd = cmd + ("\n" + "\n".join(sh_blobs) if sh_blobs else "")

    if not any(
        tok in effective_cmd
        for tok in ("python", "python3", "run_mutation.py", ".py")
    ):
        return "allow", None

    # Only short-circuit test suites and linters when EVERY chained segment is a test/linter invocation
    segments = [seg.strip() for seg in _CHAIN_SPLIT_RE.split(effective_cmd) if seg.strip()]
    if segments and all(_TEST_OR_LINTER_CMD_RE.search(seg) for seg in segments):
        return "allow", None

    # 1. Explicit invocation of skills/execute-mutation/scripts/run_mutation.py
    if "run_mutation.py" in effective_cmd:
        script_match = _SCRIPT_ARG_RE.search(effective_cmd)
        raw_target_script = (
            script_match.group(1) or script_match.group(2) or script_match.group(3)
            if script_match
            else None
        )
        target_script = _resolve_candidate_script_path(raw_target_script, effective_ws)
        op_match = _OPERATION_ARG_RE.search(effective_cmd)
        op_arg = (
            op_match.group(1) or op_match.group(2) or op_match.group(3)
            if op_match
            else ""
        )
        after_match = _AFTER_ARG_RE.search(effective_cmd)
        after_arg = (
            after_match.group(1) or after_match.group(2) or after_match.group(3)
            if after_match
            else ""
        )
        del_ok, del_err, _ = _check_prohibited_deletion_for_hook(
            script_path=target_script,
            operation_summary=op_arg,
            after_state=after_arg,
        )
        if not del_ok:
            return "deny", del_err

        if "--record-only" in effective_cmd:
            return (
                "force_ask",
                "⚠️ RECORD-ONLY DRY-RUN RECEIPT: Confirm recording a dry-run receipt without executing "
                "a live validate_only=True Google Ads API call?",
            )

        if "--dry-run" in effective_cmd and "--execute" not in effective_cmd:
            return "allow", None
        if "--execute" in effective_cmd:
            if not is_execute_mutates_enabled():
                return (
                    "deny",
                    "BLOCKED BY HITL MUTATION GUARD: Mutate support is disabled by configuration "
                    "(execute_mutates = false in config/assistant_config). Set 'execute_mutates = true' in "
                    "config/assistant_config to enable live Google Ads API mutations.",
                )
            ok, message, _ = _verify_dry_run_receipt_for_hook(
                script_path=target_script,
                hook_context=hook_context,
                workspace_cwd=effective_ws,
            )
            return ("force_ask", message) if ok else ("deny", message)

    # 2. Direct execution of a .py script, python -m module, or python -c snippet
    script_candidates = _PY_FILE_ARG_RE.findall(effective_cmd)
    py_files: list[str] = []
    for grp in script_candidates:
        candidate = grp[0] or grp[1] or grp[2]
        if candidate and os.path.basename(candidate) not in _READONLY_SKILL_SCRIPTS_SET:
            py_files.append(candidate)

    for mod_name in _PY_MODULE_ARG_RE.findall(effective_cmd):
        if mod_name not in ("pytest", "ruff", "mypy", "flake8", "pip", "venv", "json.tool"):
            rel_mod = mod_name.replace(".", os.sep)
            for mod_cand in (f"{rel_mod}.py", os.path.join(rel_mod, "__main__.py")):
                resolved_mod = _resolve_candidate_script_path(mod_cand, effective_ws)
                if resolved_mod and os.path.isfile(resolved_mod):
                    py_files.append(resolved_mod)
                    break

    code_blobs: list[str] = [effective_cmd]
    resolved_target_script: Optional[str] = None
    for py_file in py_files:
        resolved_py = _resolve_candidate_script_path(py_file, effective_ws)
        if resolved_py and os.path.isfile(resolved_py):
            resolved_target_script = resolved_py
            try:
                with open(resolved_py, "r", encoding="utf-8") as f:
                    code_blobs.append(f.read())
            except OSError:
                pass

    combined_code = "\n".join(code_blobs)
    uncommented_code = _COMMENT_LINE_RE.sub("", combined_code)

    if not MUTATION_CALL_PATTERN.search(uncommented_code):
        return "allow", None

    del_ok, del_err, _ = _check_prohibited_deletion_for_hook(
        script_path=resolved_target_script,
        code_text=uncommented_code,
    )
    if not del_ok:
        return "deny", del_err

    limits_ok, limits_err, _ = _check_financial_limits_for_hook(
        script_path=resolved_target_script,
        code_text=uncommented_code,
    )
    if not limits_ok:
        return "deny", limits_err

    # A Google Ads mutation method is present in the executed code.
    explicit_execute_flag = "--execute" in cmd
    sanitized_for_vo = _HELP_KW_RE.sub("", uncommented_code)

    has_validate_only_true = bool(_VALIDATE_ONLY_TRUE_RE.search(sanitized_for_vo))
    has_validate_only_false = bool(_VALIDATE_ONLY_FALSE_RE.search(sanitized_for_vo))
    has_non_validate_only_call = bool(_NON_VALIDATE_ONLY_CALL_RE.search(uncommented_code))

    if (
        has_validate_only_true
        and not has_validate_only_false
        and not has_non_validate_only_call
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
        workspace_cwd=effective_ws,
    )
    return ("force_ask", message) if ok else ("deny", message)


def _should_run_first_prompt_parity(input_data: Dict[str, Any]) -> bool:
    """Determines whether to run first-prompt parity checks, deduplicating per session."""
    if input_data.get("parentConversationId") or input_data.get("isSubagent"):
        return False
    invocation_num = input_data.get("invocationNum", 1)
    execution_num = input_data.get("executionNum")
    if isinstance(execution_num, int) and execution_num > 1:
        return False
    is_candidate_first = (invocation_num == 1) or ("invocationNum" not in input_data)
    if not is_candidate_first:
        return False

    conv_id = input_data.get("conversationId") or input_data.get("session_id")
    if not conv_id or os.environ.get("PYTEST_CURRENT_TEST"):
        return True

    import hashlib
    import tempfile

    uid_tag = str(os.getuid()) if hasattr(os, "getuid") else "user"
    conv_hash = hashlib.sha256(str(conv_id).encode("utf-8")).hexdigest()[:24]
    marker_dir = os.path.join(tempfile.gettempdir(), f"gads_assistant_sessions_{uid_tag}")
    marker_path = os.path.join(marker_dir, f"{conv_hash}.seen")
    if os.path.isfile(marker_path):
        return False
    try:
        os.makedirs(marker_dir, mode=0o700, exist_ok=True)
        fd = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
    except FileExistsError:
        return False
    except OSError:
        pass
    return True


def handle_hook() -> None:
    """Handles Jetski and Claude Code CLI lifecycle hook execution (PreInvocation and PreToolUse)."""
    input_data: Dict[str, Any] = {}
    raw_stdin = ""
    if not sys.stdin.isatty():
        try:
            raw_stdin = sys.stdin.read()
            if raw_stdin.strip():
                parsed = json.loads(raw_stdin)
                if isinstance(parsed, dict):
                    input_data = parsed
                elif "toolCall" in raw_stdin or "tool_input" in raw_stdin:
                    print(
                        json.dumps(
                            {
                                "decision": "deny",
                                "reason": "BLOCKED BY HITL MUTATION GUARD: Malformed hook JSON payload.",
                            }
                        )
                    )
                    return
        except Exception:
            if "toolCall" in raw_stdin or "tool_input" in raw_stdin:
                print(
                    json.dumps(
                        {
                            "decision": "deny",
                            "reason": "BLOCKED BY HITL MUTATION GUARD: Malformed hook JSON payload.",
                        }
                    )
                )
                return

    if not is_plugin_enabled():
        if "toolCall" in input_data or "tool_input" in input_data:
            print(json.dumps({"decision": "allow"}))
        else:
            print(json.dumps({}))
        return

    try:
        config_path = sync_and_set_config_kv()
    except Exception:
        config_path = os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        )

    # 1. PreToolUse hook (shell execution & protected file-write interception)
    if "toolCall" in input_data or "tool_input" in input_data:
        tool_call = input_data.get("toolCall", {})
        tool_name = str(
            (tool_call.get("name") if isinstance(tool_call, dict) else None)
            or input_data.get("tool_name")
            or ""
        )
        if isinstance(tool_call, dict) and "args" in tool_call:
            args = tool_call.get("args", {})
        else:
            args = input_data.get("tool_input", {})
        if not isinstance(args, dict):
            args = {}

        is_claude = "tool_input" in input_data or bool(os.environ.get("CLAUDE_CODE"))

        # Check file-write tool calls targeting protected receipts, audit logs, or guardrail configs
        target_file = (
            args.get("TargetFile")
            or args.get("file_path")
            or args.get("path")
            or ""
        )
        cmd = args.get("CommandLine") or args.get("command") or ""
        if (tool_name in _FILE_WRITE_TOOLS or (target_file and not cmd)) and isinstance(
            target_file, str
        ):
            base = os.path.basename(target_file.strip())
            if base in _PROTECTED_DENY_FILES:
                reason_fw = (
                    f"BLOCKED BY HITL MUTATION GUARD: Direct file writes to '{base}' are prohibited. "
                    "Receipts and audit logs may only be written by run_mutation.py."
                )
                deny_fw: Dict[str, Any] = {"decision": "deny", "reason": reason_fw}
                if is_claude:
                    deny_fw["permissionDecision"] = "deny"
                    deny_fw["permissionDecisionReason"] = reason_fw
                print(json.dumps(deny_fw))
                return
            if base in _PROTECTED_ASK_FILES:
                reason_cfg = (
                    f"⚠️ PROTECTED CONFIGURATION EDIT: Confirm modification of '{target_file}'?"
                )
                ask_fw: Dict[str, Any] = {"decision": "force_ask", "reason": reason_cfg}
                if is_claude:
                    ask_fw["permissionDecision"] = "ask"
                    ask_fw["permissionDecisionReason"] = reason_cfg
                print(json.dumps(ask_fw))
                return
            print(json.dumps({"decision": "allow"}))
            return

        workspace_cwd = _extract_workspace_cwd(input_data)
        decision, reason = evaluate_mutation_guard(
            cmd,
            hook_context=input_data,
            workspace_cwd=workspace_cwd,
        )
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
            updated_cmd = _LEADING_SHELL_COMMENTS_RE.sub("", cmd)
            if not updated_cmd.strip():
                updated_cmd = cmd

            # Resolve assistant plugin root directory
            this_dir = os.path.dirname(os.path.abspath(__file__))
            plugin_root = os.path.abspath(os.path.join(this_dir, ".."))
            global_plugin_dir = os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant"
            )
            claude_plugin_dir = os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant"
            )
            if not os.path.isdir(os.path.join(plugin_root, "skills")):
                if os.path.isdir(global_plugin_dir):
                    plugin_root = global_plugin_dir
                elif os.path.isdir(claude_plugin_dir):
                    plugin_root = claude_plugin_dir

            env_dir = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("GOOGLE_ADS_ASSISTANT_DIR")
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

            # Case F: skills/<skill_name>/(scripts|references)/<file> and config/config_init.py path resolution
            if any(ptok in updated_cmd for ptok in ("python", ".py")):
                def _resolve_skill_path(match: re.Match) -> str:
                    rel_path = match.group(0)
                    if os.path.exists(rel_path):
                        return rel_path
                    if workspace_cwd and os.path.exists(os.path.join(workspace_cwd, rel_path)):
                        return rel_path
                    for candidate_root in (plugin_root, global_plugin_dir, claude_plugin_dir):
                        target = os.path.join(candidate_root, rel_path)
                        if os.path.exists(target):
                            return target
                    return rel_path

                updated_cmd = _SKILL_REL_PATH_RE.sub(
                    _resolve_skill_path,
                    updated_cmd,
                )

            def _escape_dq(val: str) -> str:
                return (
                    val.replace("\\", "\\\\")
                    .replace('"', '\\"')
                    .replace("$", "\\$")
                    .replace("`", "\\`")
                    .replace("\r", "")
                    .replace("\n", "")
                )

            escaped_cfg = _escape_dq(config_path)
            escaped_root = _escape_dq(plugin_root)
            escaped_cfg_dir = _escape_dq(os.path.join(plugin_root, "config"))

            # Ensure GOOGLE_ADS_CONFIGURATION_FILE_PATH is exported in the subshell
            if "GOOGLE_ADS_CONFIGURATION_FILE_PATH" not in updated_cmd:
                updated_cmd = (
                    f'export GOOGLE_ADS_CONFIGURATION_FILE_PATH="{escaped_cfg}" && {updated_cmd}'
                )

            # Ensure GOOGLE_ADS_ASSISTANT_DIR is exported in the subshell
            if "GOOGLE_ADS_ASSISTANT_DIR" not in updated_cmd:
                updated_cmd = (
                    f'export GOOGLE_ADS_ASSISTANT_DIR="{escaped_root}" && {updated_cmd}'
                )

            # Ensure PYTHONPATH includes the plugin config directory so sitecustomize.py resolves config/ paths
            plugin_config_dir = os.path.join(plugin_root, "config")
            if "PYTHONPATH" not in updated_cmd and os.path.isdir(plugin_config_dir):
                updated_cmd = (
                    f'export PYTHONPATH="{escaped_cfg_dir}${{PYTHONPATH:+:$PYTHONPATH}}" && {updated_cmd}'
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
            if is_claude:
                response_payload["hookSpecificOutput"] = {
                    "hookEventName": "PreToolUse",
                    "updatedInput": {**args, **overwrite},
                }

        print(json.dumps(response_payload))
        return

    # 2. PreInvocation / SessionStart hook (model prompt injection & deduplicated first-prompt parity check)
    is_first_prompt = _should_run_first_prompt_parity(input_data)

    mutates_enabled = is_execute_mutates_enabled()
    mutates_state_str = "execute_mutates = true" if mutates_enabled else "execute_mutates = false"

    if is_first_prompt:
        parity_info: Dict[str, Any] = check_python_client_lib_parity(
            check_github=not bool(os.environ.get("PYTEST_CURRENT_TEST")),
            check_pypi=not bool(os.environ.get("PYTEST_CURRENT_TEST")),
        )

        active_api_version = (
            parity_info.get("api_version")
            or get_configured_api_version()
            or detect_latest_api_version()
        )
        table_markdown = parity_info.get("table_markdown") or format_parity_table_markdown(
            parity_info, active_api_version
        )

        msg = (
            f"CRITICAL GOOGLE ADS CONFIGURATION & HITL MUTATION NOTICE:\n"
            f"1. The active Google Ads API configuration file is at: {config_path} (or config/google-ads.yaml), with active api_version = \"{active_api_version}\".\n"
            f"   All Python client initializations MUST explicitly pass path='config/google-ads.yaml' to GoogleAdsClient.load_from_storage(path='config/google-ads.yaml').\n"
            f"2. HITL MUTATION VERIFICATION & AUDIT MANDATE ({mutates_state_str} in config/assistant_config): "
            f"Live mutations are currently {'ENABLED' if mutates_enabled else 'DISABLED (set execute_mutates = true in config/assistant_config to enable)'}. "
            f"Only 'create' and 'update' mutations are allowed; deletion ('remove') operations are strictly prohibited. "
            f"Before executing ANY live Google Ads mutation, you MUST:\n"
            f"   (a) Ensure execute_mutates = true is configured in config/assistant_config,\n"
            f"   (b) Query current resource state via GAQL,\n"
            f"   (c) Execute a validate_only=True dry-run via skills/execute-mutation/scripts/run_mutation.py --dry-run to generate saved/data/last_dry_run.json,\n"
            f"   (d) Disclose the exact financial/serving/structural consequences to the user and wait for explicit confirmation before calling --execute (which appends to saved/logs/mutation_audit.jsonl).\n"
            f"3. RUNNABLE CODE STORAGE MANDATE: When asked to save code that can be run later, it MUST strictly be saved in the current working directory in a sub-directory called 'saved' (e.g., ./saved/ or ./saved/code/).\n"
            f"4. STARTUP CLIENT LIBRARY & SITE-DIRECTORY PARITY VERIFICATION (FIRST PROMPT ENTRY):\n"
            f"   - (1) google-ads in site directory vs pypi.org: Installed = {parity_info.get('system_version') or 'NOT INSTALLED'}, Latest PyPI = {parity_info.get('pypi_version') or 'UNKNOWN'}\n"
            f"   - (2) client_libs/google-ads-python vs GitHub: Local = {parity_info.get('local_version') or 'NOT INSTALLED'}, Latest GitHub = {parity_info.get('github_version') or 'UNKNOWN'}\n"
            f"   - (3) Determined Google Ads API Version to use: {active_api_version}\n\n"
            f"   Parity Table:\n{table_markdown}\n\n"
            f"   MANDATORY FIRST-PROMPT DIRECTIVE:\n"
            f"   Because the user has entered their first prompt in this session, you MUST present this version verification table to the user at the very beginning of your response.\n"
        )
        if parity_info.get("upgrade_prompt_required"):
            msg += (
                "   Because one or more components are not the latest version, you MUST ask the user if they want to update them before proceeding:\n"
                "   - If the user replies YES: run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --upgrade_system` to install the latest version of google-ads from pypi.org into the site directory, install the latest version of the client library into the site directory, update client_libs/google-ads-python in the Assistant directory structure, update api_version in config/assistant_config (and config/api_version.txt if present) to the latest version, and print the results to the screen.\n"
                "   - If the user replies NO: proceed using the currently active versions."
            )
        else:
            msg += (
                "   All Google Ads components are up to date and match the latest upstream releases. State this, confirm active API version, and proceed directly to answer the user's prompt."
            )
    else:
        active_api_version = get_configured_api_version() or detect_latest_api_version()
        msg = (
            f"CRITICAL GOOGLE ADS CONFIGURATION & HITL MUTATION NOTICE:\n"
            f"1. The active Google Ads API configuration file is at: {config_path} (or config/google-ads.yaml), with active api_version = \"{active_api_version}\".\n"
            f"   All Python client initializations MUST explicitly pass path='config/google-ads.yaml' to GoogleAdsClient.load_from_storage(path='config/google-ads.yaml').\n"
            f"2. HITL MUTATION VERIFICATION & AUDIT MANDATE ({mutates_state_str} in config/assistant_config): "
            f"Live mutations are currently {'ENABLED' if mutates_enabled else 'DISABLED (set execute_mutates = true in config/assistant_config to enable)'}. "
            f"Only 'create' and 'update' mutations are allowed; deletion ('remove') operations are strictly prohibited.\n"
            f"3. RUNNABLE CODE STORAGE MANDATE: When asked to save code that can be run later, it MUST strictly be saved in the current working directory in a sub-directory called 'saved' (e.g., ./saved/ or ./saved/code/).\n"
            f"4. ACTIVE API CONFIGURATION: Active Google Ads API version: \"{active_api_version}\". Parity verification was completed on the first prompt."
        )

    response_payload = {
        "injectSteps": [
            {
                "ephemeralMessage": msg,
            }
        ]
    }
    print(json.dumps(response_payload))


def main() -> None:
    """Initializes config/google-ads.yaml from ~/google-ads.yaml at session start."""
    import argparse

    if "--hook" in sys.argv or (not sys.stdin.isatty() and len(sys.argv) == 1):
        handle_hook()
        return

    parser = argparse.ArgumentParser(
        description="Initialize config/google-ads.yaml from ~/google-ads.yaml and manage plugin configuration."
    )
    parser.add_argument("--key", default="login_customer_id", help="Config key to set or verify")
    parser.add_argument("--value", default=None, help="Config value to set")
    parser.add_argument(
        "--execute-mutates",
        default=None,
        choices=["true", "false"],
        help="Configure whether the plugin supports live mutations (execute_mutates = <true, false> in config/assistant_config)",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Enable the plugin so it is active in Jetski/Antigravity and Claude Code sessions",
    )
    parser.add_argument(
        "--disable",
        action="store_true",
        help="Disable the plugin so it is not invoked in Jetski/Antigravity and Claude Code sessions",
    )
    parser.add_argument(
        "--plugin-enabled",
        default=None,
        choices=["true", "false"],
        help="Explicitly set enabled = <true, false> in config/assistant_config and update plugin manifests",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report the current enabled/disabled status of the plugin and exit",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output plugin status in JSON format when used with --status, --enable, or --disable",
    )
    parser.add_argument(
        "--target",
        default="all",
        choices=["agy", "claude", "all"],
        help="Target platform when enabling or disabling the plugin (default: all)",
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

    if args.enable and args.disable:
        print("[config_init] Error: Cannot specify both --enable and --disable.", file=sys.stderr)
        sys.exit(2)

    if args.enable or args.disable:
        target_state = True if args.enable else False
        set_plugin_enabled(
            target_state,
            config_dir=args.config_dir,
            target_type=args.target,
        )
        status_info = get_plugin_status(config_dir=args.config_dir)
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(format_plugin_status_text(status_info))
        return

    if args.status:
        status_info = get_plugin_status(config_dir=args.config_dir)
        if args.json:
            print(json.dumps(status_info, indent=2))
        else:
            print(format_plugin_status_text(status_info))
        return

    if args.execute_mutates is not None:
        set_execute_mutates(args.execute_mutates.lower() == "true", config_dir=args.config_dir)

    if args.plugin_enabled is not None:
        set_plugin_enabled(
            args.plugin_enabled.lower() == "true",
            config_dir=args.config_dir,
            target_type=args.target,
        )

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
        if args.plugin_enabled is not None:
            set_plugin_enabled(
                args.plugin_enabled.lower() == "true",
                config_dir=args.config_dir,
                target_type=args.target,
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

