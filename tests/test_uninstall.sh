#!/bin/bash
set -u

# --- Test Setup ---
TEST_TMP_DIR=$(mktemp -d)
UNINSTALL_SCRIPT_PATH="$(cd "$(dirname "$0")/.." && pwd)/uninstall.sh"

echo "Running tests in ${TEST_TMP_DIR}"

# 1. Mock Environment
FAKE_HOME=$(mktemp -d)
# We create a fake project directory inside another temp dir to simulate deletion
MOCK_PARENT_DIR=$(mktemp -d)
FAKE_PROJECT="${MOCK_PARENT_DIR}/google-ads-api-developer-assistant"
mkdir -p "${FAKE_PROJECT}"

echo "FAKE_HOME: ${FAKE_HOME}"
echo "FAKE_PROJECT: ${FAKE_PROJECT}"

export HOME="${FAKE_HOME}"
mkdir -p "${FAKE_HOME}/bin"
export PATH="${FAKE_HOME}/bin:${PATH}"

# Cleanup function
cleanup() {
    rm -rf "${TEST_TMP_DIR}"
    rm -rf "${FAKE_HOME}"
    rm -rf "${MOCK_PARENT_DIR}"
}
trap cleanup EXIT

# Create mock git
cat > "${FAKE_HOME}/bin/git" <<EOF
#!/bin/bash
if [[ "\$1" == "rev-parse" ]]; then
    # Return the temp dir as the project root
    echo "${FAKE_PROJECT}"
else
    echo "Mock git: command \$* ignored"
fi
EOF
chmod +x "${FAKE_HOME}/bin/git"

# 2. Setup "Project" in Mock Dir
cd "${FAKE_PROJECT}"
touch "some_file.txt"
mkdir "some_dir"

# --- Test Case 1: Run uninstall.sh without --type (Should Fail) ---
echo "--- Running uninstall.sh without --type (Expected Failure) ---"
if bash "${UNINSTALL_SCRIPT_PATH}" 2>/dev/null; then
    echo "FAIL: uninstall.sh should have failed when missing --type"
    exit 1
fi

# --- Test Case 2: Run uninstall.sh with invalid --type (Should Fail) ---
echo "--- Running uninstall.sh with invalid --type (Expected Failure) ---"
if bash "${UNINSTALL_SCRIPT_PATH}" --type invalid 2>/dev/null; then
    echo "FAIL: uninstall.sh should have failed with invalid --type"
    exit 1
fi

# --- Test Case 3: Run uninstall.sh --type project with 'n' ---
echo "--- Running uninstall.sh --type project with 'n' (Cancellation) ---"
if ! echo "n" | bash "${UNINSTALL_SCRIPT_PATH}" --type project; then
    echo "FAIL: uninstall.sh failed on cancellation check"
    exit 1
fi

if [[ ! -d "${FAKE_PROJECT}" ]]; then
    echo "FAIL: project directory was deleted on cancellation"
    exit 1
fi
echo "PASS: Cancellation respected"

# --- Test Case 4: Run uninstall.sh --type project --java (Partial Removal) ---
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-java"
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-python"

echo "--- Running uninstall.sh --type project --java (Partial Removal) ---"
if ! bash "${UNINSTALL_SCRIPT_PATH}" --type project --java; then
    echo "FAIL: uninstall.sh failed with --type project --java"
    exit 1
fi

if [[ -d "${FAKE_PROJECT}/client_libs/google-ads-java" ]]; then
    echo "FAIL: google-ads-java was not removed from project"
    exit 1
fi

if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-python" ]]; then
    echo "FAIL: google-ads-python was unexpectedly removed from project"
    exit 1
fi
echo "PASS: Project library partial removal successful"

# --- Test Case 5: Run uninstall.sh --type project --all (Remove All Client Libs) ---
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-java"
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-python"
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-php"

echo "--- Running uninstall.sh --type project --all (Remove All Client Libs) ---"
if ! bash "${UNINSTALL_SCRIPT_PATH}" --type project --all; then
    echo "FAIL: uninstall.sh failed with --type project --all"
    exit 1
fi

for l in java python php; do
    if [[ -d "${FAKE_PROJECT}/client_libs/google-ads-${l}" ]]; then
        echo "FAIL: google-ads-${l} was not removed by --all"
        exit 1
    fi
done
echo "PASS: Project --all library removal successful"

