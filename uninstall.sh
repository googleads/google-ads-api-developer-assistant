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
#   This script uninstalls the Google Ads API Developer Assistant.
#   It supports removing either the standalone project directory, the installed plugin,
#   or specific client libraries from either environment.

set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

# Helper to resolve OS-specific target plugin directory
get_plugin_target_dir() {
  local target="$1"
  local os_type
  os_type=$(uname -s 2>/dev/null || echo "Linux")

  case "${target}" in
    agy)
      echo "${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
      ;;
    claudecode)
      case "${os_type}" in
        Darwin*)
          echo "${HOME}/Library/Application Support/Claude/plugins/google-ads-api-developer-assistant"
          ;;
        Linux*)
          if [[ -n "${XDG_CONFIG_HOME:-}" ]]; then
            echo "${XDG_CONFIG_HOME}/claude/plugins/google-ads-api-developer-assistant"
          else
            echo "${HOME}/.config/claude/plugins/google-ads-api-developer-assistant"
          fi
          ;;
        CYGWIN*|MINGW*|MSYS*)
          if [[ -n "${APPDATA:-}" ]]; then
            echo "${APPDATA}/Claude/plugins/google-ads-api-developer-assistant"
          else
            echo "${HOME}/.claude/plugins/google-ads-api-developer-assistant"
          fi
          ;;
        *)
          echo "${HOME}/.claude/plugins/google-ads-api-developer-assistant"
          ;;
      esac
      ;;
    *)
      err "ERROR: Invalid target '${target}'. Must be 'agy' or 'claudecode'."
      exit 1
      ;;
  esac
}

# --- Defaults ---
TARGET=""
UNINSTALL_PYTHON=false
UNINSTALL_PHP=false
UNINSTALL_RUBY=false
UNINSTALL_JAVA=false
UNINSTALL_DOTNET=false
UNINSTALL_ALL_LIBS=false
ANY_SELECTED=false
AUTO_CONFIRM=false

# --- Help Function ---
usage() {
  echo "Usage: $0 <agy|claudecode> [OPTIONS]"
  echo "       $0 --target <agy|claudecode> [OPTIONS]"
  echo "  Uninstalls the Google Ads API Developer Assistant plugin from Antigravity or Claude Code."
  echo ""
  echo "  Required Argument:"
  echo "    <agy|claudecode>           Target platform: 'agy' (Antigravity) or 'claudecode' (Claude Code)"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    --target TARGET            Target platform ('agy' or 'claudecode')"
  echo "    --agy                      Uninstall from Antigravity (shorthand for --target agy)"
  echo "    --claudecode               Uninstall from Claude Code (shorthand for --target claudecode)"
  echo "    -y, --yes, -f, --force     Skip confirmation prompt"
  echo "    --all                      Remove all client libraries from plugin client_libs/"
  echo "    --python                   Remove only google-ads-python client library"
  echo "    --php                      Remove only google-ads-php client library"
  echo "    --ruby                     Remove only google-ads-ruby client library"
  echo "    --java                     Remove only google-ads-java client library"
  echo "    --dotnet                   Remove only google-ads-dotnet client library"
  echo ""
  echo "  Examples:"
  echo "    $0 agy                     (Uninstalls and deletes the entire Antigravity plugin directory)"
  echo "    $0 claudecode -y           (Uninstalls Claude Code plugin without confirmation prompt)"
  echo "    $0 agy --all               (Removes all client libraries from the Antigravity plugin)"
  echo "    $0 claudecode --java       (Removes only the Java library from the Claude Code plugin)"
  echo ""
}

