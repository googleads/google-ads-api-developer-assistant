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
  echo "Usage: $0 --type <project|plugin> [OPTIONS]"
  echo "  Updates the Google Ads API Developer Assistant and configured client libraries."
  echo ""
  echo "  Required Arguments:"
  echo "    -t, --type TYPE            Update type: 'project' or 'plugin'"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --python                   Ensure google-ads-python is present and updated"
  echo "    --php                      Ensure google-ads-php is present and updated"
  echo "    --ruby                     Ensure google-ads-ruby is present and updated"
  echo "    --java                     Ensure google-ads-java is present and updated"
  echo "    --dotnet                   Ensure google-ads-dotnet is present and updated"
  echo "    --context_path PATH        Add the specified directory to the project configuration for context (project mode only)"
  echo ""
  echo "  Examples:"
  echo "    $0 --type project          (Updates project and cloned client libraries)"
  echo "    $0 --type plugin           (Updates all client libraries in the plugin structure)"
  echo "    $0 --type plugin --java    (Ensures Java library is present and updated in plugin)"
  echo ""
}

# --- Defaults ---
UPDATE_TYPE=""
INSTALL_PYTHON=false
INSTALL_PHP=false
INSTALL_RUBY=false
INSTALL_JAVA=false
INSTALL_DOTNET=false
ANY_SELECTED=false
CONTEXT_PATH=""

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    -t|--type)
      if [[ $# -lt 2 ]]; then
        err "ERROR: --type requires an argument ('project' or 'plugin')."
        usage
        exit 1
      fi
      UPDATE_TYPE=$(echo "$2" | tr '[:upper:]' '[:lower:]')
      shift 2
      ;;
    --type=*)
      UPDATE_TYPE=$(echo "${1#*=}" | tr '[:upper:]' '[:lower:]')
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
    --context_path)
      if [[ $# -lt 2 ]]; then
        err "ERROR: --context_path requires a value."
        exit 1
      fi
      CONTEXT_PATH="$2"
      shift 2
      ;;
    --context_path=*)
      CONTEXT_PATH="${1#*=}"
      shift
      ;;
    context_path=*)
      CONTEXT_PATH="${1#*=}"
      shift
      ;;
    *)
      err "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

# --- Validate Required Type Argument ---
if [[ -z "${UPDATE_TYPE}" ]]; then
  err "ERROR: Missing required argument: --type <project|plugin>"
  usage
  exit 1
fi

if [[ "${UPDATE_TYPE}" != "project" && "${UPDATE_TYPE}" != "plugin" ]]; then
  err "ERROR: Invalid update type '${UPDATE_TYPE}'. Must be 'project' or 'plugin'."
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

# --- Plugin Update Branch ---
if [[ "${UPDATE_TYPE}" == "plugin" ]]; then
  if ! command -v git &> /dev/null; then
    err "ERROR: git is not installed. Please install it to continue."
    exit 1
  fi

  PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google_ads_assistant_plugin"
  if [[ ! -d "${PLUGIN_TARGET_DIR}" ]]; then
    err "ERROR: Plugin directory '${PLUGIN_TARGET_DIR}' does not exist. Please run install.sh --type plugin first."
    exit 1
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

  # Pre-seed latest API version in plugin config
  detect_and_seed_api_version "${PLUGIN_CLIENT_LIBS}/google-ads-python/google/ads/googleads" "${PLUGIN_TARGET_DIR}/config"

  echo "Plugin update complete."
  exit 0
fi

# --- Dependency Check ---
if ! command -v jq &> /dev/null; then
  err "ERROR: jq is not installed. Please install it to continue."
  err "See: https://jqlang.github.io/jq/download/"
  exit 1
fi
if ! command -v git &> /dev/null; then
  err "ERROR: git is not installed. Please install it to continue."
  exit 1
fi

# --- Project Directory Resolution ---
# Determine the root directory of the current git repository.
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  err "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
fi
readonly PROJECT_DIR_ABS
echo "Detected project root: ${PROJECT_DIR_ABS}"

# --- Update Assistant Repo ---
echo "Updating google-ads-api-developer-assistant..."

CUSTOMER_ID_FILE="customer_id.txt"
TEMP_CUSTOMER_ID=$(mktemp)

