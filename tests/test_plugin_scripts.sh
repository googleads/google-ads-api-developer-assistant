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
CLAUDE_PLUGIN_DIR="${TEST_HOME}/.claude/plugins/marketplace/google-ads-api-developer-assistant"

echo "Test 1: install.sh requires target argument ('agy' or 'claudecode')"
if "${PROJECT_ROOT}/install.sh" 2>/dev/null; then
  echo "FAIL: install.sh without target should fail"
  exit 1
fi
echo "PASS: install.sh enforces required target argument."

echo "Test 2: install.sh --help displays agy and claudecode options"
output=$("${PROJECT_ROOT}/install.sh" --help)
if ! echo "$output" | grep -qi "claudecode"; then
  echo "FAIL: install.sh --help should mention claudecode"
  exit 1
fi
echo "PASS: install.sh --help is valid."

echo "Test 3: install.sh agy installs plugin into ~/.gemini/config/plugins/google-ads-api-developer-assistant"
"${PROJECT_ROOT}/install.sh" agy
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

echo "Test 4: install.sh claudecode installs plugin into OS-specific Claude Code plugins directory"
"${PROJECT_ROOT}/install.sh" claudecode
if [[ ! -d "${CLAUDE_PLUGIN_DIR}" ]]; then
  echo "FAIL: Claude Code plugin directory was not created at ${CLAUDE_PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${CLAUDE_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in ${CLAUDE_PLUGIN_DIR}"
  exit 1
fi
echo "PASS: Claude Code plugin successfully installed."

echo "Test 5: update.sh agy updates Antigravity plugin"
"${PROJECT_ROOT}/update.sh" agy
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update in agy"
  exit 1
fi
echo "PASS: update.sh agy executed successfully."

echo "Test 6: update.sh claudecode updates Claude Code plugin"
"${PROJECT_ROOT}/update.sh" claudecode
if [[ ! -f "${CLAUDE_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update in claudecode"
  exit 1
fi
echo "PASS: update.sh claudecode executed successfully."

echo "Test 7: uninstall.sh agy --python removes google-ads-python from agy plugin client_libs"
mkdir -p "${AGY_PLUGIN_DIR}/client_libs/google-ads-python"
"${PROJECT_ROOT}/uninstall.sh" agy --python -y
if [[ -d "${AGY_PLUGIN_DIR}/client_libs/google-ads-python" ]]; then
  echo "FAIL: google-ads-python client library was not removed from agy"
  exit 1
fi
if [[ ! -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: agy plugin directory should still exist after removing a single client library"
  exit 1
fi
echo "PASS: Client library removal succeeded for agy."

echo "Test 8: uninstall.sh agy -y deletes the Antigravity plugin directory"
"${PROJECT_ROOT}/uninstall.sh" agy -y
if [[ -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: agy plugin directory still exists after uninstallation"
  exit 1
fi
echo "PASS: Antigravity plugin uninstallation succeeded."

echo "Test 9: uninstall.sh claudecode -y deletes the Claude Code plugin directory"
"${PROJECT_ROOT}/uninstall.sh" claudecode -y
if [[ -d "${CLAUDE_PLUGIN_DIR}" ]]; then
  echo "FAIL: claudecode plugin directory still exists after uninstallation"
  exit 1
fi
echo "PASS: Claude Code plugin uninstallation succeeded."

echo "=== All Tests Passed Successfully! ==="
