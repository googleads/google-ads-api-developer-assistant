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
#   This script initializes the development environment for the Google Ads API Developer Assistant.
#   It performs the following steps:
#   1. Verifies that required tools (jq, git) are installed.
#   2. Clones or updates the 'google-ads-python' repository into a specified directory.

# Exit on any error, and on undefined variables.
set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

# --- Project Directory Resolution ---
# Determine the root directory of the google-ads-api-developer-assistant git repository.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if PROJECT_DIR_ABS=$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null) && [[ -d "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant" ]]; then
  :
elif ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null) || [[ ! -d "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant" ]]; then
  err "ERROR: Could not locate the google-ads-api-developer-assistant git repository."
  exit 1
fi
readonly PROJECT_DIR_ABS
echo "Detected project root: ${PROJECT_DIR_ABS}"

# --- Configuration ---
readonly PLUGIN_SOURCE_DIR="${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant"
readonly ALL_LANGS="python php ruby java dotnet"

# Helper functions for repo info (Replacing associative arrays for Bash 3.2 compatibility)
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

readonly PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
readonly CLAUDE_MARKETPLACE_DIR="${HOME}/.claude/plugins/google-ads-assistant-local"
readonly CLAUDE_PLUGIN_TARGET_DIR="${CLAUDE_MARKETPLACE_DIR}/plugins/google-ads-api-developer-assistant"

# --- Defaults ---
TYPE=""
INSTALL_PYTHON=true
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
  echo "  Installs the Google Ads API Developer Assistant as a plugin for Antigravity or Claude Code."
  echo ""
  echo "  Required Argument:"
  echo "    <agy|claude>               Target platform: 'agy' (Antigravity) or 'claude' (Claude Code)"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --type TYPE                Target platform ('agy' or 'claude')"
  echo "    --agy                      Install for Antigravity (shorthand for --type agy)"
  echo "    --claude                   Install for Claude Code (shorthand for --type claude)"
  echo "    --cid, --customer-id CID   Default Google Ads Customer ID (e.g. 1234567890)"
  echo "    --enable                   Ensure the plugin is enabled after installation (default)"
  echo "    --disable, --disabled      Install the plugin in disabled state so it is not invoked on startup"
  echo "    --status                   Show the current enabled/disabled status of the plugin and exit"
  echo "    --all                      Include all client libraries (Python, PHP, Ruby, Java, .NET)"
  echo "    --python                   Include google-ads-python client library (included by default)"
  echo "    --php                      Include google-ads-php client library"
  echo "    --ruby                     Include google-ads-ruby client library"
  echo "    --java                     Include google-ads-java client library"
  echo "    --dotnet                   Include google-ads-dotnet client library"
  echo ""
  echo "  By default, the Python client library is included in the plugin."
  echo ""
  echo "  Examples:"
  echo "    $0 agy                     (Installs Antigravity plugin with Python client library)"
  echo "    $0 agy --disable           (Installs Antigravity plugin in disabled state)"
  echo "    $0 claude                  (Installs Claude Code plugin via claude CLI)"
  echo "    $0 agy --java              (Installs Antigravity plugin with Java and Python client libraries)"
  echo "    $0 claude --php --dotnet   (Installs Claude Code plugin with PHP, .NET, and Python client libraries)"
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
    --link|--symlink)
      err "ERROR: --link is not supported. Antigravity plugin is always installed as a standalone copy."
      exit 1
      ;;
    *)
      err "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ "${STATUS_ONLY}" == "true" ]]; then
  exec "${PROJECT_DIR_ABS}/plugin.sh" status "${TYPE:-all}"
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

