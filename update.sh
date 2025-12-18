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
#   2. Reads '.gemini/settings.json' to locate the 'google-ads-python' repository.
#   3. Updates the 'google-ads-python' repository (git pull).

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
  echo "  2. Reads '.gemini/settings.json' to find configured client libraries."
  echo "  3. Updates each found client library repository (git pull)."
  echo ""
  echo "  Options:"
  echo "    -h, --help    Show this help message and exit"
  echo ""
}

# --- Argument Parsing ---
if [[ "${1:-}" == "-h" ]] || [[ "${1:-}" == "--help" ]]; then
  usage
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

SETTINGS_JSON=".gemini/settings.json"
TEMP_SETTINGS=$(mktemp)

CUSTOMER_ID_FILE="customer_id.txt"
TEMP_CUSTOMER_ID=$(mktemp)

# 1. Backup existing settings if they exist
if [[ -f "${SETTINGS_JSON}" ]]; then
    echo "Backing up ${SETTINGS_JSON}..."
    cp "${SETTINGS_JSON}" "${TEMP_SETTINGS}"
    
    # 2. Reset local changes to settings.json to allow git pull
    # Only if the file is tracked and modified (or just blindly checkout if we know it's strict)
    # Safest is to just checkout it if it exists in git.
    if git ls-files --error-unmatch "${SETTINGS_JSON}" &> /dev/null; then
        echo "Resetting ${SETTINGS_JSON} to avoid merge conflicts..."
        git checkout "${SETTINGS_JSON}"
    fi
fi

# 1b. Backup customer_id.txt if it exists
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
    # Attempt to restore settings if they were backed up? 
    # Probably safer to leave the repo state as is if pull failed, 
    # but strictly speaking we might want to restore the user's settings 
    # if we reverted them.
    if [[ -f "${TEMP_SETTINGS}" ]] && [[ -s "${TEMP_SETTINGS}" ]]; then
         echo "Restoring original settings after failed pull..."
         mv "${TEMP_SETTINGS}" "${SETTINGS_JSON}"
    fi
    if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
         echo "Restoring original customer_id.txt after failed pull..."
         mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    fi
    exit 1
fi

# 3. Restore/Merge settings
if [[ -f "${TEMP_SETTINGS}" ]] && [[ -s "${TEMP_SETTINGS}" ]]; then
    echo "Merging preserved settings with new defaults..."
    # Merge: existing (backup) *over* new (repo)
    # We want local user values to override repo values, but we also want 
    # to keep any new keys from the repo that weren't in user's file.
    # Logic: .[0] is repo (new), .[1] is backup (user). 
    # .[0] * .[1] means backup overrides repo.
    if jq -s '.[0] * .[1]' "${SETTINGS_JSON}" "${TEMP_SETTINGS}" > "${TEMP_SETTINGS}.merged"; then
        mv "${TEMP_SETTINGS}.merged" "${SETTINGS_JSON}"
        echo "Settings restored and merged successfully."
    else
        err "WARN: Failed to merge settings.json. Restoring original backup without merge."
        mv "${TEMP_SETTINGS}" "${SETTINGS_JSON}"
    fi
    rm -f "${TEMP_SETTINGS}"
fi

# 3b. Restore customer_id.txt
if [[ -f "${TEMP_CUSTOMER_ID}" ]] && [[ -s "${TEMP_CUSTOMER_ID}" ]]; then
    echo "Restoring preserved ${CUSTOMER_ID_FILE}..."
    # Always overwrite with user's backup
    mv "${TEMP_CUSTOMER_ID}" "${CUSTOMER_ID_FILE}"
    echo "${CUSTOMER_ID_FILE} restored successfully."
    rm -f "${TEMP_CUSTOMER_ID}"
fi

echo "Successfully updated google-ads-api-developer-assistant."

# --- Locate and Update Client Libraries ---
readonly SETTINGS_FILE="${PROJECT_DIR_ABS}/.gemini/settings.json"

if [[ ! -f "${SETTINGS_FILE}" ]]; then
  err "ERROR: Settings file not found: ${SETTINGS_FILE}"
  err "Please run setup.sh first."
  exit 1
fi

echo "Reading ${SETTINGS_FILE} to find client libraries..."

# Read all includeDirectories
INCLUDE_DIRS=()
while IFS= read -r line; do
    INCLUDE_DIRS+=("$line")
done < <(jq -r '.context.includeDirectories[]' "${SETTINGS_FILE}")

if [[ ${#INCLUDE_DIRS[@]} -eq 0 ]]; then
    echo "WARN: No directories found in ${SETTINGS_FILE}."
    exit 0
fi

echo "Found ${#INCLUDE_DIRS[@]} directories in settings."

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

    # Skip if it is the project directory itself or a subdirectory of it
    if [[ "${abs_lib_path}" == "${PROJECT_DIR_ABS}"* ]]; then
        echo "Skipping internal directory: ${abs_lib_path}"
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
