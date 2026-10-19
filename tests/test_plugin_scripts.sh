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
CLAUDE_MARKETPLACE_DIR="${TEST_HOME}/.claude/plugins/google-ads-assistant-local"
CLAUDE_PLUGIN_DIR="${CLAUDE_MARKETPLACE_DIR}/plugins/google-ads-api-developer-assistant"

# Create mock claude CLI in TEST_HOME/bin
mkdir -p "${TEST_HOME}/bin"
export PATH="${TEST_HOME}/bin:${PATH}"
cat << 'EOF' > "${TEST_HOME}/bin/claude"
#!/bin/bash
echo "[MOCK CLAUDE] Called with: $*"
exit 0
EOF
chmod +x "${TEST_HOME}/bin/claude"

echo "Test 1: install.sh requires type argument ('agy' or 'claude')"
if "${PROJECT_ROOT}/install.sh" 2>/dev/null; then
  echo "FAIL: install.sh without type argument should fail"
  exit 1
fi
echo "PASS: install.sh enforces required type argument."

echo "Test 2: install.sh --help displays options"
output=$("${PROJECT_ROOT}/install.sh" --help)
if ! echo "$output" | grep -qi "claude"; then
  echo "FAIL: install.sh --help should mention claude"
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
if [[ ! -f "${AGY_PLUGIN_DIR}/config/assistant_config" ]]; then
  echo "FAIL: config/assistant_config missing in ${AGY_PLUGIN_DIR}"
  exit 1
fi
echo "PASS: Antigravity plugin successfully installed."

echo "Test 4: install.sh claude installs standalone copy and executes claude CLI marketplace commands"
output=$("${PROJECT_ROOT}/install.sh" claude)
if ! echo "$output" | grep -q "plugin marketplace add ${CLAUDE_MARKETPLACE_DIR}"; then
  echo "FAIL: install.sh claude did not register standalone marketplace directory ${CLAUDE_MARKETPLACE_DIR}"
  exit 1
fi
if ! echo "$output" | grep -q "plugin install google-ads-api-developer-assistant@google-ads-assistant-local"; then
  echo "FAIL: install.sh claude did not execute plugin install"
  exit 1
fi
if [[ ! -f "${CLAUDE_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in standalone Claude plugin dir ${CLAUDE_PLUGIN_DIR}"
  exit 1
fi
if [[ ! -f "${CLAUDE_MARKETPLACE_DIR}/.claude-plugin/marketplace.json" ]]; then
  echo "FAIL: marketplace.json missing in ${CLAUDE_MARKETPLACE_DIR}/.claude-plugin"
  exit 1
fi
echo "PASS: install.sh claude installed standalone copy and executed Claude Code marketplace commands."

echo "Test 5: update.sh requires type argument ('agy' or 'claude')"
if "${PROJECT_ROOT}/update.sh" 2>/dev/null; then
  echo "FAIL: update.sh without type argument should fail"
  exit 1
fi
echo "PASS: update.sh enforces required type argument."

echo "Test 6: update.sh --help displays agy and claude options"
output=$("${PROJECT_ROOT}/update.sh" --help)
if ! echo "$output" | grep -qi "claude"; then
  echo "FAIL: update.sh --help should mention claude"
  exit 1
fi
echo "PASS: update.sh --help is valid."

echo "Test 7: update.sh agy updates Antigravity plugin"
"${PROJECT_ROOT}/update.sh" agy
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update in agy"
  exit 1
fi
echo "PASS: update.sh agy executed successfully."

echo "Test 8: update.sh claude updates standalone Claude Code plugin"
"${PROJECT_ROOT}/update.sh" claude
if [[ ! -f "${CLAUDE_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in standalone Claude plugin after update"
  exit 1
fi
echo "PASS: update.sh claude executed successfully."

echo "Test 9: update.sh claude --php adds google-ads-php to standalone Claude plugin client_libs"
"${PROJECT_ROOT}/update.sh" claude --php
if [[ ! -d "${CLAUDE_PLUGIN_DIR}/client_libs/google-ads-php" ]]; then
  echo "FAIL: google-ads-php missing from standalone Claude plugin client_libs"
  exit 1
fi
echo "PASS: update.sh claude --php added client library successfully."

echo "Test 10: install.sh agy rejects --link option (always installs standalone copy)"
if "${PROJECT_ROOT}/install.sh" agy --link 2>/dev/null; then
  echo "FAIL: install.sh agy --link should fail because symlinking to repo is disabled"
  exit 1
fi
if [[ -L "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: ${AGY_PLUGIN_DIR} must not be a symbolic link"
  exit 1
fi
echo "PASS: install.sh agy rejects --link and enforces standalone copy."

echo "Test 11: update.sh agy migrates any legacy symbolic link to a standalone directory copy"
rm -rf "${AGY_PLUGIN_DIR}"
ln -sfn "${PROJECT_ROOT}/plugins/google-ads-api-developer-assistant" "${AGY_PLUGIN_DIR}"
"${PROJECT_ROOT}/update.sh" agy
if [[ -L "${AGY_PLUGIN_DIR}" || ! -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: update.sh agy did not replace legacy symlink at ${AGY_PLUGIN_DIR} with a real directory"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in migrated standalone directory ${AGY_PLUGIN_DIR}"
  exit 1
fi
echo "PASS: update.sh agy migrated legacy symbolic link to standalone copy."

echo "Test 12: global script execution from arbitrary directory using GOOGLE_ADS_ASSISTANT_DIR"
export GOOGLE_ADS_ASSISTANT_DIR="${AGY_PLUGIN_DIR}"
version_output=$(cd "${TEST_HOME}" && python3 "${GOOGLE_ADS_ASSISTANT_DIR}/skills/ext-version/scripts/get_extension_version.py")
if [[ "${version_output}" != "4.1.0" ]]; then
  echo "FAIL: expected version 4.1.0, got: '${version_output}'"
  exit 1
fi
echo "PASS: global script execution succeeded from outside directory."

echo "=== All Tests Passed Successfully! ==="
