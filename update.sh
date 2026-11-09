#!/bin/bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Description:
#   This script updates the Google Ads API Developer Assistant and its dependencies.
#   It supports updating either the standalone project or the installed plugin.

# Exit on any error, and on undefined variables.
set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

readonly AGY_PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
readonly CLAUDE_MARKETPLACE_DIR="${HOME}/.claude/plugins/google-ads-assistant-local"
readonly CLAUDE_PLUGIN_TARGET_DIR="${CLAUDE_MARKETPLACE_DIR}/plugins/google-ads-api-developer-assistant"

# --- Defaults ---
TYPE=""
INSTALL_PYTHON=false
INSTALL_PHP=false
INSTALL_RUBY=false
INSTALL_JAVA=false
INSTALL_DOTNET=false
ANY_SELECTED=false
CUSTOMER_ID=""
PLUGIN_ENABLED_OPT=""
STATUS_ONLY=false

# --- Help Function ---
usage() {
  echo "Usage: $0 <agy|claude> [OPTIONS]"
  echo "       $0 --type <agy|claude> [OPTIONS]"
  echo "  Updates the Google Ads API Developer Assistant plugin and configured client libraries for Antigravity or Claude Code."
  echo ""
  echo "  Required Argument:"
  echo "    <agy|claude>               Target platform: 'agy' (Antigravity) or 'claude' (Claude Code)"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --type TYPE                Target platform ('agy' or 'claude')"
  echo "    --agy                      Update Antigravity plugin (shorthand for --type agy)"
  echo "    --claude                   Update Claude Code plugin (shorthand for --type claude)"
  echo "    --cid, --customer-id CID   Default Google Ads Customer ID (e.g. 1234567890)"
  echo "    --enable                   Enable the plugin after updating"
  echo "    --disable, --disabled      Disable the plugin after updating"
  echo "    --status                   Show the current enabled/disabled status of the plugin and exit"
  echo "    --all                      Ensure all client libraries are present and updated in plugin"
  echo "    --python                   Ensure google-ads-python is present and updated in plugin"
  echo "    --php                      Ensure google-ads-php is present and updated in plugin"
  echo "    --ruby                     Ensure google-ads-ruby is present and updated in plugin"
  echo "    --java                     Ensure google-ads-java is present and updated in plugin"
  echo "    --dotnet                   Ensure google-ads-dotnet is present and updated in plugin"
  echo ""
  echo "  Examples:"
  echo "    $0 agy                     (Updates repository, Antigravity plugin, and client libraries)"
  echo "    $0 agy --disable           (Updates Antigravity plugin and leaves it disabled)"
  echo "    $0 claude                  (Updates repository, Claude Code plugin, and client libraries)"
  echo "    $0 agy --java              (Ensures Java library is added/updated in Antigravity plugin)"
  echo "    $0 claude --php --dotnet   (Ensures PHP and .NET libraries are added/updated in Claude Code plugin)"
  echo ""
}

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    [aA][gG][yY]|[cC][lL][aA][uU][dD][eE]|[cC][lL][aA][uU][dD][eE][cC][oO][dD][eE]|[aA][lL][lL])
      TYPE=$(echo "$1" | tr '[:upper:]' '[:lower:]')
      if [[ "${TYPE}" == "claudecode" ]]; then
        TYPE="claude"
      fi
      shift
      ;;
    --type)
      if [[ $# -lt 2 ]]; then
        err "ERROR: --type requires an argument ('agy' or 'claude')."
        usage
        exit 1
      fi
      TYPE=$(echo "$2" | tr '[:upper:]' '[:lower:]')
      if [[ "${TYPE}" == "claudecode" ]]; then
        TYPE="claude"
      fi
      shift 2
      ;;
    --type=*)
      TYPE=$(echo "${1#*=}" | tr '[:upper:]' '[:lower:]')
      if [[ "${TYPE}" == "claudecode" ]]; then
        TYPE="claude"
      fi
      shift
      ;;
    --agy)
      TYPE="agy"
      shift
      ;;
    --claude|--claudecode)
      TYPE="claude"
      shift
      ;;
    --cid|--customer-id|--customer_id)
      if [[ $# -lt 2 ]]; then
        err "ERROR: $1 requires an argument."
        exit 1
      fi
      CUSTOMER_ID="$2"
      shift 2
      ;;
    --cid=*|--customer-id=*|--customer_id=*)
      CUSTOMER_ID="${1#*=}"
      shift
      ;;
    --enable|--enabled)
      PLUGIN_ENABLED_OPT="true"
      shift
      ;;
    --disable|--disabled)
      PLUGIN_ENABLED_OPT="false"
      shift
      ;;
    --status)
      STATUS_ONLY=true
      shift
      ;;
    --all)
      INSTALL_PYTHON=true
      INSTALL_PHP=true
      INSTALL_RUBY=true
      INSTALL_JAVA=true
      INSTALL_DOTNET=true
      ANY_SELECTED=true
      shift
      ;;
    --python)
      INSTALL_PYTHON=true
      ANY_SELECTED=true
      shift
      ;;
    --php)
      INSTALL_PHP=true
      ANY_SELECTED=true
      shift
      ;;
    --ruby)
      INSTALL_RUBY=true
      ANY_SELECTED=true
      shift
      ;;
    --java)
      INSTALL_JAVA=true
      ANY_SELECTED=true
      shift
      ;;
    --dotnet)
      INSTALL_DOTNET=true
      ANY_SELECTED=true
      shift
      ;;
    *)
      err "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "${STATUS_ONLY}" == "true" ]]; then
  SCRIPT_DIR_TMP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec "${SCRIPT_DIR_TMP}/plugin.sh" status "${TYPE:-all}"
