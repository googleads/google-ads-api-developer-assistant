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
if [[ ! -f "${AGY_PLUGIN_DIR}/config/api_version.txt" ]]; then
  echo "FAIL: config/api_version.txt missing in ${AGY_PLUGIN_DIR}"
  exit 1
fi
echo "PASS: Antigravity plugin successfully installed."

echo "Test 4: install.sh claude executes claude CLI marketplace add and install commands"
output=$("${PROJECT_ROOT}/install.sh" claude)
if ! echo "$output" | grep -q "plugin marketplace add"; then
  echo "FAIL: install.sh claude did not execute marketplace add"
  exit 1
fi
if ! echo "$output" | grep -q "plugin install google-ads-api-developer-assistant@google-ads-assistant-local"; then
  echo "FAIL: install.sh claude did not execute plugin install"
  exit 1
fi
echo "PASS: install.sh claude executed Claude Code marketplace commands."

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

echo "Test 8: update.sh claude updates Claude Code plugin in repository"
"${PROJECT_ROOT}/update.sh" claude
if [[ ! -f "${PROJECT_ROOT}/plugins/google-ads-api-developer-assistant/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in repository plugin after update"
  exit 1
fi
echo "PASS: update.sh claude executed successfully."

echo "Test 9: update.sh claude --php adds google-ads-php to repository plugin client_libs"
"${PROJECT_ROOT}/update.sh" claude --php
if [[ ! -d "${PROJECT_ROOT}/plugins/google-ads-api-developer-assistant/client_libs/google-ads-php" ]]; then
  echo "FAIL: google-ads-php missing from repository plugin client_libs"
  exit 1
fi
echo "PASS: update.sh claude --php added client library successfully."

echo "=== All Tests Passed Successfully! ==="
