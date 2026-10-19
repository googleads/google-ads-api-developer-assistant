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
  echo "    --all                      Ensure all client libraries are present and updated in plugin"
  echo "    --python                   Ensure google-ads-python is present and updated in plugin"
  echo "    --php                      Ensure google-ads-php is present and updated in plugin"
  echo "    --ruby                     Ensure google-ads-ruby is present and updated in plugin"
  echo "    --java                     Ensure google-ads-java is present and updated in plugin"
  echo "    --dotnet                   Ensure google-ads-dotnet is present and updated in plugin"
  echo ""
  echo "  Examples:"
  echo "    $0 agy                     (Updates repository, Antigravity plugin, and client libraries)"
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
    agy|claude|claudecode)
      TYPE="$1"
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
    git pull
  )
}

# Helper to detect latest API version from client_libs and pre-seed config/assistant_config
detect_and_seed_api_version() {
  local search_dir="$1"
  local target_config_dir="$2"
  
  if [[ -d "${search_dir}" ]]; then
    local latest_v=""
    latest_v=$(find "${search_dir}" -mindepth 1 -maxdepth 1 -type d -name 'v*' 2>/dev/null | sed 's/.*\/v//' | grep -E '^[0-9]+$' | sort -n | tail -n 1)
    if [[ -n "${latest_v}" ]]; then
      mkdir -p "${target_config_dir}"
      local cfg_file="${target_config_dir}/assistant_config"
      local cid="12345678"
      local exec_mutates="false"
      if [[ -f "${cfg_file}" ]]; then
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
      fi
      if [[ "${cid}" == "12345678" ]]; then
        for legacy_file in "${target_config_dir}/customer_id" "${target_config_dir}/customer_id.txt" "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant/config/customer_id" "${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant/config/customer_id.txt"; do
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
api_version = "v${latest_v}"
customer_id = "${cid}"
execute_mutates = ${exec_mutates}
EOF
      echo "Configured API version v${latest_v} in ${cfg_file}"
    fi
  fi
}

# --- Dependency Check ---
if ! command -v git &> /dev/null; then
  err "ERROR: git is not installed. Please install it to continue."
  exit 1
fi

# --- Project Directory Resolution ---
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  err "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
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

# Backup config/assistant_config and legacy customer_id files if they exist
for cfg_file in assistant_config customer_id customer_id.txt; do
  if [[ -f "${PLUGIN_SOURCE_DIR}/config/${cfg_file}" ]]; then
    cp "${PLUGIN_SOURCE_DIR}/config/${cfg_file}" "${TEMP_CONFIG_DIR}/${cfg_file}"
  fi
done

if ! git pull; then
  err "ERROR: Failed to update google-ads-api-developer-assistant repository."
  # Restore config files if backup exists
  for cfg_file in assistant_config customer_id customer_id.txt; do
    if [[ -f "${TEMP_CONFIG_DIR}/${cfg_file}" ]]; then
      cp "${TEMP_CONFIG_DIR}/${cfg_file}" "${PLUGIN_SOURCE_DIR}/config/${cfg_file}"
    fi
  done
  exit 1
fi

# Restore config files
for cfg_file in assistant_config customer_id customer_id.txt; do
  if [[ -f "${TEMP_CONFIG_DIR}/${cfg_file}" ]]; then
    cp "${TEMP_CONFIG_DIR}/${cfg_file}" "${PLUGIN_SOURCE_DIR}/config/${cfg_file}"
  fi
done

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
      if ! git clone "${repo_url}" "${source_lib_path}"; then
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

# Pre-seed latest API version in repository plugin config
detect_and_seed_api_version "${PLUGIN_SOURCE_DIR}/client_libs/google-ads-python/google/ads/googleads" "${PLUGIN_SOURCE_DIR}/config"

sync_installed_plugin_dir() {
  local target_plugin_dir="$1"
  local platform_label="$2"

  if [[ -L "${target_plugin_dir}" ]]; then
    echo "Replacing legacy symlink at ${target_plugin_dir} with standalone plugin copy..."
    rm -f "${target_plugin_dir}"
  fi

  if [[ ! -d "${target_plugin_dir}" ]]; then
    echo "Plugin not yet installed at ${target_plugin_dir}. Installing standalone copy for ${platform_label}..."
    mkdir -p "$(dirname "${target_plugin_dir}")"
    cp -r "${PLUGIN_SOURCE_DIR}" "${target_plugin_dir}"
  else
    echo "Syncing plugin files to ${target_plugin_dir}..."
    local existing_cfg_backup="${TEMP_CONFIG_DIR}/target_assistant_config"
    if [[ -f "${target_plugin_dir}/config/assistant_config" ]]; then
      cp "${target_plugin_dir}/config/assistant_config" "${existing_cfg_backup}"
    fi
    for item in "${PLUGIN_SOURCE_DIR}"/*; do
      if [[ -e "${item}" ]]; then
        local item_name
        item_name=$(basename "${item}")
        if [[ "${item_name}" != "client_libs" ]]; then
          cp -r "${item}" "${target_plugin_dir}/"
        fi
      fi
    done
    if [[ -f "${existing_cfg_backup}" ]]; then
      cp "${existing_cfg_backup}" "${target_plugin_dir}/config/assistant_config"
    fi
  fi

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
          cp -r "${lib_dir}" "${target_lib_path}"
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
}

if [[ "${TYPE}" == "agy" ]]; then
  sync_installed_plugin_dir "${AGY_PLUGIN_TARGET_DIR}" "agy"
elif [[ "${TYPE}" == "claude" ]]; then
  mkdir -p "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin"
  cp "${PROJECT_DIR_ABS}/.claude-plugin/marketplace.json" "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin/marketplace.json"
  sync_installed_plugin_dir "${CLAUDE_PLUGIN_TARGET_DIR}" "claude"
fi

echo "Plugin update for ${TYPE} complete."
echo ""
if [[ "${TYPE}" == "agy" ]]; then
  echo "Restart your Antigravity / agy host to apply changes."
else
  echo "In your Claude Code session, run /reload-plugins to apply changes."
fi
