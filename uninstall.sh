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
#   It supports removing either the standalone project directory or the installed plugin.

set -eu

# Function to print errors to stderr
err() {
  echo "[$(date +'%Y-%m-%dT%H:%M:%S%z')]: $*" >&2
}

# --- Defaults ---
UNINSTALL_TYPE=""
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
  echo ""
  echo "  Examples:"
  echo "    $0 --type project          (Uninstalls and deletes the project directory)"
  echo "    $0 --type plugin           (Uninstalls and deletes the plugin directory)"
  echo ""
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
