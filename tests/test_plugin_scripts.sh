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

PLUGIN_DIR="${TEST_HOME}/.gemini/config/plugins/google-ads-api-developer-assistant"

echo "Test 1: install.sh --help does not require --type"
output=$("${PROJECT_ROOT}/install.sh" --help)
if echo "$output" | grep -qi "\--type"; then
  echo "FAIL: install.sh --help should not mention --type"
  exit 1
fi
echo "PASS: install.sh --help is clean."

echo "Test 2: uninstall.sh --help does not require --type"
output=$("${PROJECT_ROOT}/uninstall.sh" --help)
if echo "$output" | grep -qi "\--type"; then
  echo "FAIL: uninstall.sh --help should not mention --type"
  exit 1
fi
echo "PASS: uninstall.sh --help is clean."

echo "Test 3: update.sh --help does not require --type"
output=$("${PROJECT_ROOT}/update.sh" --help)
if echo "$output" | grep -qi "\--type"; then
  echo "FAIL: update.sh --help should not mention --type"
  exit 1
fi
echo "PASS: update.sh --help is clean."

echo "Test 4: install.sh installs plugin into ~/.gemini/config/plugins/google-ads-api-developer-assistant"
"${PROJECT_ROOT}/install.sh"
if [[ ! -d "${PLUGIN_DIR}" ]]; then
  echo "FAIL: Plugin directory was not created at ${PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in ${PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${PLUGIN_DIR}/config/api_version.txt" ]]; then
  echo "FAIL: config/api_version.txt missing in ${PLUGIN_DIR}"
  exit 1
fi
echo "PASS: Plugin successfully installed."

echo "Test 5: update.sh runs and preserves plugin configuration"
"${PROJECT_ROOT}/update.sh"
if [[ ! -f "${PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update"
  exit 1
fi
echo "PASS: update.sh executed successfully."

echo "Test 6: uninstall.sh --python removes google-ads-python from plugin client_libs"
mkdir -p "${PLUGIN_DIR}/client_libs/google-ads-python"
"${PROJECT_ROOT}/uninstall.sh" --python -y
if [[ -d "${PLUGIN_DIR}/client_libs/google-ads-python" ]]; then
  echo "FAIL: google-ads-python client library was not removed"
  exit 1
fi
if [[ ! -d "${PLUGIN_DIR}" ]]; then
  echo "FAIL: Plugin directory should still exist after removing a single client library"
  exit 1
fi
echo "PASS: Client library removal succeeded."

echo "Test 7: uninstall.sh -y deletes the entire plugin directory"
"${PROJECT_ROOT}/uninstall.sh" -y
if [[ -d "${PLUGIN_DIR}" ]]; then
  echo "FAIL: Plugin directory still exists after uninstallation"
  exit 1
fi
echo "PASS: Full uninstallation succeeded."

echo "=== All Tests Passed Successfully! ==="
