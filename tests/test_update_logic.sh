#!/bin/bash
set -u

# --- Test Update Logic ---
TEST_TMP_DIR=$(mktemp -d)
UPDATE_SCRIPT_PATH="$(cd "$(dirname "$0")/.." && pwd)/update.sh"

echo "Running tests in ${TEST_TMP_DIR}"

# Cleanup function
cleanup() {
    rm -rf "${TEST_TMP_DIR}"
}
trap cleanup EXIT

# 1. Mock Environment
FAKE_HOME=$(mktemp -d)
FAKE_PROJECT=$(mktemp -d)
echo "FAKE_HOME: ${FAKE_HOME}"
echo "FAKE_PROJECT: ${FAKE_PROJECT}"

export HOME="${FAKE_HOME}"
mkdir -p "${FAKE_HOME}/bin"
export PATH="${FAKE_HOME}/bin:${PATH}"

# Cleanup function (updated)
cleanup() {
    rm -rf "${TEST_TMP_DIR}"
    rm -rf "${FAKE_HOME}"
    rm -rf "${FAKE_PROJECT}"
}
trap cleanup EXIT

# Create mock git
cat > "${FAKE_HOME}/bin/git" <<EOF
#!/bin/bash
if [[ "\$1" == "rev-parse" ]]; then
    # Return the temp dir as the project root
    echo "${FAKE_PROJECT}"
elif [[ "\$1" == "pull" ]]; then
    echo "Mock pull successful"
    # Simulate update by modifying files ONLY IF we are meant to simulate a repo update?
    # update.sh pulls. If we want to test merging, we need 'git pull' to seemingly update the file.
    # But since we can't easily make 'git pull' actually update a file in this simple mock without a real repo,
    # we might need to rely on the fact that update.sh backs up BEFORE pulling.
    # Wait, update.sh backs up, then pulls, then merges.
    # If 'git pull' doesn't change anything, the merge might be trivial.
    # We want to simulate 'git pull' CHANGING the file to the REPO version.
    
    # Check CWD to verify provided settings.json vs others?
    # For now, let's just create the "repo" version of files here if they exist
    if [[ -f ".gemini/settings.json" ]]; then
         # Simulate repo having new values
         echo '{"repo_setting": true, "common_setting": "repo_value", "context": {"includeDirectories": []}}' > ".gemini/settings.json"
    fi
    # We don't touch customer_id.txt in repo usually, or maybe we do?
    # If repo has customer_id.txt, it might overwrite.
    if [[ -f "customer_id.txt" ]]; then
         echo "REPO_CUSTOMER_ID" > "customer_id.txt"
    fi
elif [[ "\$1" == "ls-files" ]]; then
    exit 0 # everything matches for now
elif [[ "\$1" == "checkout" ]]; then
    echo "Mock checkout \$2"
    # Actually restore the file to "HEAD" state?
    # logic: if git ls-files ...; then git checkout ...; fi
    # We can just ignore checkout for this test as we want to test the MERGE/RESTORE logic primarily.
else
    echo "Mock git: command \$* ignored"
fi
EOF
chmod +x "${FAKE_HOME}/bin/git"

# Create mock jq if not present
if ! command -v jq &> /dev/null; then
    echo "FAIL: real jq is required for this test"
    exit 1
fi

# 2. Setup "Project" in Temp Dir
mkdir -p "${FAKE_PROJECT}/.gemini"
SETTINGS_JSON="${FAKE_PROJECT}/.gemini/settings.json"
CUSTOMER_ID_FILE="${FAKE_PROJECT}/customer_id.txt"

# Initial "User" State
echo '{"user_setting": true, "common_setting": "user_value", "context": {"includeDirectories": []}}' > "${SETTINGS_JSON}"
echo "USER_CUSTOMER_ID" > "${CUSTOMER_ID_FILE}"

echo "Initial settings:"
cat "${SETTINGS_JSON}"
echo "Initial customer_id:"
cat "${CUSTOMER_ID_FILE}"

# 3. Run update.sh from within FAKE_PROJECT (update.sh expects to be in repo)
cd "${FAKE_PROJECT}"
echo "--- Running update.sh ---"
if ! bash "${UPDATE_SCRIPT_PATH}"; then
    echo "FAIL: update.sh failed"
    exit 1
fi

# 4. Verify Results
echo "Final settings:"
cat "${SETTINGS_JSON}"
echo "Final customer_id:"
cat "${CUSTOMER_ID_FILE}"

# Verify Settings
USER_VAL=$(jq -r .user_setting "${SETTINGS_JSON}")
REPO_VAL=$(jq -r .repo_setting "${SETTINGS_JSON}")
COMMON_VAL=$(jq -r .common_setting "${SETTINGS_JSON}")

if [[ "$USER_VAL" == "true" ]] && [[ "$REPO_VAL" == "true" ]] && [[ "$COMMON_VAL" == "user_value" ]]; then
    echo "PASS: Settings merged correctly"
else
    echo "FAIL: Settings merge incorrect"
    exit 1
fi

# Verify Customer ID
CID_VAL=$(cat "${CUSTOMER_ID_FILE}")
if [[ "$CID_VAL" == "USER_CUSTOMER_ID" ]]; then
    echo "PASS: Customer ID preserved"
else
    echo "FAIL: Customer ID NOT preserved (Got: $CID_VAL)"
    exit 1
fi

echo "ALL TESTS PASSED"
