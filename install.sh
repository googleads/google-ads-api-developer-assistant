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

# --- Project Directory Resolution ---
# Determine the root directory of the current git repository.
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  err "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
fi
readonly PROJECT_DIR_ABS
echo "Detected project root: ${PROJECT_DIR_ABS}"

# --- Configuration ---
readonly DEFAULT_PARENT_DIR="${PROJECT_DIR_ABS}/client_libs"
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

# --- Defaults ---
# Simple variables to track selection (associative arrays not supported in Bash 3.2)
INSTALL_PYTHON=true
INSTALL_PHP=false
INSTALL_RUBY=false
INSTALL_JAVA=false
INSTALL_DOTNET=false
ANY_SELECTED=false
INSTALL_DEPS=false

# --- Dependency Check ---
if ! command -v jq &> /dev/null; then
  echo "jq is not installed. Attempting to install..."
  if command -v brew &> /dev/null; then
      echo "Homebrew detected. Installing jq..."
      if brew install jq; then
          echo "Successfully installed jq."
      else
          err "ERROR: Failed to install jq via Homebrew."
          exit 1
      fi
  elif command -v apt-get &> /dev/null; then
      if sudo apt-get update && sudo apt-get install -y jq; then
          echo "Successfully installed jq."
      else
          err "ERROR: Failed to install jq automatically."
          err "Please install jq manually to continue."
          err "See: https://jqlang.github.io/jq/download/"
          exit 1
      fi
  else
      err "ERROR: jq is not installed and no supported package manager (brew/apt-get) found."
      err "Please install jq manually to continue."
      err "See: https://jqlang.github.io/jq/download/"
      exit 1
  fi
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
  echo "  It clones the selected client libraries into '${DEFAULT_PARENT_DIR}'."
  echo "  The google-ads-python library is always installed by default."
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit
    --install-deps             Install dependencies (e.g. pip packages)"
  echo "    --php                      Include google-ads-php"
  echo "    --ruby                     Include google-ads-ruby"
  echo "    --java                     Include google-ads-java"
  echo "    --dotnet                   Include google-ads-dotnet"
  echo ""
  echo "  If no language flags are provided, only the Python library will be installed."
  echo ""
  echo "  Example:"
  echo "    $0 --java                  (Installs Java and Python libraries)"
  echo ""
}

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
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
    --install-deps)
      INSTALL_DEPS=true
      shift
      ;;
    *)
      err "ERROR: Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

# --- Language Selection Logic ---
# Python is always installed. Other languages are only installed if selected.
if [[ "${ANY_SELECTED}" == "false" ]]; then
  echo "No additional languages selected. Defaulting to Python only."
fi

# --- Path Resolution and Validation ---
# Ensure default directory exists
echo "Ensuring default library directory exists: ${DEFAULT_PARENT_DIR}"
mkdir -p "${DEFAULT_PARENT_DIR}" || { err "ERROR: Failed to create ${DEFAULT_PARENT_DIR}"; exit 1; }

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

# Resolve paths
for lang in $ALL_LANGS; do
  if is_enabled "$lang"; then
    repo_name=$(get_repo_name "$lang")
    path="${DEFAULT_PARENT_DIR}/${repo_name}"
    
    # Resolve to absolute path
    if command -v realpath &> /dev/null; then
        # Try using -m if available (doesn't require existence), otherwise just path
        # On macOS, realpath might not support -m or might not exist (coreutils).
        # We handle missing realpath below.
        ABS_PATH=$(realpath -m "$path" 2>/dev/null || realpath "$path" 2>/dev/null || echo "$path")
    else
        # Fallback - parent (DEFAULT_PARENT_DIR) exists now
        ABS_PATH="$(cd "${DEFAULT_PARENT_DIR}" && pwd)/$(basename "$path")"
    fi
    
    # Store path in dynamic variable for later use (jq args)
    # Bash 3.2 compatible way to set variable by name
    eval "LIB_PATH_${lang}='${ABS_PATH}'"
    

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