# 1. Backup customer_id.txt if it exists
if [[ -f "${CUSTOMER_ID_FILE}" ]]; then
    echo "Backing up ${CUSTOMER_ID_FILE}..."
    cp "${CUSTOMER_ID_FILE}" "${TEMP_CUSTOMER_ID}"

    # Reset local changes to customer_id.txt to allow git pull
    if git ls-files --error-unmatch "${CUSTOMER_ID_FILE}" &> /dev/null; then
        echo "Resetting ${CUSTOMER_ID_FILE} to avoid merge conflicts..."
        git checkout "${CUSTOMER_ID_FILE}"
    fi
fi

if ! git pull; then
    err "ERROR: Failed to update google-ads-api-developer-assistant."
    if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
         echo "Restoring original customer_id.txt after failed pull..."
         mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    fi
    exit 1
fi

# 2. Restore customer_id.txt
if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
    echo "Restoring preserved ${CUSTOMER_ID_FILE}..."
    mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    echo "${CUSTOMER_ID_FILE} restored successfully."
    rm -f "${TEMP_CUSTOMER_ID}"
fi

echo "Successfully updated google-ads-api-developer-assistant."

# --- Handle Specific Library Additions ---
readonly ALL_LANGS="python php ruby java dotnet"
readonly DEFAULT_PARENT_DIR="${PROJECT_DIR_ABS}/client_libs"

for lang in $ALL_LANGS; do
  if is_enabled "$lang"; then
    repo_url=$(get_repo_url "$lang")
    repo_name=$(get_repo_name "$lang")
    lib_path="${DEFAULT_PARENT_DIR}/${repo_name}"

    if [[ ! -d "${lib_path}" ]]; then
        echo "Library ${repo_name} not found. Cloning into ${lib_path}..."
        mkdir -p "${DEFAULT_PARENT_DIR}"
        if ! git clone "${repo_url}" "${lib_path}"; then
            err "ERROR: Failed to clone ${repo_url}"
            exit 1
        fi
    fi
  fi
done

# --- Handle context_path argument ---
if [[ -n "${CONTEXT_PATH}" ]]; then
  echo "Registering context path: ${CONTEXT_PATH}..."
  if ! "${PROJECT_DIR_ABS}/.venv/bin/python3" "${PROJECT_DIR_ABS}/update_project_context.py" "${PROJECT_DIR_ABS}" "${CONTEXT_PATH}"; then
    err "ERROR: Failed to register context path."
    exit 1
  fi
fi

# --- Locate and Update Client Libraries ---
echo "Locating client libraries in ${DEFAULT_PARENT_DIR}..."

INCLUDE_DIRS=()
if [[ -d "${DEFAULT_PARENT_DIR}" ]]; then
    for dir in "${DEFAULT_PARENT_DIR}"/*; do
        if [[ -d "${dir}/.git" ]]; then
            INCLUDE_DIRS+=("${dir}")
        fi
    done
fi

if [[ ${#INCLUDE_DIRS[@]} -eq 0 ]]; then
    echo "No client libraries found to update in ${DEFAULT_PARENT_DIR}."
    exit 0
fi

echo "Found ${#INCLUDE_DIRS[@]} client libraries to update."

for lib_path in "${INCLUDE_DIRS[@]}"; do
    # Skip if path is empty
    [[ -z "${lib_path}" ]] && continue

    # Check if path exists
    if [[ ! -d "${lib_path}" ]]; then
        echo "WARN: Directory not found: ${lib_path}. Skipping."
        continue
    fi

    # Resolve absolute path for comparison
    if ! abs_lib_path=$(realpath "${lib_path}" 2>/dev/null); then
         echo "WARN: Could not resolve path: ${lib_path}. Skipping."
         continue
    fi

    # Skip the main assistant workspace since we already updated it
    if [[ "${abs_lib_path}" == "${PROJECT_DIR_ABS}" ]]; then
        continue
    fi



    # Check if it is a git repository
    if [[ ! -d "${abs_lib_path}/.git" ]]; then
        echo "Skipping non-git directory: ${abs_lib_path}"
        continue
    fi

    echo "Updating repository at: ${abs_lib_path}..."
    if ! (cd "${abs_lib_path}" && git pull); then
        err "ERROR: Failed to update ${abs_lib_path}"
        # We continue updating other libraries even if one fails? 
        # The prompt didn't specify, but usually best effort is good for updates.
        # However, scripts usually exit on error. set -e is on.
        # To fail fast:
        exit 1
    fi
    echo "Successfully updated ${abs_lib_path}."
done

# Pre-seed latest API version in project config
detect_and_seed_api_version "${DEFAULT_PARENT_DIR}/google-ads-python/google/ads/googleads" "${PROJECT_DIR_ABS}/config"

echo "Update complete."
