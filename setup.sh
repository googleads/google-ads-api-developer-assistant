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
readonly DEFAULT_PARENT_DIR="${HOME}/gaada"

# Associative arrays for repo URLs and default names
declare -A REPO_URLS=(
  ["python"]="https://github.com/googleads/google-ads-python.git"
  ["php"]="https://github.com/googleads/google-ads-php.git"
  ["ruby"]="https://github.com/googleads/google-ads-ruby.git"
  ["java"]="https://github.com/googleads/google-ads-java.git"
  ["dotnet"]="https://github.com/googleads/google-ads-dotnet.git"
)

declare -A REPO_NAMES=(
  ["python"]="google-ads-python"
  ["php"]="google-ads-php"
  ["ruby"]="google-ads-ruby"
  ["java"]="google-ads-java"
  ["dotnet"]="google-ads-dotnet"
)

# Defaults for paths (will be populated with defaults or overrides)
declare -A LIB_PATHS

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

# --- Help Function ---
usage() {
  echo "Usage: $0 [OPTIONS]"
  echo "  Clones/updates Google Ads client libraries and modifies the settings file."
  echo ""
  echo "  This script initializes the development environment for the Google Ads API Developer Assistant."
  echo "  It clones the client libraries into '${DEFAULT_PARENT_DIR}' by default, or to specified paths."
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --python <path>            Override path for google-ads-python"
  echo "    --php <path>               Override path for google-ads-php"
  echo "    --ruby <path>              Override path for google-ads-ruby"
  echo "    --java <path>              Override path for google-ads-java"
  echo "    --dotnet <path>            Override path for google-ads-dotnet"
  echo ""
  echo "  Example:"
  echo "    $0 --java /home/user/my-java-repo --python /home/user/my-python-repo"
  echo ""
}

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --python)
      LIB_PATHS["python"]="$2"
      shift 2
      ;;
    --php)
      LIB_PATHS["php"]="$2"
      shift 2
      ;;
    --ruby)
      LIB_PATHS["ruby"]="$2"
      shift 2
      ;;
    --java)
      LIB_PATHS["java"]="$2"
      shift 2
      ;;
    --dotnet)
      LIB_PATHS["dotnet"]="$2"
      shift 2
      ;;
    *)
      err "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

# --- Project Directory Resolution ---
# Determine the root directory of the current git repository.
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  err "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
fi
readonly PROJECT_DIR_ABS
echo "Detected project root: ${PROJECT_DIR_ABS}"

# --- Path Resolution and Validation ---
# Ensure default directory exists if we are going to use it
if [[ ! -d "${DEFAULT_PARENT_DIR}" ]]; then
  # We only create it if we actually need it (i.e., at least one lib is using default)
  # But simpler to just create it if it doesn't exist, as it's the intended home.
  echo "Creating default library directory: ${DEFAULT_PARENT_DIR}"
  mkdir -p "${DEFAULT_PARENT_DIR}" || { err "ERROR: Failed to create ${DEFAULT_PARENT_DIR}"; exit 1; }
fi

for lang in "${!REPO_NAMES[@]}"; do
  if [[ -z "${LIB_PATHS[$lang]:-}" ]]; then
    # Use default path
    LIB_PATHS["$lang"]="${DEFAULT_PARENT_DIR}/${REPO_NAMES[$lang]}"
  fi
  
  # Resolve to absolute path
  # Note: The directory might not exist yet if it's a clone target, 
  # but the parent should exist if we are to be safe? 
  # Actually, 'git clone' creates the directory. 
  # We should resolve the parent dir for validation if possible, or just resolve the path if it exists.
  
  # Logic:
  # 1. If path exists, resolve it.
  # 2. If path doesn't exist, check if parent exists.
  
  path="${LIB_PATHS[$lang]}"
  parent_dir=$(dirname "$path")
  
  if [[ ! -d "$parent_dir" ]]; then
     echo "Creating parent directory for $lang: $parent_dir"
     mkdir -p "$parent_dir" || { err "ERROR: Failed to create parent directory $parent_dir"; exit 1; }
  fi

  # Now we can optimistically set the absolute path. 
  # Ideally we want the canonical path. 
  # 'realpath' works on non-existent files in some versions, or we can use -m.
  # If -m is not supported, we can cd to parent and pwd.
  
  if command -v realpath &> /dev/null; then
      # Try using -m if available (doesn't require existence), otherwise just path
      ABS_PATH=$(realpath -m "$path")
  else
      # Fallback
      ABS_PATH="$(cd "$parent_dir" && pwd)/$(basename "$path")"
  fi
  
  LIB_PATHS["$lang"]="$ABS_PATH"

  # Validation: check against project dir
  if [[ "${ABS_PATH}" == "${PROJECT_DIR_ABS}"* ]]; then
     err "ERROR: ${lang} path (${ABS_PATH}) cannot be a subdirectory of the project directory (${PROJECT_DIR_ABS})"
     exit 1
  fi