for lang in $ALL_LANGS; do
  if is_enabled "$lang"; then
    eval "path=\"\$LIB_PATH_${lang}\""
    url=$(get_repo_url "$lang")
    clone_or_update "$url" "$path"
  fi
done

# --- Modify settings.json ---
readonly SETTINGS_FILE="${PROJECT_DIR_ABS}/.gemini/settings.json"

if [[ ! -f "${SETTINGS_FILE}" ]]; then
  err "ERROR: Settings file not found: ${SETTINGS_FILE}"
  exit 1
fi

echo "Updating ${SETTINGS_FILE} with context paths..."

readonly CONTEXT_PATH_EXAMPLES="${PROJECT_DIR_ABS}/api_examples"
readonly CONTEXT_PATH_SAVED="${PROJECT_DIR_ABS}/saved/code"

# Construct jq args
JQ_ARGS=(
  --arg examples "${CONTEXT_PATH_EXAMPLES}"
  --arg saved "${CONTEXT_PATH_SAVED}"
)

# Add each lib path as an arg
for lang in $ALL_LANGS; do
  if is_enabled "$lang"; then
    eval "path=\"\$LIB_PATH_${lang}\""
    JQ_ARGS+=(--arg "lib_${lang}" "${path}")
  fi
done

# Construct the array construction string for jq
JQ_ARRAY_STR="[\$examples, \$saved"
for lang in $ALL_LANGS; do
  if is_enabled "$lang"; then
    JQ_ARRAY_STR+=", \$lib_$lang"
  fi
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

echo "Registering Google Ads API Developer Assistant as a Gemini extension..."
if command -v gemini &> /dev/null; then
  # Use yes Y to handle the interactive prompt as --consent is not supported in OSS
  # Capture output to detect "already installed" state
  if ! INSTALL_OUTPUT=$(yes Y | gemini extensions install https://github.com/googleads/google-ads-api-developer-assistant.git 2>&1); then
    if [[ "${INSTALL_OUTPUT}" == *"already installed"* ]]; then
      echo "Extension already installed. Reinstalling..."
      gemini extensions uninstall "google-ads-api-developer-assistant" || true
      yes Y | gemini extensions install https://github.com/googleads/google-ads-api-developer-assistant.git
    else
      echo "${INSTALL_OUTPUT}" >&2
      err "WARN: Failed to register extension automatically. You may need to run 'gemini extensions install https://github.com/googleads/google-ads-api-developer-assistant.git' manually."
    fi
  else
    echo "${INSTALL_OUTPUT}"
  fi
else
  echo "WARN: 'gemini' command not found. Skipping extension registration."
fi

if is_enabled "python" && [[ "${INSTALL_DEPS}" == "true" ]]; then
  echo "Installing google-ads via pip..."
  python -m pip install --upgrade google-ads
fi

if is_enabled "php" && [[ "${INSTALL_DEPS}" == "true" ]]; then
  echo "Installing google-ads-php dependencies via composer..."
  eval "path=\"\$LIB_PATH_php\""
  if [[ -f "${path}/composer.json" ]]; then
    (cd "${path}" && composer install)
  else
    echo "WARN: composer.json not found in ${path}"
  fi
fi

if is_enabled "ruby" && [[ "${INSTALL_DEPS}" == "true" ]]; then
  echo "Installing google-ads-ruby dependencies via bundle..."
  eval "path=\"\$LIB_PATH_ruby\""
  if [[ -f "${path}/Gemfile" ]]; then
    (cd "${path}" && bundle install)
  else
    echo "WARN: Gemfile not found in ${path}"
  fi
fi

trap - EXIT # Clear the trap

echo "Successfully updated ${SETTINGS_FILE}"
echo "New contents of context.includeDirectories:"
jq '.context.includeDirectories' "${SETTINGS_FILE}"

echo "Installation complete."
echo ""
echo "IMPORTANT: You must configure and verify the development environment for each language you wish to use."
echo "           (e.g.,  run 'pip install google-ads' for Python, run 'composer install' for PHP, etc.)"
echo "           If you used --install-deps, you can verify the installation by running 'python -m pip show google-ads' for Python, 'composer show google/ads-api-php-client' for PHP, etc."
