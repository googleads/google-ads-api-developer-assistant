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

# Helper to detect latest API version from client_libs and pre-seed config/api_version.txt
detect_and_seed_api_version() {
  local search_dir="$1"
  local target_config_dir="$2"
  
  if [[ -d "${search_dir}" ]]; then
    local latest_v=""
    latest_v=$(find "${search_dir}" -mindepth 1 -maxdepth 1 -type d -name 'v*' 2>/dev/null | sed 's/.*\/v//' | grep -E '^[0-9]+$' | sort -n | tail -n 1)
    if [[ -n "${latest_v}" ]]; then
      mkdir -p "${target_config_dir}"
      echo "v${latest_v}" > "${target_config_dir}/api_version.txt"
      echo "Configured API version v${latest_v} in ${target_config_dir}/api_version.txt"
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

CUSTOMER_ID_FILE="${PROJECT_DIR_ABS}/config/customer_id"
TEMP_CUSTOMER_ID=$(mktemp)

# Backup config/customer_id if it exists
if [[ -f "${CUSTOMER_ID_FILE}" ]]; then
    cp "${CUSTOMER_ID_FILE}" "${TEMP_CUSTOMER_ID}"
fi

if ! git pull; then
    err "ERROR: Failed to update google-ads-api-developer-assistant repository."
    if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
         mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    fi
    exit 1
fi

# Restore config/customer_id
if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
    mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    rm -f "${TEMP_CUSTOMER_ID}"
fi

echo "Successfully updated repository."

# --- Update Plugin Installation & Client Libraries ---
PLUGIN_SOURCE_DIR="${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant"
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
    fi
  fi
done

# Locate and update all client libraries in repository
echo "Locating client libraries to update..."
if [[ -d "${PLUGIN_SOURCE_DIR}/client_libs" ]]; then
  for dir in "${PLUGIN_SOURCE_DIR}/client_libs"/*; do
    if [[ -d "${dir}/.git" ]]; then
      echo "Updating repository at: ${dir}..."
      if ! (cd "${dir}" && git pull); then
        err "ERROR: Failed to update ${dir}"
        exit 1
      fi
      echo "Successfully updated $(basename "${dir}")."
    fi
  done
fi

# Pre-seed latest API version in repository plugin and project config
detect_and_seed_api_version "${PLUGIN_SOURCE_DIR}/client_libs/google-ads-python/google/ads/googleads" "${PLUGIN_SOURCE_DIR}/config"
detect_and_seed_api_version "${PLUGIN_SOURCE_DIR}/client_libs/google-ads-python/google/ads/googleads" "${PROJECT_DIR_ABS}/config"

# --- Antigravity Specific Sync ---
if [[ "${TYPE}" == "agy" ]]; then
  if [[ ! -d "${AGY_PLUGIN_TARGET_DIR}" ]]; then
    echo "Plugin not yet installed at ${AGY_PLUGIN_TARGET_DIR}. Installing for agy..."
    mkdir -p "$(dirname "${AGY_PLUGIN_TARGET_DIR}")"
    cp -r "${PLUGIN_SOURCE_DIR}" "${AGY_PLUGIN_TARGET_DIR}"
  else
    echo "Syncing plugin files to ${AGY_PLUGIN_TARGET_DIR}..."
    for item in rules sidecars skills commands config plugin.json mcp_config.json README.md customer_id; do
      if [[ -e "${PLUGIN_SOURCE_DIR}/${item}" ]]; then
        cp -r "${PLUGIN_SOURCE_DIR}/${item}" "${AGY_PLUGIN_TARGET_DIR}/"
      fi
    done
  fi

  AGY_CLIENT_LIBS="${AGY_PLUGIN_TARGET_DIR}/client_libs"
  mkdir -p "${AGY_CLIENT_LIBS}"

  if [[ -d "${PLUGIN_SOURCE_DIR}/client_libs" ]]; then
    for lib_dir in "${PLUGIN_SOURCE_DIR}/client_libs"/*; do
      if [[ -d "${lib_dir}" ]]; then
        lib_name=$(basename "${lib_dir}")
        target_lib_path="${AGY_CLIENT_LIBS}/${lib_name}"
        if [[ ! -d "${target_lib_path}" ]]; then
          echo "Copying ${lib_name} to ${target_lib_path}..."
          cp -r "${lib_dir}" "${target_lib_path}"
        fi
      fi
    done
  fi

  # Also update any existing client libraries in Antigravity target directory if they are distinct git clones
  if [[ -d "${AGY_CLIENT_LIBS}" ]]; then
    for dir in "${AGY_CLIENT_LIBS}"/*; do
      if [[ -d "${dir}/.git" ]]; then
        repo_name=$(basename "${dir}")
        source_path="${PLUGIN_SOURCE_DIR}/client_libs/${repo_name}"
        if [[ ! -d "${source_path}" || "$(cd "${dir}" && pwd)" != "$(cd "${source_path}" 2>/dev/null && pwd)" ]]; then
          echo "Updating repository at: ${dir}..."
          if ! (cd "${dir}" && git pull); then
            err "ERROR: Failed to update ${dir}"
            exit 1
          fi
          echo "Successfully updated $(basename "${dir}")."
        fi
      fi
    done
  fi

  detect_and_seed_api_version "${PLUGIN_SOURCE_DIR}/client_libs/google-ads-python/google/ads/googleads" "${AGY_PLUGIN_TARGET_DIR}/config"
fi

echo "Plugin update for ${TYPE} complete."
echo ""
if [[ "${TYPE}" == "agy" ]]; then
  echo "Restart your Antigravity / agy host to apply changes."
else
  echo "In your Claude Code session, run /reload-plugins to apply changes."
fi