done

# --- Clone/Update Repositories ---
clone_or_update() {
  local repo_url="$1"
  local clone_path="$2"
  local repo_name
  
  repo_name=$(basename "${clone_path}")

  echo "Managing repository ${repo_name} in ${clone_path}"
  if [[ -d "${clone_path}/.git" ]]; then
    echo "Directory ${clone_path} already exists. Updating..."
    if ! (cd "${clone_path}" && git pull); then
      echo "WARN: Failed to update ${repo_name}. Continuing..."
    else
      echo "Successfully updated ${repo_name}."
    fi
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

for lang in "${!REPO_URLS[@]}"; do
  clone_or_update "${REPO_URLS[$lang]}" "${LIB_PATHS[$lang]}"
done

# --- Modify settings.json ---
readonly SETTINGS_FILE="${PROJECT_DIR_ABS}/.gemini/settings.json"

if [[ ! -f "${SETTINGS_FILE}" ]]; then
  err "ERROR: Settings file not found: ${SETTINGS_FILE}"
  exit 1
fi

echo "Updating ${SETTINGS_FILE} with context paths..."

# Define the always-included directories
readonly CONTEXT_PATH_EXAMPLES="${PROJECT_DIR_ABS}/api_examples"
readonly CONTEXT_PATH_SAVED="${PROJECT_DIR_ABS}/saved_code"

# Collect all paths for jq
# We build a JSON array string or pass args. Passing args is safer.
# We have 5 dynamic paths + 2 static paths.

# Construct jq args
JQ_ARGS=(
  --arg examples "${CONTEXT_PATH_EXAMPLES}"
  --arg saved "${CONTEXT_PATH_SAVED}"
)

# Add each lib path as an arg
for lang in "${!LIB_PATHS[@]}"; do
  JQ_ARGS+=(--arg "lib_${lang}" "${LIB_PATHS[$lang]}")
done

# Construct the array construction string for jq
# It should look like: [$examples, $saved, $lib_python, $lib_php, ...]
JQ_ARRAY_STR="[\$examples, \$saved"
for lang in "${!LIB_PATHS[@]}"; do
  JQ_ARRAY_STR+=", \$lib_$lang"
done
JQ_ARRAY_STR+="]"

# Use jq to modify the JSON file
TMP_SETTINGS_FILE=""
trap 'rm -f "${TMP_SETTINGS_FILE}"' EXIT # Cleanup tmp file on exit

if ! TMP_SETTINGS_FILE=$(mktemp "${SETTINGS_FILE}.XXXXXX"); then
  err "ERROR: Failed to create temporary file."
  exit 1
fi

if ! jq \
  "${JQ_ARGS[@]}" \
  ".context.includeDirectories = ${JQ_ARRAY_STR}" \
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
if command -v gemini &> /dev/null; then
  if ! INSTALL_OUTPUT=$(gemini extensions install "${PROJECT_DIR_ABS}" 2>&1); then
    if [[ "${INSTALL_OUTPUT}" == *"already installed"* ]]; then
      echo "Extension already installed. Reinstalling..."
      # We ignore the uninstall error just in case
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
else
  echo "WARN: 'gemini' command not found. Skipping extension registration."
  echo "      This is normal if you are running this script outside of the Gemini environment"
  echo "      or if 'gemini' is an alias not exported to this script."
fi

trap - EXIT # Clear the trap

echo "Successfully updated ${SETTINGS_FILE}"
echo "New contents of context.includeDirectories:"
jq '.context.includeDirectories' "${SETTINGS_FILE}"

echo "Setup complete."
echo ""
echo "IMPORTANT: You must manually configure a development environment for each language you wish to use."
echo "           (e.g.,  run 'pip install google-ads' for Python, run 'composer install' for PHP, etc.)"

