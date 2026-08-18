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
readonly PLUGIN_SOURCE_DIR="${PROJECT_DIR_ABS}/plugins/google-ads-api-developer-assistant"
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

# Helper to resolve OS-specific target plugin directory
get_plugin_target_dir() {
  local target="$1"
  local os_type
  os_type=$(uname -s 2>/dev/null || echo "Linux")
  echo "Detected OS: ${os_type}"

  case "${target}" in
    agy)
      PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
      ;;
    claudecode)
      PLUGIN_TARGET_DIR="${HOME}/.claude/plugins/google-ads-api-developer-assistant"
      ;;
    *)
      err "ERROR: Invalid target '${target}'. Must be 'agy' or 'claudecode'."
      exit 1
      ;;
  esac
}

# --- Defaults ---
TARGET=""
INSTALL_PYTHON=true
INSTALL_PHP=false
INSTALL_RUBY=false
INSTALL_JAVA=false
INSTALL_DOTNET=false
ANY_SELECTED=false

# --- Help Function ---
usage() {
  echo "Usage: $0 <agy|claudecode> [OPTIONS]"
  echo "       $0 --target <agy|claudecode> [OPTIONS]"
  echo "  Installs the Google Ads API Developer Assistant as a plugin for Antigravity or Claude Code."
  echo ""
  echo "  Required Argument:"
  echo "    <agy|claudecode>           Target platform: 'agy' (Antigravity) or 'claudecode' (Claude Code)"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --target TARGET            Target platform ('agy' or 'claudecode')"
  echo "    --agy                      Install for Antigravity (shorthand for --target agy)"
  echo "    --claudecode               Install for Claude Code (shorthand for --target claudecode)"
  echo "    --php                      Include google-ads-php client library"
  echo "    --ruby                     Include google-ads-ruby client library"
  echo "    --java                     Include google-ads-java client library"
  echo "    --dotnet                   Include google-ads-dotnet client library"
  echo ""
  echo "  By default, the Python client library is included in the plugin."
  echo ""
  echo "  Examples:"
  echo "    $0 agy                     (Installs plugin for Antigravity)"
  echo "    $0 claudecode              (Installs plugin for Claude Code into OS-specific directory)"
  echo "    $0 agy --java              (Installs for Antigravity with Java and Python client libraries)"
  echo "    $0 claudecode --php        (Installs for Claude Code with PHP and Python client libraries)"
  echo ""
}

# --- Argument Parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    agy|claudecode)
      TARGET="$1"
      shift
      ;;
    --target)
      if [[ $# -lt 2 ]]; then
        err "ERROR: --target requires an argument ('agy' or 'claudecode')."
        usage
        exit 1
      fi
      TARGET=$(echo "$2" | tr '[:upper:]' '[:lower:]')
      shift 2
      ;;
    --target=*)
      TARGET=$(echo "${1#*=}" | tr '[:upper:]' '[:lower:]')
      shift
      ;;
    --agy)
      TARGET="agy"
      shift
      ;;
    --claudecode)
      TARGET="claudecode"
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

# --- Validate Required Target ---
if [[ -z "${TARGET}" ]]; then
  err "ERROR: Missing required target argument: 'agy' or 'claudecode'."
  usage
  exit 1
fi

if [[ "${TARGET}" != "agy" && "${TARGET}" != "claudecode" ]]; then
  err "ERROR: Invalid target '${TARGET}'. Must be 'agy' or 'claudecode'."
  usage
  exit 1
fi

