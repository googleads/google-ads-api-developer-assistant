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

readonly PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"
readonly LEGACY_PLUGIN_DIR="${HOME}/.gemini/config/plugins/google_ads_assistant_plugin"

# --- Defaults ---
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
  echo "Usage: $0 [OPTIONS]"
  echo "  Uninstalls the Google Ads API Developer Assistant plugin from Antigravity."
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    -y, --yes, -f, --force     Skip confirmation prompt"
  echo "    --all                      Remove all client libraries from plugin client_libs/"
  echo "    --python                   Remove only google-ads-python client library"
  echo "    --php                      Remove only google-ads-php client library"
  echo "    --ruby                     Remove only google-ads-ruby client library"
  echo "    --java                     Remove only google-ads-java client library"
  echo "    --dotnet                   Remove only google-ads-dotnet client library"
  echo ""
  echo "  Examples:"
  echo "    $0                         (Uninstalls and deletes the entire Antigravity plugin directory)"
  echo "    $0 -y                      (Uninstalls plugin without confirmation prompt)"
  echo "    $0 --all                   (Removes all client libraries from the plugin)"
  echo "    $0 --java                  (Removes only the Java library from the plugin)"
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
  echo "Plugin client library removal complete."
  echo ""
  echo "Restart your Antigravity / agy host to apply changes."
  exit 0
fi

echo "This will uninstall the Google Ads API Developer Assistant plugin"
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

echo "Plugin uninstallation complete."
echo ""
echo "Restart your Antigravity / agy host to complete plugin uninstallation."