# Helper functions for repo info
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
    python) [[ "${UNINSTALL_PYTHON}" == "true" ]] ;;
    php)    [[ "${UNINSTALL_PHP}"    == "true" ]] ;;
    ruby)   [[ "${UNINSTALL_RUBY}"   == "true" ]] ;;
    java)   [[ "${UNINSTALL_JAVA}"   == "true" ]] ;;
    dotnet) [[ "${UNINSTALL_DOTNET}" == "true" ]] ;;
  esac
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
    --all)
      UNINSTALL_ALL_LIBS=true
      UNINSTALL_PYTHON=true
      UNINSTALL_PHP=true
      UNINSTALL_RUBY=true
      UNINSTALL_JAVA=true
      UNINSTALL_DOTNET=true
      ANY_SELECTED=true
      shift
      ;;
    --python)
      UNINSTALL_PYTHON=true
      ANY_SELECTED=true
      shift
      ;;
    --php)
      UNINSTALL_PHP=true
      ANY_SELECTED=true
      shift
      ;;
    --ruby)
      UNINSTALL_RUBY=true
      ANY_SELECTED=true
      shift
      ;;
    --java)
      UNINSTALL_JAVA=true
      ANY_SELECTED=true
      shift
      ;;
    --dotnet)
      UNINSTALL_DOTNET=true
      ANY_SELECTED=true
      shift
      ;;
    -y|--yes|-f|--force)
      AUTO_CONFIRM=true
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

PLUGIN_TARGET_DIR=$(get_plugin_target_dir "${TARGET}")
LEGACY_PLUGIN_DIR=""
if [[ "${TARGET}" == "agy" ]]; then
  LEGACY_PLUGIN_DIR="${HOME}/.gemini/config/plugins/google_ads_assistant_plugin"
fi

if [[ ! -d "${PLUGIN_TARGET_DIR}" && ( -z "${LEGACY_PLUGIN_DIR}" || ! -d "${LEGACY_PLUGIN_DIR}" ) ]]; then
  echo "Plugin directory '${PLUGIN_TARGET_DIR}' does not exist. Nothing to uninstall."
  exit 0
fi

# If specific client libraries were requested to be removed
if [[ "${ANY_SELECTED}" == "true" ]]; then
  search_dirs=("${PLUGIN_TARGET_DIR}")
  if [[ -n "${LEGACY_PLUGIN_DIR}" && -d "${LEGACY_PLUGIN_DIR}" ]]; then
    search_dirs+=("${LEGACY_PLUGIN_DIR}")
  fi

  for dir in "${search_dirs[@]}"; do
    if [[ -d "${dir}/client_libs" ]]; then
      for lang in python php ruby java dotnet; do
        if is_enabled "$lang"; then
          repo_name=$(get_repo_name "$lang")
          lib_path="${dir}/client_libs/${repo_name}"
          if [[ -d "${lib_path}" ]]; then
            echo "Removing ${repo_name} from ${dir}/client_libs/..."
            rm -rf "${lib_path}"
            echo "Successfully removed ${repo_name}."
          else
            echo "Library ${repo_name} not found in ${dir}/client_libs/."
          fi
        fi
      done
    fi
  done
  echo "Plugin client library removal for ${TARGET} complete."
  echo ""
  if [[ "${TARGET}" == "agy" ]]; then
    echo "Restart your Antigravity / agy host to apply changes."
  else
    echo "Restart your Claude Code environment to apply changes."
  fi
  exit 0
fi

echo "This will uninstall the Google Ads API Developer Assistant plugin for ${TARGET}"
echo "and DELETE the directory: ${PLUGIN_TARGET_DIR}"

if [[ "${AUTO_CONFIRM}" != "true" ]]; then
  read -p "Are you sure you want to proceed? (Y/n): " confirm
  if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
  fi
fi

echo "Removing plugin directory: ${PLUGIN_TARGET_DIR}..."
rm -rf "${PLUGIN_TARGET_DIR}"
if [[ -n "${LEGACY_PLUGIN_DIR}" && -d "${LEGACY_PLUGIN_DIR}" ]]; then
  rm -rf "${LEGACY_PLUGIN_DIR}"
fi

echo "Plugin uninstallation for ${TARGET} complete."
echo ""
if [[ "${TARGET}" == "agy" ]]; then
  echo "Restart your Antigravity / agy host to complete plugin uninstallation."
else
  echo "Restart your Claude Code environment to complete plugin uninstallation."
fi
