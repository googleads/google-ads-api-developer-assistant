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
#   It performs the following steps:
#   1. Updates the 'google-ads-api-developer-assistant' repository (git pull).
#   2. Locates cloned client libraries under 'client_libs/'.
#   3. Updates each found client library repository (git pull).

# Exit on any error, and on undefined variables.
set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

# --- Help Function ---
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "  Updates the Google Ads API Developer Assistant and configured client libraries."
  echo ""
  echo "  This script performs the following actions:"
  echo "  1. Updates the 'google-ads-api-developer-assistant' repository (git pull)."
  echo "  2. Locates cloned client libraries under 'client_libs/'."
  echo "  3. Updates each found client library repository (git pull)."
  echo ""
  echo "  Options:"
  echo "    -h, --help           Show this help message and exit"
  echo "    --python             Ensure google-ads-python is present and updated"
  echo "    --php                Ensure google-ads-php is present and updated"
  echo "    --ruby               Ensure google-ads-ruby is present and updated"
  echo "    --java               Ensure google-ads-java is present and updated"
  echo "    --dotnet             Ensure google-ads-dotnet is present and updated"
  echo "    --context_path PATH  Add the specified directory to the project configuration for context"
  echo ""
  echo "  If flags are provided, the script will ensure those libraries are installed"
  echo "  (cloned) and registered if they weren't already."
  echo ""
}

# --- Defaults ---
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
      # Ignore unknown options or handle them
      shift
      ;;
  esac
done

# Helper functions for repo info (Matching setup.sh)
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

echo "Update complete."
