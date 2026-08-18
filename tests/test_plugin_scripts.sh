#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=== Running Plugin Scripts Test Suite ==="

# Set up temporary isolated home
TEST_HOME="$(mktemp -d)"
export HOME="${TEST_HOME}"
export ANTIGRAVITY_APP_DIR="${TEST_HOME}/.gemini"

cleanup() {
  rm -rf "${TEST_HOME}"
}
trap cleanup EXIT

AGY_PLUGIN_DIR="${TEST_HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"

echo "Test 1: install.sh --help displays options"
output=$("${PROJECT_ROOT}/install.sh" --help)
if ! echo "$output" | grep -qi "Antigravity"; then
  echo "FAIL: install.sh --help should mention Antigravity"
  exit 1
fi
echo "PASS: install.sh --help is valid."

echo "Test 2: install.sh installs plugin into ~/.gemini/config/plugins/google-ads-api-developer-assistant"
"${PROJECT_ROOT}/install.sh"
if [[ ! -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: Antigravity plugin directory was not created at ${AGY_PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in ${AGY_PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/config/api_version.txt" ]]; then
  echo "FAIL: config/api_version.txt missing in ${AGY_PLUGIN_DIR}"
  exit 1
fi
echo "PASS: Antigravity plugin successfully installed."

echo "Test 3: update.sh updates Antigravity plugin"
"${PROJECT_ROOT}/update.sh"
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update in agy"
  exit 1
fi
echo "PASS: update.sh executed successfully."

echo "Test 4: uninstall.sh --python removes google-ads-python from plugin client_libs"
mkdir -p "${AGY_PLUGIN_DIR}/client_libs/google-ads-python"
"${PROJECT_ROOT}/uninstall.sh" --python -y
if [[ -d "${AGY_PLUGIN_DIR}/client_libs/google-ads-python" ]]; then
  echo "FAIL: google-ads-python client library was not removed from agy"
  exit 1
fi
if [[ ! -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: agy plugin directory should still exist after removing a single client library"
  exit 1
fi
echo "PASS: Client library removal succeeded for agy."

echo "Test 5: uninstall.sh -y deletes the Antigravity plugin directory"
"${PROJECT_ROOT}/uninstall.sh" -y
if [[ -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: agy plugin directory still exists after uninstallation"
  exit 1
fi
echo "PASS: Antigravity plugin uninstallation succeeded."

echo "=== All Tests Passed Successfully! ==="