# --- Environment Verification ---
check_python() {
  local py_cmd=""
  for cmd in python3 python; do
    if command -v "${cmd}" &>/dev/null; then
      if "${cmd}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' &>/dev/null; then
        py_cmd="${cmd}"
        break
      fi
    fi
  done

  if [[ -n "${py_cmd}" ]]; then
    local py_ver
    py_ver=$("${py_cmd}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)
    echo "Found Python ${py_ver} (${py_cmd})"
    return 0
  fi

  local found_ver=""
  for cmd in python3 python; do
    if command -v "${cmd}" &>/dev/null; then
      found_ver=$("${cmd}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")' 2>/dev/null || true)
      if [[ -n "${found_ver}" ]]; then
        found_ver="${cmd} (${found_ver})"
        break
      fi
    fi
  done

  err "ERROR: Python 3.10 or higher is required."
  if [[ -n "${found_ver}" ]]; then
    err "Incompatible Python version detected: ${found_ver}."
  else
    err "No Python interpreter was found on PATH."
  fi
  err "Please install Python 3.10 or later and ensure it is available in your PATH."
  err "See: https://www.python.org/downloads/"
  return 1
}

check_antigravity() {
  local found_antigravity=false
  local antigravity_detail=""

  if command -v agy &>/dev/null; then
    found_antigravity=true
    antigravity_detail="Antigravity CLI (agy) found at $(command -v agy)"
  elif command -v antigravity &>/dev/null; then
    found_antigravity=true
    antigravity_detail="Antigravity CLI (antigravity) found at $(command -v antigravity)"
  fi

  if [[ "${found_antigravity}" == "false" ]]; then
    if [[ -n "${ANTIGRAVITY_APP_DIR:-}" || -n "${ANTIGRAVITY_LS_ADDRESS:-}" || -n "${ANTIGRAVITY_PORT:-}" || -n "${JETSKI_HOME:-}" || -n "${GEMINI_HOME:-}" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity environment detected via environment variables"
    elif [[ -d "${HOME}/.gemini" || -d "${HOME}/.antigravity" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity configuration/installation found in home directory (~/.gemini or ~/.antigravity)"
    elif [[ -d "/Applications/Antigravity.app" || -d "${HOME}/Applications/Antigravity.app" || -d "/Applications/Google Antigravity.app" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity Desktop application found on macOS"
    elif [[ -d "/opt/Antigravity" || -d "/usr/share/antigravity" || -d "/usr/local/share/antigravity" ]]; then
      found_antigravity=true
      antigravity_detail="Antigravity Desktop installation found on Linux"
    fi
  fi

  if [[ "${found_antigravity}" == "true" ]]; then
    echo "Found Antigravity: ${antigravity_detail}"
    return 0
  fi

  err "ERROR: Antigravity CLI or Antigravity Desktop/Web is not installed."
  err "The Google Ads API Developer Assistant requires an active Antigravity environment."
  err "Please install Antigravity CLI ('agy' or 'antigravity') or Antigravity Desktop/Web to continue."
  return 1
}

check_claudecode() {
  local found_claude=false
  local claude_detail=""

  if command -v claude &>/dev/null; then
    found_claude=true
    claude_detail="Claude Code CLI (claude) found at $(command -v claude)"
  elif command -v claude-code &>/dev/null; then
    found_claude=true
    claude_detail="Claude Code CLI found at $(command -v claude-code)"
  fi

  if [[ "${found_claude}" == "false" ]]; then
    if [[ -d "${HOME}/Library/Application Support/Claude" || -d "${HOME}/.config/claude" || -d "${HOME}/.claude" || -n "${CLAUDE_CODE_HOME:-}" ]]; then
      found_claude=true
      claude_detail="Claude environment detected in configuration directory or environment variables"
    fi
  fi

  if [[ "${found_claude}" == "true" ]]; then
    echo "Found Claude Code: ${claude_detail}"
    return 0
  fi

  echo "Note: Claude Code CLI ('claude') not found on PATH. Proceeding with installation to target plugin directory."
  return 0
}

check_environment() {
  echo "Checking environment for ${TARGET}..."
  local env_ok=true

  if ! check_python; then
    env_ok=false
  fi

  if [[ "${TARGET}" == "agy" ]]; then
    if ! check_antigravity; then
      env_ok=false
    fi
  elif [[ "${TARGET}" == "claudecode" ]]; then
    if ! check_claudecode; then
      env_ok=false
    fi
  fi

  if [[ "${env_ok}" != "true" ]]; then
    err "ERROR: Environment check failed. Aborting installation."
    exit 1
  fi
  echo "Environment check passed."
}

# Run environment verification before proceeding with installation
check_environment

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

# --- Clone/Update Repositories ---
clone_or_update() {
  local repo_url="$1"
  local clone_path="$2"
  local log_file="$3"
  local repo_name
  
  repo_name=$(basename "${clone_path}")

  {
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
  } > "${log_file}" 2>&1
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

# --- Plugin Installation ---
if ! command -v git &> /dev/null; then
  err "ERROR: git is not installed. Please install it to continue."
  exit 1
fi

if [[ ! -d "${PLUGIN_SOURCE_DIR}" ]]; then
  err "ERROR: Plugin directory '${PLUGIN_SOURCE_DIR}' does not exist."
  exit 1
fi

get_plugin_target_dir "${TARGET}"
echo "Installing plugin for ${TARGET} into: ${PLUGIN_TARGET_DIR}"
mkdir -p "$(dirname "${PLUGIN_TARGET_DIR}")"
rm -rf "${PLUGIN_TARGET_DIR}"
cp -r "${PLUGIN_SOURCE_DIR}" "${PLUGIN_TARGET_DIR}"

# Ensure plugin client_libs directory exists
mkdir -p "${PLUGIN_TARGET_DIR}/client_libs"

# Add any additional selected client libraries to plugin structure
for lang in php ruby java dotnet; do
  if is_enabled "$lang"; then
    repo_name=$(get_repo_name "$lang")
    target_lib_path="${PLUGIN_TARGET_DIR}/client_libs/${repo_name}"
    source_lib_path="${PROJECT_DIR_ABS}/client_libs/${repo_name}"
    url=$(get_repo_url "$lang")
    log_file="${PROJECT_DIR_ABS}/install_${lang}_log_$$.tmp"

    if [[ -d "${source_lib_path}" ]]; then
      echo "Adding ${repo_name} to plugin client_libs from local repository..."
      rm -rf "${target_lib_path}"
      cp -r "${source_lib_path}" "${target_lib_path}"
    else
      echo "Cloning ${repo_name} into plugin client_libs..."
      clone_or_update "$url" "${target_lib_path}" "${log_file}"
      if [[ -f "${log_file}" ]]; then
        cat "${log_file}"
        rm -f "${log_file}"
      fi
    fi
  fi
done

# Pre-seed latest API version in plugin and project config
detect_and_seed_api_version "${PLUGIN_TARGET_DIR}/client_libs/google-ads-python/google/ads/googleads" "${PLUGIN_TARGET_DIR}/config"
detect_and_seed_api_version "${PLUGIN_TARGET_DIR}/client_libs/google-ads-python/google/ads/googleads" "${PROJECT_DIR_ABS}/config"

echo "Plugin installation for ${TARGET} complete."
echo ""
if [[ "${TARGET}" == "agy" ]]; then
  echo "Restart your Antigravity / agy host to activate the plugin."
else
  echo "Restart your Claude Code environment to activate the plugin."
fi