# --- Environment Verification ---
check_python() {
  local py_cmd=""
  for cmd in python3 python; do
    if command -v "${cmd}" &>/dev/null; then
      if "${cmd}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' &>/dev/null; then
        py_cmd="${cmd}"
        break
      fi
    fi
  done

  if [[ -n "${py_cmd}" ]]; then
    local py_ver
    py_ver=$("${py_cmd}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)
    echo "Found Python ${py_ver} (${py_cmd})"
    return 0
  fi

  local found_ver=""
  for cmd in python3 python; do
    if command -v "${cmd}" &>/dev/null; then
      found_ver=$("${cmd}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)
      if [[ -n "${found_ver}" ]]; then
        found_ver="${cmd} (${found_ver})"
        break
      fi
    fi
  done

  err "ERROR: Python 3.11 or higher is required."
  if [[ -n "${found_ver}" ]]; then
    err "Incompatible Python version detected: ${found_ver}."
  else
    err "No Python interpreter was found on PATH."
  fi
  err "Please install Python 3.11 or later and ensure it is available in your PATH."
  err "See: https://www.python.org/downloads/"
  return 1
}

check_antigravity() {
  local found_antigravity=false
  local antigravity_detail=""

  if command -v agy &>/dev/null; then
    found_antigravity=true
    antigravity_detail="Antigravity CLI (agy) found at $(command -v agy)"
  elif command -v antigravity &>/dev/null; then
    found_antigravity=true
    antigravity_detail="Antigravity CLI (antigravity) found at $(command -v antigravity)"
  fi

  if [[ "${found_antigravity}" == "false" ]]; then
    if [[ -n "${ANTIGRAVITY_APP_DIR:-}" || -n "${ANTIGRAVITY_LS_ADDRESS:-}" || -n "${ANTIGRAVITY_PORT:-}" || -n "${JETSKI_HOME:-}" || -n "${GEMINI_HOME:-}" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity environment detected via environment variables"
    elif [[ -d "${HOME}/.gemini" || -d "${HOME}/.antigravity" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity configuration/installation found in home directory (~/.gemini or ~/.antigravity)"
    elif [[ -d "/Applications/Antigravity.app" || -d "${HOME}/Applications/Antigravity.app" || -d "/Applications/Google Antigravity.app" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity Desktop application found on macOS"
    elif [[ -d "/opt/Antigravity" || -d "/usr/share/antigravity" || -d "/usr/local/share/antigravity" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity Desktop installation found on Linux"
    fi
  fi

  if [[ "${found_antigravity}" == "true" ]]; then
    echo "Found Antigravity: ${antigravity_detail}"
    return 0
  fi

  err "ERROR: Antigravity CLI or Antigravity Desktop/Web is not installed."
  err "The Google Ads API Developer Assistant requires an active Antigravity environment."
  err "Please install Antigravity CLI ('agy' or 'antigravity') or Antigravity Desktop/Web to continue."
  return 1
}

check_claudecode() {
  local found_claude=false
  local claude_detail=""

  if command -v claude &>/dev/null; then
    found_claude=true
    claude_detail="Claude Code CLI (claude) found at $(command -v claude)"
  fi

  if [[ "${found_claude}" == "true" ]]; then
    echo "Found Claude Code: ${claude_detail}"
    return 0
  fi

  err "ERROR: Claude Code CLI ('claude') is not installed or not in PATH."
  err "Please install Claude Code CLI to continue."
  return 1
}

check_environment() {
  echo "Checking environment for ${TYPE}..."
  local env_ok=true

  if ! check_python; then
    env_ok=false
  fi

  if [[ "${TYPE}" == "agy" ]]; then
    if ! check_antigravity; then
      env_ok=false
    fi
  elif [[ "${TYPE}" == "claude" ]]; then
    if ! check_claudecode; then
      env_ok=false
    fi
  fi

  if [[ "${env_ok}" != "true" ]]; then
    err "ERROR: Environment check failed. Aborting installation."
    exit 1
  fi
  echo "Environment check passed."
}

# Run environment verification before proceeding with installation
check_environment

# Helper to check if a language is enabled
is_enabled() {
  case "$1" in
    python) [[ "${INSTALL_PYTHON}" == "true" ]] ;;
    php)    [[ "${INSTALL_PHP}" == "true" ]] ;;
    ruby)   [[ "${INSTALL_RUBY}" == "true" ]] ;;
    java)   [[ "${INSTALL_JAVA}" == "true" ]] ;;
    dotnet) [[ "${INSTALL_DOTNET}" == "true" ]] ;;
    *)      return 1 ;;
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
    git -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false pull
  )
}

# --- Clone/Update Repositories ---
clone_or_update() {
  local repo_url="$1"
  local clone_path="$2"
  local log_file="$3"
  local repo_name
  local clone_failed=false

  repo_name=$(basename "${clone_path}")

  {
    echo "Managing repository ${repo_name} in ${clone_path}"
    if [[ -d "${clone_path}/.git" ]]; then
      echo "Directory ${clone_path} already exists. Updating..."
      if ! update_git_repo "${clone_path}"; then
        echo "WARN: Failed to update ${repo_name}. Continuing..."
      else
        echo "Successfully updated ${repo_name}."
      fi
    elif [[ -d "${clone_path}" ]]; then
       echo "WARN: Directory ${clone_path} exists but is not a git repo. Skipping."
    else
      echo "Cloning ${repo_url} into ${clone_path}"
      if ! git -c core.longpaths=true -c maintenance.auto=false -c gc.auto=0 -c gc.autoDetach=false clone --depth 1 "${repo_url}" "${clone_path}"; then
        clone_failed=true
      else
        echo "Successfully cloned ${repo_name}."
      fi
    fi
  } > "${log_file}" 2>&1

  if [[ "${clone_failed}" == "true" ]]; then
    if [[ -f "${log_file}" ]]; then
      cat "${log_file}" >&2
    fi
    err "ERROR: Failed to clone ${repo_url}"
    exit 1
  fi
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
      for legacy_file in "${target_config_dir}/customer_id" "${target_config_dir}/customer_id.txt" "${PLUGIN_SOURCE_DIR}/config/customer_id" "${PLUGIN_SOURCE_DIR}/config/customer_id.txt"; do
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

# --- Plugin Installation ---
if ! command -v git &> /dev/null; then
  err "ERROR: git is not installed. Please install it to continue."
  exit 1
fi

if [[ ! -d "${PLUGIN_SOURCE_DIR}" ]]; then
  err "ERROR: Plugin directory '${PLUGIN_SOURCE_DIR}' does not exist."
  exit 1
fi

TEMP_LOG_DIR=$(mktemp -d)
cleanup() {
  rm -rf "${TEMP_LOG_DIR}"
}
trap cleanup EXIT

install_plugin_copy() {
  local target_dir="$1"
  local backup_root="${TEMP_LOG_DIR}/target_backup"
  local backup_cfg_dir="${backup_root}/config"
  local backup_libs_dir="${backup_root}/client_libs"
  local backup_saved_dir="${backup_root}/saved"
  local was_disabled="false"

  rm -rf "${backup_root}"
  mkdir -p "${backup_cfg_dir}" "${backup_libs_dir}"

  if [[ -L "${target_dir}" ]]; then
    rm -f "${target_dir}"
  elif [[ -d "${target_dir}" ]]; then
    if [[ -f "${target_dir}/plugin.json.disabled" && ! -f "${target_dir}/plugin.json" ]]; then
      was_disabled="true"
    elif [[ -f "${target_dir}/config/assistant_config" ]]; then
      local prior_en=""
      prior_en=$(grep -E '^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=' "${target_dir}/config/assistant_config" 2>/dev/null | head -n 1 | sed -E 's/^[[:space:]]*(enabled|plugin_enabled)[[:space:]]*=[[:space:]]*["'\'']?(true|false|TRUE|FALSE)["'\'']?.*$/\2/' | tr '[:upper:]' '[:lower:]' || true)
      if [[ "${prior_en}" == "false" ]]; then
        was_disabled="true"
      fi
    fi

    for cfg_name in assistant_config financial_limits google-ads.yaml customer_id customer_id.txt; do
      if [[ -f "${target_dir}/config/${cfg_name}" ]]; then
        cp "${target_dir}/config/${cfg_name}" "${backup_cfg_dir}/${cfg_name}"
      fi
    done

    if [[ -d "${target_dir}/saved" ]]; then
      mv "${target_dir}/saved" "${backup_saved_dir}" 2>/dev/null || safe_copy_dir "${target_dir}/saved" "${backup_saved_dir}"
    fi

    if [[ -d "${target_dir}/client_libs" ]]; then
      for existing_lib in "${target_dir}/client_libs"/google-ads-*; do
        if [[ -d "${existing_lib}" ]]; then
          local existing_lib_name
          existing_lib_name=$(basename "${existing_lib}")
          mv "${existing_lib}" "${backup_libs_dir}/${existing_lib_name}" 2>/dev/null || safe_copy_dir "${existing_lib}" "${backup_libs_dir}/${existing_lib_name}"
        fi
      done
    fi

    rm -rf "${target_dir}"
  fi

  mkdir -p "$(dirname "${target_dir}")"
  safe_copy_dir "${PLUGIN_SOURCE_DIR}" "${target_dir}"

  # Exclude gitignored repo credentials and saved artifacts from copied plugin source
  mkdir -p "${target_dir}/config"
  rm -f \
    "${target_dir}/config/google-ads.yaml" \
    "${target_dir}/config/.repo_root" \
    "${target_dir}/config/google_ads_php.ini" \
    "${target_dir}/config/google_ads_config.rb" \
    "${target_dir}/config/ads.properties" \
    "${target_dir}/config/App.config" \
    "${target_dir}/config/appsettings.json"
  rm -rf "${target_dir}/saved"

  # Restore backed-up config files, saved directory, and previously cloned client_libs
  for restore_cfg_name in assistant_config google-ads.yaml customer_id customer_id.txt; do
    if [[ -f "${backup_cfg_dir}/${restore_cfg_name}" ]]; then
      cp "${backup_cfg_dir}/${restore_cfg_name}" "${target_dir}/config/${restore_cfg_name}"
    fi
  done
  if [[ -f "${backup_cfg_dir}/financial_limits" ]]; then
    merge_financial_limits "${target_dir}/config/financial_limits" "${backup_cfg_dir}/financial_limits"
  fi
  if [[ -d "${backup_saved_dir}" ]]; then
    mv "${backup_saved_dir}" "${target_dir}/saved" 2>/dev/null || safe_copy_dir "${backup_saved_dir}" "${target_dir}/saved"
  fi

  for helper_script in plugin.sh update.sh set_financial_limits.py; do
    if [[ -f "${PROJECT_DIR_ABS}/${helper_script}" ]]; then
      cp "${PROJECT_DIR_ABS}/${helper_script}" "${target_dir}/${helper_script}"
      chmod +x "${target_dir}/${helper_script}" 2>/dev/null || true
    fi
  done
  local repo_root_for_file
  repo_root_for_file="$(cd "${PROJECT_DIR_ABS}" && (pwd -W 2>/dev/null || pwd))"
  echo "${repo_root_for_file}" > "${target_dir}/config/.repo_root"
  mkdir -p "${target_dir}/client_libs"

  for bak_lib in "${backup_libs_dir}"/google-ads-*; do
    if [[ -d "${bak_lib}" ]]; then
      local bak_lib_name
      bak_lib_name=$(basename "${bak_lib}")
      if [[ ! -d "${target_dir}/client_libs/${bak_lib_name}" ]]; then
        mv "${bak_lib}" "${target_dir}/client_libs/${bak_lib_name}" 2>/dev/null || safe_copy_dir "${bak_lib}" "${target_dir}/client_libs/${bak_lib_name}"
        rm -f "${target_dir}/client_libs/${bak_lib_name}/google-ads.yaml"
      fi
    fi
  done

  for lang in python php ruby java dotnet; do
    if is_enabled "$lang"; then
      local repo_name
      repo_name=$(get_repo_name "$lang")
      local target_lib_path="${target_dir}/client_libs/${repo_name}"
      local source_lib_path="${PLUGIN_SOURCE_DIR}/client_libs/${repo_name}"
      local url
      url=$(get_repo_url "$lang")
      local log_file="${TEMP_LOG_DIR}/install_${lang}.log"

      if [[ -d "${source_lib_path}" ]]; then
        echo "Adding ${repo_name} to plugin client_libs from local repository..."
        rm -rf "${target_lib_path}"
        safe_copy_dir "${source_lib_path}" "${target_lib_path}"
      else
        echo "Cloning ${repo_name} into plugin client_libs..."
        clone_or_update "$url" "${target_lib_path}" "${log_file}"
        if [[ -f "${log_file}" ]]; then
          cat "${log_file}"
        fi
      fi
      rm -f "${target_lib_path}/google-ads.yaml"
    fi
  done

  detect_and_seed_api_version "${target_dir}/client_libs/google-ads-python/google/ads/googleads" "${target_dir}/config"
  if [[ "${PLUGIN_ENABLED_OPT}" == "false" ]] || [[ -z "${PLUGIN_ENABLED_OPT}" && "${was_disabled}" == "true" ]]; then
    "${PROJECT_DIR_ABS}/plugin.sh" disable --config-dir "${target_dir}/config" --quiet
  else
    "${PROJECT_DIR_ABS}/plugin.sh" enable --config-dir "${target_dir}/config" --quiet
  fi

  for perm_file in "google-ads.yaml" "assistant_config" "financial_limits"; do
    if [[ -f "${target_dir}/config/${perm_file}" ]]; then
      chmod 600 "${target_dir}/config/${perm_file}" 2>/dev/null || true
    fi
  done
}

if [[ "${TYPE}" == "claude" ]]; then
  echo "Installing standalone Claude Code plugin into: ${CLAUDE_PLUGIN_TARGET_DIR}"
  mkdir -p "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin"
  cp "${PROJECT_DIR_ABS}/.claude-plugin/marketplace.json" "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin/marketplace.json"

  install_plugin_copy "${CLAUDE_PLUGIN_TARGET_DIR}"

  echo "Registering marketplace in Claude Code..."
  (
    cd "${CLAUDE_PLUGIN_TARGET_DIR}"
    claude plugin marketplace add "${CLAUDE_MARKETPLACE_DIR}"

    echo "Installing plugin in Claude Code..."
    claude plugin install google-ads-api-developer-assistant@google-ads-assistant-local
  )

  echo "Plugin installation for claude complete."
  echo "Active plugin location: ${CLAUDE_PLUGIN_TARGET_DIR}"
  echo ""
  echo "In your Claude Code session, run /reload-plugins to activate the plugin."
  exit 0
fi

# Antigravity installation
echo "Installing plugin for agy into: ${PLUGIN_TARGET_DIR}"
install_plugin_copy "${PLUGIN_TARGET_DIR}"

echo "Plugin installation for agy complete."
echo "Active plugin location: ${PLUGIN_TARGET_DIR}"
echo "Globally accessible across all workspaces on this host."
echo ""
echo "Restart your Antigravity / agy host to activate the plugin."