fi

# --- Validate Required Type ---
if [[ -z "${TYPE}" ]]; then
  err "ERROR: Missing required type argument: 'agy' or 'claude'."
  usage
  exit 1
fi

if [[ "${TYPE}" != "agy" && "${TYPE}" != "claude" ]]; then
  err "ERROR: Invalid type '${TYPE}'. Must be 'agy' or 'claude'."
  usage
  exit 1
fi

# Helper functions for repo info
get_repo_url() {
  case "$1" in
    python) echo "https://github.com/googleads/google-ads-python.git" ;;
    php)    echo "https://github.com/googleads/google-ads-php.git" ;;
    ruby)   echo "https://github.com/googleads/google-ads-ruby.git" ;;
    java)   echo "https://github.com/googleads/google-ads-java.git" ;;
    dotnet) echo "https://github.com/googleads/google-ads-dotnet.git" ;;
  esac
}

get_repo_name() {
  case "$1" in
    python) echo "google-ads-python" ;;
    php)    echo "google-ads-php" ;;
    ruby)   echo "google-ads-ruby" ;;
    java)   echo "google-ads-java" ;;
    dotnet) echo "google-ads-dotnet" ;;
  esac
}

is_enabled() {
  case "$1" in
    python) [[ "${INSTALL_PYTHON}" == "true" ]] ;;
    php)    [[ "${INSTALL_PHP}"    == "true" ]] ;;
    ruby)   [[ "${INSTALL_RUBY}"   == "true" ]] ;;
    java)   [[ "${INSTALL_JAVA}"   == "true" ]] ;;
    dotnet) [[ "${INSTALL_DOTNET}" == "true" ]] ;;
  esac
}

# Disable background git maintenance/gc to prevent transient .git/objects/maintenance.lock races during cp -r
export GIT_CONFIG_PARAMETERS="'maintenance.auto=false' 'gc.auto=0' 'gc.autoDetach=false'"

