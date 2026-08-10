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

# --- Defaults ---
UNINSTALL_TYPE=""
UNINSTALL_PYTHON=false
UNINSTALL_PHP=false
UNINSTALL_RUBY=false
UNINSTALL_JAVA=false
UNINSTALL_DOTNET=false
ANY_SELECTED=false
AUTO_CONFIRM=false

# --- Help Function ---
usage() {
  echo "Usage: $0 --type <project|plugin> [OPTIONS]"
  echo "  Uninstalls the Google Ads API Developer Assistant project or plugin."
  echo ""
  echo "  Required Arguments:"
  echo "    -t, --type TYPE            Uninstallation type: 'project' or 'plugin'"
  echo ""
  echo "  Options:"
  echo "    -h, --help                 Show this help message and exit"
  echo "    -y, --yes                  Skip confirmation prompt"
  echo "    --python                   Remove only google-ads-python client library"
  echo "    --php                      Remove only google-ads-php client library"
  echo "    --ruby                     Remove only google-ads-ruby client library"
  echo "    --java                     Remove only google-ads-java client library"
  echo "    --dotnet                   Remove only google-ads-dotnet client library"
  echo ""
  echo "  Examples:"
  echo "    $0 --type project          (Uninstalls and deletes the entire project directory)"
  echo "    $0 --type project --java   (Removes only the Java library from the project)"
  echo "    $0 --type plugin           (Uninstalls and deletes the entire plugin directory)"
  echo "    $0 --type plugin --java    (Removes only the Java library from the plugin)"
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
    -t|--type)
      if [[ $# -lt 2 ]]; then
        err "ERROR: --type requires an argument ('project' or 'plugin')."
        usage
        exit 1
      fi
      UNINSTALL_TYPE=$(echo "$2" | tr '[:upper:]' '[:lower:]')
      shift 2
      ;;
    --type=*)
      UNINSTALL_TYPE=$(echo "${1#*=}" | tr '[:upper:]' '[:lower:]')
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

# --- Validate Required Type Argument ---
if [[ -z "${UNINSTALL_TYPE}" ]]; then
  err "ERROR: Missing required argument: --type <project|plugin>"
  usage
  exit 1
fi

if [[ "${UNINSTALL_TYPE}" != "project" && "${UNINSTALL_TYPE}" != "plugin" ]]; then
  err "ERROR: Invalid uninstallation type '${UNINSTALL_TYPE}'. Must be 'project' or 'plugin'."
  usage
  exit 1
fi

# --- Plugin Uninstallation Branch ---
if [[ "${UNINSTALL_TYPE}" == "plugin" ]]; then
  PLUGIN_TARGET_DIR="${HOME}/.gemini/config/plugins/google_ads_assistant_plugin"

  if [[ ! -d "${PLUGIN_TARGET_DIR}" ]]; then
    echo "Plugin directory '${PLUGIN_TARGET_DIR}' does not exist. Nothing to uninstall."
    exit 0
  fi

  # If specific client libraries were requested to be removed
  if [[ "${ANY_SELECTED}" == "true" ]]; then
    for lang in python php ruby java dotnet; do
      if is_enabled "$lang"; then
        repo_name=$(get_repo_name "$lang")
        lib_path="${PLUGIN_TARGET_DIR}/client_libs/${repo_name}"
        if [[ -d "${lib_path}" ]]; then
          echo "Removing ${repo_name} from ${PLUGIN_TARGET_DIR}/client_libs/..."
          rm -rf "${lib_path}"
          echo "Successfully removed ${repo_name}."
        else
          echo "Library ${repo_name} not found in ${PLUGIN_TARGET_DIR}/client_libs/."
        fi
      fi
    done
    echo "Plugin client library removal complete."
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

  echo "Plugin uninstallation complete."
  exit 0
fi

# --- Project Uninstallation Branch ---
# Determine project root
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  err "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
fi

# If specific client libraries were requested to be removed
if [[ "${ANY_SELECTED}" == "true" ]]; then
  for lang in python php ruby java dotnet; do
    if is_enabled "$lang"; then
      repo_name=$(get_repo_name "$lang")
      lib_path="${PROJECT_DIR_ABS}/client_libs/${repo_name}"
      if [[ -d "${lib_path}" ]]; then
        echo "Removing ${repo_name} from ${PROJECT_DIR_ABS}/client_libs/..."
        rm -rf "${lib_path}"
        echo "Successfully removed ${repo_name}."
      else
        echo "Library ${repo_name} not found in ${PROJECT_DIR_ABS}/client_libs/."
      fi
    fi
  done
  echo "Project client library removal complete."
  exit 0
fi

echo "This will uninstall the Google Ads API Developer Assistant project"
echo "and DELETE the entire directory: ${PROJECT_DIR_ABS}"

if [[ "${AUTO_CONFIRM}" != "true" ]]; then
  read -p "Are you sure you want to proceed? (Y/n): " confirm
  if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
  fi
fi

echo "Removing project directory: ${PROJECT_DIR_ABS}..."
parent_dir=$(dirname "${PROJECT_DIR_ABS}")
project_name=$(basename "${PROJECT_DIR_ABS}")

cd "${parent_dir}"
rm -rf "${project_name}"

echo "Project uninstallation complete."