# --- Test Case 6: Run uninstall.sh --type project --clean (Clean Environment) ---
mkdir -p "${FAKE_PROJECT}/.venv"
mkdir -p "${FAKE_PROJECT}/config"
echo "v25" > "${FAKE_PROJECT}/config/api_version.txt"

echo "--- Running uninstall.sh --type project --clean ---"
if ! bash "${UNINSTALL_SCRIPT_PATH}" --type project --clean; then
    echo "FAIL: uninstall.sh failed with --type project --clean"
    exit 1
fi

if [[ -d "${FAKE_PROJECT}/.venv" ]]; then
    echo "FAIL: .venv directory still exists after --clean"
    exit 1
fi
if [[ -f "${FAKE_PROJECT}/config/api_version.txt" ]]; then
    echo "FAIL: config/api_version.txt still exists after --clean"
    exit 1
fi
if [[ ! -d "${FAKE_PROJECT}" ]]; then
    echo "FAIL: project directory was deleted during --clean"
    exit 1
fi
echo "PASS: Project --clean successful"

# --- Test Case 7: Run uninstall.sh --type plugin with cancellation and partial removal ---
FAKE_PLUGIN_DIR="${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin"
mkdir -p "${FAKE_PLUGIN_DIR}/client_libs/google-ads-java"
mkdir -p "${FAKE_PLUGIN_DIR}/client_libs/google-ads-python"
touch "${FAKE_PLUGIN_DIR}/plugin.json"

echo "--- Running uninstall.sh --type plugin with 'n' (Cancellation) ---"
if ! echo "n" | bash "${UNINSTALL_SCRIPT_PATH}" --type plugin; then
    echo "FAIL: uninstall.sh failed on plugin cancellation check"
    exit 1
fi

if [[ ! -d "${FAKE_PLUGIN_DIR}" ]]; then
    echo "FAIL: plugin directory was deleted on cancellation"
    exit 1
fi
echo "PASS: Plugin cancellation respected"

echo "--- Running uninstall.sh --type plugin --java (Partial Removal) ---"
if ! bash "${UNINSTALL_SCRIPT_PATH}" --type plugin --java; then
    echo "FAIL: uninstall.sh failed with --type plugin --java"
    exit 1
fi

if [[ -d "${FAKE_PLUGIN_DIR}/client_libs/google-ads-java" ]]; then
    echo "FAIL: google-ads-java was not removed from plugin"
    exit 1
fi

if [[ ! -d "${FAKE_PLUGIN_DIR}/client_libs/google-ads-python" ]]; then
    echo "FAIL: google-ads-python was unexpectedly removed from plugin"
    exit 1
fi
echo "PASS: Plugin library partial removal successful"

# --- Test Case 8: Run uninstall.sh --type plugin --yes (Full Removal) ---
echo "--- Running uninstall.sh --type plugin with --yes (Success) ---"
if ! bash "${UNINSTALL_SCRIPT_PATH}" --type plugin --yes; then
    echo "FAIL: uninstall.sh failed with --type plugin --yes"
    exit 1
fi

if [[ -d "${FAKE_PLUGIN_DIR}" ]]; then
    echo "FAIL: plugin directory still exists"
    exit 1
fi
echo "PASS: Plugin directory removed"

# --- Test Case 9: Run uninstall.sh --type project with 'Y' (Full Removal & Project Config Cleanup) ---
mkdir -p "${FAKE_HOME}/.gemini/config/projects"
echo "{\"name\": \"${FAKE_PROJECT}\"}" > "${FAKE_HOME}/.gemini/config/projects/test_proj.json"

echo "--- Running uninstall.sh --type project with 'Y' (Success) ---"
if ! echo "Y" | bash "${UNINSTALL_SCRIPT_PATH}" --type project; then
    echo "FAIL: uninstall.sh failed"
    exit 1
fi

# Check if directory deleted
if [[ -d "${FAKE_PROJECT}" ]]; then
    echo "FAIL: project directory still exists"
    exit 1
fi

# Check if project config was cleaned up
if [[ -f "${FAKE_HOME}/.gemini/config/projects/test_proj.json" ]]; then
    echo "FAIL: project configuration was not cleaned up from ~/.gemini/config/projects/"
    exit 1
fi
echo "PASS: Project directory and project config removed"

echo "ALL BASH UNINSTALL TESTS PASSED"
