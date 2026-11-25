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

assert_no_claude_only_files() {
  local plugin_dir="$1"
  local ctx="$2"
  for rel in .claude-plugin .mcp.json .mcp.json.disabled hooks commands; do
    if [[ -e "${plugin_dir}/${rel}" || -L "${plugin_dir}/${rel}" ]]; then
      echo "FAIL: Claude-only item '${rel}' should not exist in agy plugin dir (${ctx}): ${plugin_dir}/${rel}"
      exit 1
    fi
  done
}

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
assert_no_claude_only_files "${AGY_PLUGIN_DIR}" "install agy"
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

echo "Test 7: update.sh agy --no-git-pull updates Antigravity plugin and preserves allow_tier1_financial_mutates"
sed 's/^allow_tier1_financial_mutates = false$/allow_tier1_financial_mutates = true/' "${AGY_PLUGIN_DIR}/config/assistant_config" > "${AGY_PLUGIN_DIR}/config/assistant_config.tmp"
mv "${AGY_PLUGIN_DIR}/config/assistant_config.tmp" "${AGY_PLUGIN_DIR}/config/assistant_config"
if ! grep -q '^allow_tier1_financial_mutates = true$' "${AGY_PLUGIN_DIR}/config/assistant_config"; then
  echo "allow_tier1_financial_mutates = true" >> "${AGY_PLUGIN_DIR}/config/assistant_config"
fi
echo 'custom_operator_note = "keep-me"' >> "${AGY_PLUGIN_DIR}/config/assistant_config"
"${PROJECT_ROOT}/update.sh" agy --no-git-pull
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing after update in agy"
  exit 1
fi
if ! grep -q '^allow_tier1_financial_mutates = true$' "${AGY_PLUGIN_DIR}/config/assistant_config"; then
  echo "FAIL: update.sh clobbered allow_tier1_financial_mutates = true in assistant_config"
  exit 1
fi
if ! grep -q '^custom_operator_note = "keep-me"$' "${AGY_PLUGIN_DIR}/config/assistant_config"; then
  echo "FAIL: update.sh clobbered custom TOML keys in assistant_config"
  exit 1
fi
assert_no_claude_only_files "${AGY_PLUGIN_DIR}" "update agy"
echo "PASS: update.sh agy preserved allow_tier1_financial_mutates and custom keys."

