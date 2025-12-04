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
#   3. Updates the '.gemini/settings.json' file to include the project's API examples,
#      saved code, and the cloned Python library in the context.
#   4. Registers the project as a Gemini extension.

# Exit on any error, and on undefined variables.
set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

# --- Configuration ---
readonly PYTHON_LIB_REPO_URL="https://github.com/googleads/google-ads-python.git"
readonly PYTHON_LIB_NAME="google-ads-python"

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

# --- Argument Parsing ---
if [[ $# -eq 0 ]]; then
  readonly PYTHON_LIB_PARENT_DIR_ARG="${HOME}/python/src"
  echo "No python_lib_parent_dir provided. Using default: ${PYTHON_LIB_PARENT_DIR_ARG}"
elif [[ $# -eq 1 ]]; then
  readonly PYTHON_LIB_PARENT_DIR_ARG="$1"
else
  echo "Usage: $0 [python_lib_parent_dir]" >&2
  echo "  Clones/updates the ${PYTHON_LIB_NAME} repository and modifies the settings file." >&2
  echo "  This script must be run from within the google-ads-api-developer-assistant git repository." >&2
  echo "  [python_lib_parent_dir]: Optional. Fully qualified path to an existing directory" >&2
  echo "                         where the '${PYTHON_LIB_NAME}' library will be cloned." >&2
  echo "                         Defaults to: \${HOME}/python/src" >&2
  echo "                         This must NOT be under the project directory." >&2
  echo "  Example: $0 /home/user/development/libs" >&2
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

# --- Python Lib Path Resolution and Validation ---
if [[ ! -d "${PYTHON_LIB_PARENT_DIR_ARG}" ]]; then
  echo "Directory ${PYTHON_LIB_PARENT_DIR_ARG} does not exist. Creating it..."
  if ! mkdir -p "${PYTHON_LIB_PARENT_DIR_ARG}"; then
    err "ERROR: Failed to create directory: ${PYTHON_LIB_PARENT_DIR_ARG}"
    exit 1
  fi
fi

if ! PYTHON_LIB_PARENT_DIR=$(realpath "${PYTHON_LIB_PARENT_DIR_ARG}" 2>/dev/null); then
  err "ERROR: Invalid path provided for python_lib_parent_dir: ${PYTHON_LIB_PARENT_DIR_ARG}"
  exit 1
fi
readonly PYTHON_LIB_PARENT_DIR

readonly PYTHON_LIB_CLONE_PATH="${PYTHON_LIB_PARENT_DIR}/${PYTHON_LIB_NAME}"

# Ensure python_lib_parent_dir is NOT under the project_dir
if [[ "${PYTHON_LIB_PARENT_DIR}" == "${PROJECT_DIR_ABS}"* ]]; then
  err "ERROR: python_lib_parent_dir (${PYTHON_LIB_PARENT_DIR}) cannot be a subdirectory of the project directory (${PROJECT_DIR_ABS})"
  exit 1
fi

# --- Clone/Update Python Lib Repository ---
clone_or_update() {
  local repo_url="$1"
  local clone_path="$2"
  local repo_name

  repo_name=$(basename "${clone_path}")

  echo "Managing repository ${repo_name} in ${clone_path}"
  if [[ -d "${clone_path}/.git" ]]; then
    echo "WARN: Directory ${clone_path} already exists and is a git repo. Skipping clone."
    # Optionally, you could add git pull here:
    # (cd "${clone_path}" && git pull) || err "Failed to pull updates for ${repo_name}"
  elif [[ -d "${clone_path}" ]]; then
     echo "WARN: Directory ${clone_path} exists but is not a git repo. Skipping."
  else
    echo "Cloning ${repo_url} into ${clone_path}"
    if ! git clone "${repo_url}" "${clone_path}"; then
      err "ERROR: Failed to clone ${repo_url}"
      exit 1
    fi
    echo "Successfully cloned ${repo_name}."
  fi
}

clone_or_update "${PYTHON_LIB_REPO_URL}" "${PYTHON_LIB_CLONE_PATH}"

# --- Modify settings.json ---
readonly SETTINGS_FILE="${PROJECT_DIR_ABS}/.gemini/settings.json"

if [[ ! -f "${SETTINGS_FILE}" ]]; then
  err "ERROR: Settings file not found: ${SETTINGS_FILE}"
  exit 1
fi

echo "Updating ${SETTINGS_FILE} with context paths..."

# Define the includeDirectories paths, ensuring they are full paths
readonly CONTEXT_PATH1="${PROJECT_DIR_ABS}/api_examples"
readonly CONTEXT_PATH2="${PROJECT_DIR_ABS}/saved_code"
if ! CONTEXT_PATH3=$(realpath "${PYTHON_LIB_CLONE_PATH}" 2>/dev/null); then
    err "ERROR: Could not resolve absolute path for python lib clone: ${PYTHON_LIB_CLONE_PATH}"
    exit 1
fi
readonly CONTEXT_PATH3

# Use jq to modify the JSON file
TMP_SETTINGS_FILE=""
trap 'rm -f "${TMP_SETTINGS_FILE}"' EXIT # Cleanup tmp file on exit

if ! TMP_SETTINGS_FILE=$(mktemp "${SETTINGS_FILE}.XXXXXX"); then
  err "ERROR: Failed to create temporary file."
  exit 1
fi

if ! jq \
  --arg path1 "${CONTEXT_PATH1}" \
  --arg path2 "${CONTEXT_PATH2}" \
  --arg path3 "${CONTEXT_PATH3}" \
  '.context.includeDirectories = [$path1, $path2, $path3]' \
  "${SETTINGS_FILE}" > "${TMP_SETTINGS_FILE}"; then
  err "ERROR: jq command failed to update ${SETTINGS_FILE}"
  exit 1
fi

# Replace the original file with the modified one
if ! mv "${TMP_SETTINGS_FILE}" "${SETTINGS_FILE}"; then
  err "ERROR: Failed to move temporary file to ${SETTINGS_FILE}"
  exit 1
fi

# Register the extension with the gemini extensions manifest
echo "Registering with the gemini extensions manifest"
if ! INSTALL_OUTPUT=$(gemini extensions install "${PROJECT_DIR_ABS}" 2>&1); then
  if [[ "${INSTALL_OUTPUT}" == *"already installed"* ]]; then
    echo "Extension already installed. Reinstalling..."
    # We ignore the uninstall error just in case, though it should exist if we got "already installed"
    gemini extensions uninstall "google-ads-api-developer-assistant" || true
    gemini extensions install "${PROJECT_DIR_ABS}"
  else
    echo "${INSTALL_OUTPUT}" >&2
    err "ERROR: Failed to install extension."
    exit 1
  fi
else
  echo "${INSTALL_OUTPUT}"
fi

trap - EXIT # Clear the trap as the file has been moved.

echo "Successfully updated ${SETTINGS_FILE}"
echo "New contents of context.includeDirectories:"
jq '.context.includeDirectories' "${SETTINGS_FILE}"

echo "Setup complete."