# Helper to safely copy a directory (including git repos) without failing on transient git lock files
safe_copy_dir() {
  local src="$1"
  local dest="$2"
  find "${src}" -type f \( -name "maintenance.lock" -o -name "gc.pid" -o -name "gc.log.lock" \) -path "*/.git/*" -delete 2>/dev/null || true
  if ! cp -r "${src}" "${dest}" 2>/dev/null; then
    sleep 1
    rm -rf "${dest}"
    find "${src}" -type f \( -name "maintenance.lock" -o -name "gc.pid" -o -name "gc.log.lock" \) -path "*/.git/*" -delete 2>/dev/null || true
    cp -r "${src}" "${dest}"
  fi
}

# Helper to safely update a git repository even if HEAD is detached (e.g., checked out at a release tag)
update_git_repo() {
  local repo_dir="$1"
  (
    cd "${repo_dir}"
    if ! git symbolic-ref -q HEAD >/dev/null 2>&1; then
      local default_branch=""
      default_branch=$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||' || true)
      if [[ -z "${default_branch}" ]]; then
        for candidate in main master; do
          if git show-ref --verify --quiet "refs/heads/${candidate}" || git show-ref --verify --quiet "refs/remotes/origin/${candidate}"; then
            default_branch="${candidate}"
            break
          fi
        done
      fi
      if [[ -n "${default_branch}" ]]; then
        if git show-ref --verify --quiet "refs/heads/${default_branch}"; then
          git checkout "${default_branch}" >/dev/null 2>&1 || true
        else
          git checkout -B "${default_branch}" "origin/${default_branch}" >/dev/null 2>&1 || true
        fi
        git branch --set-upstream-to="origin/${default_branch}" "${default_branch}" >/dev/null 2>&1 || true
      fi
    fi
    git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
  )
}

# Helper to merge non-zero user-configured key=value overrides onto the newly copied financial_limits template
merge_financial_limits() {
  local template_file="$1"
  local backup_file="$2"
  if [[ ! -f "${backup_file}" ]]; then
    return 0
  fi
  if [[ ! -f "${template_file}" ]]; then
    cp "${backup_file}" "${template_file}"
    chmod 600 "${template_file}" 2>/dev/null || true
    return 0
  fi

  local py_cmd=""
  for cmd in python3 python; do
    if command -v "${cmd}" &>/dev/null && "${cmd}" -c "import sys" &>/dev/null; then
      py_cmd="${cmd}"
      break
    fi
  done

  if [[ -n "${py_cmd}" ]]; then
    "${py_cmd}" - "${template_file}" "${backup_file}" <<'PYEOF'
import os
import re
import sys

template_path, backup_path = sys.argv[1], sys.argv[2]
overrides = {}
section = ""

with open(backup_path, "r", encoding="utf-8") as bf:
    for raw in bf:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        sec_m = re.match(r"^\[([A-Za-z0-9_.]+)\]$", line)
        if sec_m:
            section = sec_m.group(1)
            continue
        kv_m = re.match(r"^([A-Za-z0-9_.]+)\s*=\s*(.+)$", line)
        if kv_m:
            key = kv_m.group(1).strip()
            val_str = kv_m.group(2).strip().strip("\"'")
            if section and "." not in key:
                key = f"{section}.{key}"
            try:
                if float(val_str) != 0.0:
                    overrides[key] = val_str
            except ValueError:
                pass

if overrides:
    with open(template_path, "r", encoding="utf-8") as tf:
        t_lines = tf.readlines()
    applied = set()
    out_lines = []
    line_re = re.compile(r"^(\s*)([A-Za-z0-9_.]+)(\s*=\s*)([^#\r\n]+?)(\s*#.*)?(\r?\n?)$")
    for raw in t_lines:
        m = line_re.match(raw)
        if m and m.group(2) in overrides:
            key = m.group(2)
            applied.add(key)
            comment = m.group(5) or ""
            nl = m.group(6) or "\n"
            out_lines.append(f"{m.group(1)}{key}{m.group(3)}{overrides[key]}{comment}{nl}")
        else:
            out_lines.append(raw)
    for k, v in overrides.items():
        if k not in applied:
            if out_lines and not out_lines[-1].endswith("\n"):
                out_lines[-1] += "\n"
            out_lines.append(f"{k} = {v}\n")
    with open(template_path, "w", encoding="utf-8") as tf:
        tf.writelines(out_lines)
    try:
        os.chmod(template_path, 0o600)
    except OSError:
        pass
PYEOF
  fi
  chmod 600 "${template_file}" 2>/dev/null || true
}

