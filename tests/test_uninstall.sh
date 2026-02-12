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

# Create mock gemini
cat > "${FAKE_HOME}/bin/gemini" <<EOF
#!/bin/bash
echo "MOCK: gemini \$*" >> "${TEST_TMP_DIR}/uninstall_log.txt"
EOF
chmod +x "${FAKE_HOME}/bin/gemini"

# 2. Setup "Project" in Mock Dir
cd "${FAKE_PROJECT}"
touch "some_file.txt"
mkdir "some_dir"

# --- Test Case 1: Run uninstall.sh with 'n' ---
echo "--- Running uninstall.sh with 'n' (Cancellation) ---"
if ! echo "n" | bash "${UNINSTALL_SCRIPT_PATH}"; then
    echo "FAIL: uninstall.sh failed on cancellation check"
    exit 1
fi

if [[ ! -d "${FAKE_PROJECT}" ]]; then
    echo "FAIL: project directory was deleted on cancellation"
    exit 1
fi
echo "PASS: Cancellation respected"

# --- Test Case 2: Run uninstall.sh with 'Y' ---
echo "--- Running uninstall.sh with 'Y' (Success) ---"
# We need to run it such that it can delete the directory it's "in"
# The script calls 'cd ${parent_dir}' before 'rm -rf'
if ! echo "Y" | bash "${UNINSTALL_SCRIPT_PATH}"; then
    echo "FAIL: uninstall.sh failed"
    exit 1
fi

# Check if directory deleted
if [[ -d "${FAKE_PROJECT}" ]]; then
    echo "FAIL: project directory still exists"
    exit 1
fi
echo "PASS: Directory removed"

# Check if gemini uninstall was called
if grep -q "gemini extensions uninstall google-ads-api-developer-assistant" "${TEST_TMP_DIR}/uninstall_log.txt"; then
    echo "PASS: gemini extensions uninstall called"
else
    echo "FAIL: gemini extensions uninstall NOT called"
    cat "${TEST_TMP_DIR}/uninstall_log.txt"
    exit 1
fi

echo "ALL BASH UNINSTALL TESTS PASSED"
