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

# --- Help Function ---
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "  Updates the Google Ads API Developer Assistant plugin and configured client libraries."
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --python                   Ensure google-ads-python is present and updated in plugin"
  echo "    --php                      Ensure google-ads-php is present and updated in plugin"
  echo "    --ruby                     Ensure google-ads-ruby is present and updated in plugin"
  echo "    --java                     Ensure google-ads-java is present and updated in plugin"
  echo "    --dotnet                   Ensure google-ads-dotnet is present and updated in plugin"
  echo ""
  echo "  Examples:"
  echo "    $0                         (Updates repository, plugin, and all configured client libraries)"
  echo "    $0 --java                  (Ensures Java library is added/updated in the plugin)"
  echo ""
}

# --- Defaults ---
INSTALL_PYTHON=false
INSTALL_PHP=false
INSTALL_RUBY=false
INSTALL_JAVA=false
INSTALL_DOTNET=false
ANY_SELECTED=false

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
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

CUSTOMER_ID_FILE="${PROJECT_DIR_ABS}/config/customer_id.txt"
TEMP_CUSTOMER_ID=$(mktemp)

# Backup config/customer_id.txt if it exists
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

# Restore config/customer_id.txt
if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
    mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    rm -f "${TEMP_CUSTOMER_ID}"
fi

echo "Successfully updated repository."

# --- Update Plugin Installation ---
PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
PLUGIN_SOURCE_DIR="${PROJECT_DIR_ABS}/plugins/agy"

if [[ ! -d "${PLUGIN_TARGET_DIR}" ]]; then
  echo "Plugin not yet installed at ${PLUGIN_TARGET_DIR}. Installing..."
  mkdir -p "${HOME}/.gemini/config/plugins"
  cp -r "${PLUGIN_SOURCE_DIR}" "${PLUGIN_TARGET_DIR}"
else
  echo "Syncing plugin files to ${PLUGIN_TARGET_DIR}..."
  for item in rules sidecars skills config plugin.json README.md; do
    if [[ -e "${PLUGIN_SOURCE_DIR}/${item}" ]]; then
      cp -r "${PLUGIN_SOURCE_DIR}/${item}" "${PLUGIN_TARGET_DIR}/"
    fi
  done
fi

PLUGIN_CLIENT_LIBS="${PLUGIN_TARGET_DIR}/client_libs"
mkdir -p "${PLUGIN_CLIENT_LIBS}"

# Handle specific library additions if requested
for lang in python php ruby java dotnet; do
  if is_enabled "$lang"; then
    repo_url=$(get_repo_url "$lang")
    repo_name=$(get_repo_name "$lang")
    lib_path="${PLUGIN_CLIENT_LIBS}/${repo_name}"

    if [[ ! -d "${lib_path}" ]]; then
      echo "Library ${repo_name} not found in plugin. Cloning into ${lib_path}..."
      if ! git clone "${repo_url}" "${lib_path}"; then
        err "ERROR: Failed to clone ${repo_url}"
        exit 1
      fi
    fi
  fi
done

# Locate and update all client libraries in the plugin structure
echo "Locating client libraries in ${PLUGIN_CLIENT_LIBS}..."
INCLUDE_DIRS=()
if [[ -d "${PLUGIN_CLIENT_LIBS}" ]]; then
  for dir in "${PLUGIN_CLIENT_LIBS}"/*; do
    if [[ -d "${dir}/.git" ]]; then
      INCLUDE_DIRS+=("${dir}")
    fi
  done
fi

if [[ ${#INCLUDE_DIRS[@]} -eq 0 ]]; then
  echo "No git client libraries found to update in ${PLUGIN_CLIENT_LIBS}."
else
  echo "Found ${#INCLUDE_DIRS[@]} client libraries to update."
  for lib_path in "${INCLUDE_DIRS[@]}"; do
    [[ -z "${lib_path}" ]] && continue
    if [[ ! -d "${lib_path}" ]]; then
      echo "WARN: Directory not found: ${lib_path}. Skipping."
      continue
    fi

    echo "Updating repository at: ${lib_path}..."
    if ! (cd "${lib_path}" && git pull); then
      err "ERROR: Failed to update ${lib_path}"
      exit 1
    fi
    echo "Successfully updated ${lib_path}."
  done
fi

# Pre-seed latest API version in plugin and project config
detect_and_seed_api_version "${PLUGIN_CLIENT_LIBS}/google-ads-python/google/ads/googleads" "${PLUGIN_TARGET_DIR}/config"
detect_and_seed_api_version "${PLUGIN_CLIENT_LIBS}/google-ads-python/google/ads/googleads" "${PROJECT_DIR_ABS}/config"

echo "Plugin update complete."
echo ""
echo "Restart your Antigravity / agy host to apply changes."
