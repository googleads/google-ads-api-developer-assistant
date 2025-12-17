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
if ! git pull; then
    err "ERROR: Failed to update google-ads-api-developer-assistant."
    exit 1
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