echo "Test 8: update.sh claude --no-git-pull updates standalone Claude Code plugin including dotfiles (.claude-plugin, .mcp.json)"
echo '{"stale": true}' > "${CLAUDE_PLUGIN_DIR}/.mcp.json"
echo '{"stale": true}' > "${CLAUDE_PLUGIN_DIR}/.claude-plugin/plugin.json"
"${PROJECT_ROOT}/update.sh" claude --no-git-pull
if [[ ! -f "${CLAUDE_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in standalone Claude plugin after update"
  exit 1
fi
if grep -q '"stale"' "${CLAUDE_PLUGIN_DIR}/.mcp.json"; then
  echo "FAIL: update.sh claude did not sync hidden .mcp.json file"
  exit 1
fi
if grep -q '"stale"' "${CLAUDE_PLUGIN_DIR}/.claude-plugin/plugin.json"; then
  echo "FAIL: update.sh claude did not sync hidden .claude-plugin/ directory"
  exit 1
fi
echo "PASS: update.sh claude synced dotfiles (.claude-plugin and .mcp.json)."

echo "Test 9: update.sh claude --no-git-pull --php adds google-ads-php when present or skips offline pull"
if [[ -d "${PROJECT_ROOT}/plugins/google-ads-api-developer-assistant/client_libs/google-ads-php" ]]; then
  "${PROJECT_ROOT}/update.sh" claude --no-git-pull --php
  if [[ ! -d "${CLAUDE_PLUGIN_DIR}/client_libs/google-ads-php" ]]; then
    echo "FAIL: google-ads-php missing from standalone Claude plugin client_libs"
    exit 1
  fi
fi
echo "PASS: update.sh claude --no-git-pull client_libs handling verified."

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

echo "Test 11: update.sh agy --no-git-pull migrates any legacy symbolic link to a standalone directory copy"
rm -rf "${AGY_PLUGIN_DIR}"
ln -sfn "${PROJECT_ROOT}/plugins/google-ads-api-developer-assistant" "${AGY_PLUGIN_DIR}"
"${PROJECT_ROOT}/update.sh" agy --no-git-pull
if [[ -L "${AGY_PLUGIN_DIR}" || ! -d "${AGY_PLUGIN_DIR}" ]]; then
  echo "FAIL: update.sh agy did not replace legacy symlink at ${AGY_PLUGIN_DIR} with a real directory"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json missing in migrated standalone directory ${AGY_PLUGIN_DIR}"
  exit 1
fi
assert_no_claude_only_files "${AGY_PLUGIN_DIR}" "symlink migration"
echo "PASS: update.sh agy migrated legacy symbolic link to standalone copy."

echo "Test 12: global script execution from arbitrary directory using GOOGLE_ADS_ASSISTANT_DIR"
export GOOGLE_ADS_ASSISTANT_DIR="${AGY_PLUGIN_DIR}"
version_output=$(cd "${TEST_HOME}" && python3 "${GOOGLE_ADS_ASSISTANT_DIR}/skills/ext-version/scripts/get_extension_version.py")
if [[ "${version_output}" != "4.1.0" ]]; then
  echo "FAIL: expected version 4.1.0, got: '${version_output}'"
  exit 1
fi
echo "PASS: global script execution succeeded from outside directory."

echo "Test 13: plugin.sh disable, status, test, is-enabled, and enable"
"${PROJECT_ROOT}/plugin.sh" disable agy >/dev/null
if "${PROJECT_ROOT}/plugin.sh" is-enabled --config-dir "${AGY_PLUGIN_DIR}/config" --quiet; then
  echo "FAIL: plugin.sh is-enabled should exit 1 when disabled"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json.disabled" || -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: plugin.json was not renamed to plugin.json.disabled in ${AGY_PLUGIN_DIR}"
  exit 1
fi
"${PROJECT_ROOT}/plugin.sh" test --config-dir "${AGY_PLUGIN_DIR}/config" --expect disabled >/dev/null

# Verify update.sh preserves disabled state unless --enable is specified and leaves no Claude-only artifacts
"${PROJECT_ROOT}/update.sh" agy --no-git-pull >/dev/null
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json.disabled" || -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: update.sh did not preserve disabled state in ${AGY_PLUGIN_DIR}"
  exit 1
fi
assert_no_claude_only_files "${AGY_PLUGIN_DIR}" "update agy while disabled"

# Verify install.sh agy --disable also leaves no Claude-only artifacts (including .mcp.json.disabled)
"${PROJECT_ROOT}/install.sh" agy --disable >/dev/null
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json.disabled" || -f "${AGY_PLUGIN_DIR}/plugin.json" ]]; then
  echo "FAIL: install.sh agy --disable did not install in disabled state in ${AGY_PLUGIN_DIR}"
  exit 1
fi
assert_no_claude_only_files "${AGY_PLUGIN_DIR}" "install agy --disable"

# Re-enable and verify
"${PROJECT_ROOT}/plugin.sh" enable agy >/dev/null
if ! "${PROJECT_ROOT}/plugin.sh" is-enabled --config-dir "${AGY_PLUGIN_DIR}/config" --quiet; then
  echo "FAIL: plugin.sh is-enabled should exit 0 when enabled"
  exit 1
fi
if [[ ! -f "${AGY_PLUGIN_DIR}/plugin.json" || -f "${AGY_PLUGIN_DIR}/plugin.json.disabled" ]]; then
  echo "FAIL: plugin.json was not restored in ${AGY_PLUGIN_DIR}"
  exit 1
fi
"${PROJECT_ROOT}/plugin.sh" test --config-dir "${AGY_PLUGIN_DIR}/config" --expect enabled >/dev/null
echo "PASS: plugin.sh disable, status, test, is-enabled, and enable verified."

echo "Test 14: installed update.sh in plugin directory runs offline from an arbitrary directory outside the git repo"
if [[ ! -x "${AGY_PLUGIN_DIR}/update.sh" ]]; then
  echo "FAIL: update.sh was not installed or not executable in ${AGY_PLUGIN_DIR}"
  exit 1
fi
(cd "${TEST_HOME}" && "${AGY_PLUGIN_DIR}/update.sh" agy --no-git-pull >/dev/null)
echo "PASS: installed update.sh executed successfully from outside the git repository."

echo "=== All Tests Passed Successfully! ==="