# Helper to detect latest API version from client_libs and pre-seed config/assistant_config
detect_and_seed_api_version() {
  local search_dir="$1"
  local target_config_dir="$2"
  local latest_v=""

  if [[ -d "${search_dir}" ]]; then
    latest_v=$(find "${search_dir}" -mindepth 1 -maxdepth 1 -type d -name 'v*' 2>/dev/null | sed 's/.*\/v//' | grep -E '^[0-9]+$' | sort -n | tail -n 1 || true)
  fi

  if [[ -n "${latest_v}" || -n "${CUSTOMER_ID}" ]]; then
    mkdir -p "${target_config_dir}"
    local cfg_file="${target_config_dir}/assistant_config"
    local api_ver="v26"
    if [[ -n "${latest_v}" ]]; then
      api_ver="v${latest_v}"
    fi
    local cid="12345678"
    local exec_mutates="false"
    local plugin_enabled="true"
    if [[ -f "${cfg_file}" ]]; then
      if [[ -z "${latest_v}" ]]; then
        local existing_ver=""
        existing_ver=$(grep -E '^[[:space:]]*api_version[[:space:]]*=' "${cfg_file}" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*api_version[[:space:]]*=[[:space:]]*["'\'']?([^"'\''#[:space:]]+)["'\'']?.*$/\1/' || true)
        if [[ -n "${existing_ver}" ]]; then
          api_ver="${existing_ver}"
        fi
      fi
      local existing_cid=""
      existing_cid=$(grep -E '^[[:space:]]*customer_id[[:space:]]*=' "${cfg_file}" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*customer_id[[:space:]]*=[[:space:]]*["'\'']?([^"'\''#[:space:]]+)["'\'']?.*$/\1/' || true)
      if [[ -n "${existing_cid}" ]]; then
        cid="${existing_cid}"
      fi
      local existing_em=""
      existing_em=$(grep -E '^[[:space:]]*execute_mutates[[:space:]]*=' "${cfg_file}" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*execute_mutates[[:space:]]*=[[:space:]]*["'\'']?(true|false|TRUE|FALSE)["'\'']?.*$/\1/' | tr '[:upper:]' '[:lower:]' || true)
      if [[ "${existing_em}" == "true" || "${existing_em}" == "false" ]]; then
        exec_mutates="${existing_em}"
      fi
      local existing_en=""
      existing_en=$(grep -E '^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=' "${cfg_file}" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=[[:space:]]*["'\'']?(true|false|TRUE|FALSE)["'\'']?.*$/\2/' | tr '[:upper:]' '[:lower:]' || true)
      if [[ "${existing_en}" == "true" || "${existing_en}" == "false" ]]; then
        plugin_enabled="${existing_en}"
      fi
    fi
    if [[ -n "${PLUGIN_ENABLED_OPT}" ]]; then
      plugin_enabled="${PLUGIN_ENABLED_OPT}"
    fi
    if [[ -n "${CUSTOMER_ID}" ]]; then
      cid=$(echo "${CUSTOMER_ID}" | sed -E 's/^[[:space:]"'\'']+|[[:space:]"'\'']+$//g; s/-//g')
    elif [[ "${cid}" == "12345678" ]]; then
      for legacy_file in \
        "${target_config_dir}/customer_id" \
        "${target_config_dir}/customer_id.txt" \
        "${TEMP_CONFIG_DIR}/legacy_customer_id" \
        "${TEMP_CONFIG_DIR}/legacy_customer_id.txt" \
        "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant/config/customer_id" \
        "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant/config/customer_id.txt"; do
        if [[ -f "${legacy_file}" ]]; then
          local legacy_cid=""
          legacy_cid=$(head -n 1 "${legacy_file}" 2>/dev/null | sed -E 's/^[[:space:]"'\'']+|[[:space:]"'\'']+$//g' || true)
          if [[ -n "${legacy_cid}" && "${legacy_cid}" != "12345678" ]]; then
            cid="${legacy_cid}"
            break
          fi
        fi
      done
    fi
    cat <<EOF > "${cfg_file}"
api_version = "${api_ver}"
customer_id = "${cid}"
execute_mutates = ${exec_mutates}
enabled = ${plugin_enabled}
EOF
    chmod 600 "${cfg_file}" 2>/dev/null || true
    echo "Configured API version ${api_ver} in ${cfg_file}"
  fi
}

# --- Dependency Check ---
if ! command -v git &> /dev/null; then
  err "ERROR: git is not installed. Please install it to continue."
  exit 1
fi

# --- Project Directory Resolution ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR_ABS=""
if candidate=$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null) && [[ -d "${candidate}/plugins/google-ads-api-developer-assistant" ]]; then
  PROJECT_DIR_ABS="${candidate}"
fi
if [[ -z "${PROJECT_DIR_ABS}" ]]; then
  for repo_root_file in \
    "${SCRIPT_DIR}/config/.repo_root" \
    "${AGY_PLUGIN_TARGET_DIR}/config/.repo_root" \
    "${CLAUDE_PLUGIN_TARGET_DIR}/config/.repo_root"; do
    if [[ -f "${repo_root_file}" ]]; then
      saved_root=$(head -n 1 "${repo_root_file}" 2>/dev/null | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' || true)
      if [[ -n "${saved_root}" && -d "${saved_root}/plugins/google-ads-api-developer-assistant" ]]; then
        PROJECT_DIR_ABS="${saved_root}"
        break
      fi
    fi
  done
fi
if [[ -z "${PROJECT_DIR_ABS}" ]]; then
  if candidate=$(git rev-parse --show-toplevel 2>/dev/null) && [[ -d "${candidate}/plugins/google-ads-api-developer-assistant" ]]; then
    PROJECT_DIR_ABS="${candidate}"
  else
    err "ERROR: Could not locate the google-ads-api-developer-assistant git repository."
    exit 1
  fi
fi
readonly PROJECT_DIR_ABS
echo "Detected project root: ${PROJECT_DIR_ABS}"

# --- Update Assistant Repo ---
echo "Updating google-ads-api-developer-assistant..."

PLUGIN_SOURCE_DIR="${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant"
TEMP_CONFIG_DIR=$(mktemp -d)
cleanup() {
  rm -rf "${TEMP_CONFIG_DIR}"
}
trap cleanup EXIT

# If git-tracked config files in the repository checkout have local modifications,
# back them up (for migrating overrides to installed targets) and reset them so git pull
# never fails with merge conflicts and the repo's tracked config/ stays clean at upstream HEAD.
for tracked_rel in \
  "plugins/google-ads-api-developer-assistant/config/assistant_config" \
  "plugins/google-ads-api-developer-assistant/config/financial_limits"; do
  tracked_base=$(basename "${tracked_rel}")
  if git -C "${PROJECT_DIR_ABS}" ls-files --error-unmatch "${tracked_rel}" >/dev/null 2>&1; then
    if ! git -C "${PROJECT_DIR_ABS}" diff --quiet -- "${tracked_rel}" 2>/dev/null; then
      cp "${PROJECT_DIR_ABS}/${tracked_rel}" "${TEMP_CONFIG_DIR}/repo_${tracked_base}"
      git -C "${PROJECT_DIR_ABS}" checkout -- "${tracked_rel}" >/dev/null 2>&1 || true
    fi
  fi
done

for legacy_name in customer_id customer_id.txt; do
  if [[ -f "${PLUGIN_SOURCE_DIR}/config/${legacy_name}" ]]; then
    cp "${PLUGIN_SOURCE_DIR}/config/${legacy_name}" "${TEMP_CONFIG_DIR}/legacy_${legacy_name}"
  fi
done

if ! git -C "${PROJECT_DIR_ABS}" -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull; then
  err "ERROR: Failed to update google-ads-api-developer-assistant repository."
  exit 1
fi

echo "Successfully updated repository."

# --- Update Plugin Installation & Client Libraries ---
mkdir -p "${PLUGIN_SOURCE_DIR}/client_libs"

# Handle specific library additions in repository plugin source
for lang in python php ruby java dotnet; do
  if is_enabled "$lang"; then
    repo_url=$(get_repo_url "$lang")
    repo_name=$(get_repo_name "$lang")
    source_lib_path="${PLUGIN_SOURCE_DIR}/client_libs/${repo_name}"

    if [[ ! -d "${source_lib_path}" ]]; then
      echo "Library ${repo_name} not found in repository client_libs. Cloning into ${source_lib_path}..."
      if ! git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false clone --depth 1 "${repo_url}" "${source_lib_path}"; then
        err "ERROR: Failed to clone ${repo_url}"
        exit 1
      fi
      rm -f "${source_lib_path}/google-ads.yaml"
    fi
  fi
done

# Locate and update all client libraries in repository
echo "Locating client libraries to update..."
if [[ -d "${PLUGIN_SOURCE_DIR}/client_libs" ]]; then
  for dir in "${PLUGIN_SOURCE_DIR}/client_libs"/*; do
    if [[ -d "${dir}/.git" ]]; then
      echo "Updating repository at: ${dir}..."
      if ! update_git_repo "${dir}"; then
        echo "WARN: Failed to update $(basename "${dir}"). Continuing..." >&2
      else
        echo "Successfully updated $(basename "${dir}")."
      fi
      rm -f "${dir}/google-ads.yaml"
    fi
  done
fi

sync_installed_plugin_dir() {
  local target_plugin_dir="$1"
  local platform_label="$2"
  local was_disabled="false"

  if [[ -L "${target_plugin_dir}" ]]; then
    echo "Replacing legacy symlink at ${target_plugin_dir} with standalone plugin copy..."
    rm -f "${target_plugin_dir}"
  fi

  if [[ -d "${target_plugin_dir}" ]]; then
    if [[ -f "${target_plugin_dir}/plugin.json.disabled" && ! -f "${target_plugin_dir}/plugin.json" ]]; then
      was_disabled="true"
    elif [[ -f "${target_plugin_dir}/config/assistant_config" ]]; then
      local prior_en=""
      prior_en=$(grep -E '^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=' "${target_plugin_dir}/config/assistant_config" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=[[:space:]]*["'\'']?(true|false|TRUE|FALSE)["'\'']?.*$/\2/' | tr '[:upper:]' '[:lower:]' || true)
      if [[ "${prior_en}" == "false" ]]; then
        was_disabled="true"
      fi
    fi
  fi

  if [[ ! -d "${target_plugin_dir}" ]]; then
    echo "Plugin not yet installed at ${target_plugin_dir}. Installing standalone copy for ${platform_label}..."
    mkdir -p "$(dirname "${target_plugin_dir}")"
    safe_copy_dir "${PLUGIN_SOURCE_DIR}" "${target_plugin_dir}"
    rm -rf "${target_plugin_dir}/saved"
    mkdir -p "${target_plugin_dir}/config"
    rm -f \
      "${target_plugin_dir}/config/google-ads.yaml" \
      "${target_plugin_dir}/config/.repo_root" \
      "${target_plugin_dir}/config/google_ads_php.ini" \
      "${target_plugin_dir}/config/google_ads_config.rb" \
      "${target_plugin_dir}/config/ads.properties" \
      "${target_plugin_dir}/config/App.config" \
      "${target_plugin_dir}/config/appsettings.json"
    if [[ -f "${TEMP_CONFIG_DIR}/repo_assistant_config" ]]; then
      cp "${TEMP_CONFIG_DIR}/repo_assistant_config" "${target_plugin_dir}/config/assistant_config"
    fi
    if [[ -f "${TEMP_CONFIG_DIR}/repo_financial_limits" ]]; then
      merge_financial_limits "${target_plugin_dir}/config/financial_limits" "${TEMP_CONFIG_DIR}/repo_financial_limits"
    fi
  else
    echo "Syncing plugin files to ${target_plugin_dir}..."
    local existing_cfg_backup="${TEMP_CONFIG_DIR}/target_assistant_config"
    local existing_fin_backup="${TEMP_CONFIG_DIR}/target_financial_limits"
    local existing_yaml_backup="${TEMP_CONFIG_DIR}/target_google_ads_yaml"
    local existing_saved_backup="${TEMP_CONFIG_DIR}/target_saved"
    rm -f "${existing_cfg_backup}" "${existing_fin_backup}" "${existing_yaml_backup}"
    rm -rf "${existing_saved_backup}"

    if [[ -f "${target_plugin_dir}/config/assistant_config" ]]; then
      cp "${target_plugin_dir}/config/assistant_config" "${existing_cfg_backup}"
    fi
    if [[ -f "${target_plugin_dir}/config/financial_limits" ]]; then
      cp "${target_plugin_dir}/config/financial_limits" "${existing_fin_backup}"
    fi
    if [[ -f "${target_plugin_dir}/config/google-ads.yaml" ]]; then
      cp "${target_plugin_dir}/config/google-ads.yaml" "${existing_yaml_backup}"
    fi
    if [[ -d "${target_plugin_dir}/saved" ]]; then
      safe_copy_dir "${target_plugin_dir}/saved" "${existing_saved_backup}"
    fi

    for item in "${PLUGIN_SOURCE_DIR}"/*; do
      if [[ -e "${item}" ]]; then
        local item_name
        item_name=$(basename "${item}")
        if [[ "${item_name}" != "client_libs" && "${item_name}" != "saved" ]]; then
          cp -r "${item}" "${target_plugin_dir}/"
        fi
      fi
    done

    mkdir -p "${target_plugin_dir}/config"
    rm -f \
      "${target_plugin_dir}/config/google-ads.yaml" \
      "${target_plugin_dir}/config/.repo_root" \
      "${target_plugin_dir}/config/google_ads_php.ini" \
      "${target_plugin_dir}/config/google_ads_config.rb" \
      "${target_plugin_dir}/config/ads.properties" \
      "${target_plugin_dir}/config/App.config" \
      "${target_plugin_dir}/config/appsettings.json"

    if [[ -f "${existing_cfg_backup}" ]]; then
      cp "${existing_cfg_backup}" "${target_plugin_dir}/config/assistant_config"
    elif [[ -f "${TEMP_CONFIG_DIR}/repo_assistant_config" ]]; then
      cp "${TEMP_CONFIG_DIR}/repo_assistant_config" "${target_plugin_dir}/config/assistant_config"
    fi

    if [[ -f "${TEMP_CONFIG_DIR}/repo_financial_limits" ]]; then
      merge_financial_limits "${target_plugin_dir}/config/financial_limits" "${TEMP_CONFIG_DIR}/repo_financial_limits"
    fi
    if [[ -f "${existing_fin_backup}" ]]; then
      merge_financial_limits "${target_plugin_dir}/config/financial_limits" "${existing_fin_backup}"
    fi

    if [[ -f "${existing_yaml_backup}" ]]; then
      cp "${existing_yaml_backup}" "${target_plugin_dir}/config/google-ads.yaml"
      chmod 600 "${target_plugin_dir}/config/google-ads.yaml" 2>/dev/null || true
    fi

    if [[ -d "${existing_saved_backup}" && ! -d "${target_plugin_dir}/saved" ]]; then
      safe_copy_dir "${existing_saved_backup}" "${target_plugin_dir}/saved"
    fi
  fi

  for helper_script in plugin.sh update.sh set_financial_limits.py; do
    if [[ -f "${PROJECT_DIR_ABS}/${helper_script}" ]]; then
      rm -f "${target_plugin_dir}/${helper_script}"
      cp "${PROJECT_DIR_ABS}/${helper_script}" "${target_plugin_dir}/${helper_script}"
      chmod +x "${target_plugin_dir}/${helper_script}" 2>/dev/null || true
    fi
  done
  mkdir -p "${target_plugin_dir}/config"
  local repo_root_for_file
  repo_root_for_file="$(cd "${PROJECT_DIR_ABS}" && (pwd -W 2>/dev/null || pwd))"
  echo "${repo_root_for_file}" > "${target_plugin_dir}/config/.repo_root"

  local target_client_libs="${target_plugin_dir}/client_libs"
  mkdir -p "${target_client_libs}"

  if [[ -d "${PLUGIN_SOURCE_DIR}/client_libs" ]]; then
    for lib_dir in "${PLUGIN_SOURCE_DIR}/client_libs"/*; do
      if [[ -d "${lib_dir}" ]]; then
        local lib_name
        lib_name=$(basename "${lib_dir}")
        local target_lib_path="${target_client_libs}/${lib_name}"
        if [[ ! -d "${target_lib_path}" ]]; then
          echo "Copying ${lib_name} to ${target_lib_path}..."
          safe_copy_dir "${lib_dir}" "${target_lib_path}"
          rm -f "${target_lib_path}/google-ads.yaml"
        fi
      fi
    done
  fi

  if [[ -d "${target_client_libs}" ]]; then
    for dir in "${target_client_libs}"/*; do
      if [[ -d "${dir}/.git" ]]; then
        local repo_name
        repo_name=$(basename "${dir}")
        echo "Updating repository at: ${dir}..."
        if ! update_git_repo "${dir}"; then
          echo "WARN: Failed to update ${repo_name} in target directory. Continuing..." >&2
        else
          echo "Successfully updated ${repo_name}."
        fi
        rm -f "${dir}/google-ads.yaml"
      fi
    done
  fi

  detect_and_seed_api_version "${target_plugin_dir}/client_libs/google-ads-python/google/ads/googleads" "${target_plugin_dir}/config"

  if [[ "${PLUGIN_ENABLED_OPT}" == "false" ]] || [[ -z "${PLUGIN_ENABLED_OPT}" && "${was_disabled}" == "true" ]]; then
    "${PROJECT_DIR_ABS}/plugin.sh" disable --config-dir "${target_plugin_dir}/config" --quiet
  elif [[ "${PLUGIN_ENABLED_OPT}" == "true" ]]; then
    "${PROJECT_DIR_ABS}/plugin.sh" enable --config-dir "${target_plugin_dir}/config" --quiet
  fi

  for perm_file in "google-ads.yaml" "assistant_config" "financial_limits"; do
    if [[ -f "${target_plugin_dir}/config/${perm_file}" ]]; then
      chmod 600 "${target_plugin_dir}/config/${perm_file}" 2>/dev/null || true
    fi
  done
}

if [[ "${TYPE}" == "agy" ]]; then
  sync_installed_plugin_dir "${AGY_PLUGIN_TARGET_DIR}" "agy"
elif [[ "${TYPE}" == "claude" ]]; then
  mkdir -p "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin"
  cp "${PROJECT_DIR_ABS}/.claude-plugin/marketplace.json" "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin/marketplace.json"
  sync_installed_plugin_dir "${CLAUDE_PLUGIN_TARGET_DIR}" "claude"
  if command -v claude &>/dev/null; then
    claude plugin update google-ads-api-developer-assistant@google-ads-assistant-local >/dev/null 2>&1 \
      || claude plugin install google-ads-api-developer-assistant@google-ads-assistant-local >/dev/null 2>&1 \
      || true
  fi
fi

echo "Plugin update for ${TYPE} complete."
echo ""
if [[ "${TYPE}" == "agy" ]]; then
  echo "Restart your Antigravity / agy host to apply changes."
else
  echo "In your Claude Code session, run /reload-plugins to apply changes."
fi
