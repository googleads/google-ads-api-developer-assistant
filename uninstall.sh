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
#   This script uninstalls the Google Ads API Developer Assistant extension
#   and removes the local project directory.

set -eu

# Determine project root
if ! PROJECT_DIR_ABS=$(git rev-parse --show-toplevel 2>/dev/null); then
  echo "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
  exit 1
fi

echo "This will uninstall the Google Ads API Developer Assistant extension"
echo "and DELETE the entire directory: ${PROJECT_DIR_ABS}"
read -p "Are you sure you want to proceed? (Y/n): " confirm

if [[ ! "${confirm}" =~ ^[Yy]$ ]]; then
  echo "Uninstallation cancelled."
  exit 0
fi

if command -v gemini &> /dev/null; then
  echo "Uninstalling Gemini extension..."
  gemini extensions uninstall "google-ads-api-developer-assistant" || echo "WARN: Extension was not registered or failed to uninstall. Continuing..."
else
  echo "WARN: 'gemini' command not found. Skipping extension uninstallation."
fi

echo "Removing project directory: ${PROJECT_DIR_ABS}..."
# Use a temporary script to remove the directory because the current script is inside it
# Actually on Linux we can usually delete the script while it's running, but to be safe:
parent_dir=$(dirname "${PROJECT_DIR_ABS}")
project_name=$(basename "${PROJECT_DIR_ABS}")

cd "${parent_dir}"
rm -rf "${project_name}"

echo "Uninstallation complete."
