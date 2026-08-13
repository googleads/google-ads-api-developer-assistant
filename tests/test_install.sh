#!/bin/bash
set -u

# --- Test Setup ---
TEST_TMP_DIR=$(mktemp -d)
SETUP_SCRIPT_PATH="$(cd "$(dirname "$0")/.." && pwd)/install.sh"

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

# Cleanup function
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
elif [[ "\$1" == "clone" ]]; then
    # Mock clone: just create directory and mock v25 structure
    target="\$3"
    mkdir -p "\$target/.git"
    mkdir -p "\$target/google/ads/googleads/v25"
    echo "Mock cloned into \$target"
elif [[ "\$1" == "pull" ]]; then
    echo "Mock pull successful"
else
    # Fallback to real git if needed, but avoiding it is safer
    echo "Mock git: command \$* ignored"
fi
EOF
chmod +x "${FAKE_HOME}/bin/git"

# Create mock jq if not present (unlikely, but safe)
if ! command -v jq &> /dev/null; then
    echo "jq not found, using mock implementation (this test prefers real jq)"
    # A simple mock might be too hard for the complex jq command used
    echo "FAIL: real jq is required for this test"
    exit 1
fi

# 2. Setup "Project" in Temp Dir
# install.sh expects to be run from within the repo
# We will run it from FAKE_PROJECT, pretending it's the repo root

# Create dummy directories that install.sh references
mkdir -p "${FAKE_PROJECT}/api_examples"
mkdir -p "${FAKE_PROJECT}/saved/code"
mkdir -p "${FAKE_PROJECT}/plugins/agy/client_libs/google-ads-python/google/ads/googleads/v25"
echo '{"name": "google-ads-api-developer-assistant"}' > "${FAKE_PROJECT}/plugins/agy/plugin.json"

# --- Test Case 1: Run install.sh without --type (Should Fail) ---
echo "--- Running install.sh without --type (Expected Failure) ---"
if bash "${SETUP_SCRIPT_PATH}" 2>/dev/null; then
    echo "FAIL: install.sh should have failed when missing --type"
    exit 1
fi

# --- Test Case 2: Run install.sh with invalid --type (Should Fail) ---
echo "--- Running install.sh with invalid --type (Expected Failure) ---"
if bash "${SETUP_SCRIPT_PATH}" --type invalid 2>/dev/null; then
    echo "FAIL: install.sh should have failed with invalid --type"
    exit 1
fi

# --- Test Case 3: Environment Check - Incompatible Python Version (Should Fail) ---
echo "--- Running install.sh with incompatible Python version (Expected Failure) ---"
cat > "${FAKE_HOME}/bin/python3" <<'EOF'
#!/bin/bash
if [[ "$*" == *"-c"* ]]; then
    echo "3.9.5"
    exit 1
fi
exit 0
EOF
chmod +x "${FAKE_HOME}/bin/python3"

cat > "${FAKE_HOME}/bin/python" <<'EOF'
#!/bin/bash
if [[ "$*" == *"-c"* ]]; then
    echo "3.9.5"
    exit 1
fi
exit 0
EOF
chmod +x "${FAKE_HOME}/bin/python"

if bash "${SETUP_SCRIPT_PATH}" --type project 2>/dev/null; then
    echo "FAIL: install.sh should have failed when Python < 3.10"
    exit 1
fi

# Restore mock python
rm -f "${FAKE_HOME}/bin/python3" "${FAKE_HOME}/bin/python"

# --- Test Case 4: Environment Check - Missing Antigravity (Should Fail) ---
echo "--- Running install.sh with missing Antigravity (Expected Failure) ---"
EMPTY_MOCK_HOME=$(mktemp -d)
CLEAN_PATH="${FAKE_HOME}/bin:/usr/bin:/bin"
if env -i PATH="${CLEAN_PATH}" HOME="${EMPTY_MOCK_HOME}" \
   bash "${SETUP_SCRIPT_PATH}" --type project 2>/dev/null; then
    echo "FAIL: install.sh should have failed when Antigravity is missing"
    rm -rf "${EMPTY_MOCK_HOME}"
    exit 1
fi
rm -rf "${EMPTY_MOCK_HOME}"

# --- Test Case 5: Run install.sh --type project ---
echo "--- Running install.sh --type project ---"
if ! bash "${SETUP_SCRIPT_PATH}" --type project; then
    echo "FAIL: install.sh failed with --type project"
    exit 1
fi

# Check if directory created (mock clone)
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-python/.git" ]]; then
    echo "FAIL: google-ads-python was not 'cloned' (mocked)"
    exit 1
fi

# Check that config/api_version.txt was pre-seeded with v25
if [[ ! -f "${FAKE_PROJECT}/config/api_version.txt" ]] || [[ "$(cat "${FAKE_PROJECT}/config/api_version.txt")" != "v25" ]]; then
    echo "FAIL: config/api_version.txt was not pre-seeded with v25"
    exit 1
fi

# Check that other languages are NOT cloned
for lang in php ruby java dotnet; do
    if [[ -d "${FAKE_PROJECT}/client_libs/google-ads-${lang}" ]]; then
        echo "FAIL: google-ads-${lang} was cloned but should not have been (default is Python only)"
        exit 1
    fi
done

# --- Test Case 4: Run install.sh --type project --java ---
echo "--- Running install.sh --type project --java ---"
if ! bash "${SETUP_SCRIPT_PATH}" --type project --java; then
    echo "FAIL: install.sh failed with --type project --java"
    exit 1
fi

# Check if java directory created
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-java/.git" ]]; then
    echo "FAIL: google-ads-java was not 'cloned'"
    exit 1
fi

# --- Test Case 5: Run install.sh --type plugin ---
echo "--- Running install.sh --type plugin ---"
if ! bash "${SETUP_SCRIPT_PATH}" --type plugin; then
    echo "FAIL: install.sh failed with --type plugin"
    exit 1
fi

# Check if plugin was copied to ~/.gemini/config/plugins/google_ads_assistant_plugin
if [[ ! -f "${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin/plugin.json" ]]; then
    echo "FAIL: plugin was not installed into ~/.gemini/config/plugins/google_ads_assistant_plugin"
    exit 1
fi

# Check that plugin config/api_version.txt was seeded
if [[ ! -f "${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin/config/api_version.txt" ]] || [[ "$(cat "${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin/config/api_version.txt")" != "v25" ]]; then
    echo "FAIL: plugin config/api_version.txt was not seeded with v25"
    exit 1
fi

# Check that non-selected client libraries are not in plugin client_libs
if [[ -d "${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin/client_libs/google-ads-java" ]]; then
    echo "FAIL: google-ads-java exists in plugin client_libs but was not requested"
    exit 1
fi

# --- Test Case 6: Run install.sh --type plugin --java ---
echo "--- Running install.sh --type plugin --java ---"
if ! bash "${SETUP_SCRIPT_PATH}" --type plugin --java; then
    echo "FAIL: install.sh failed with --type plugin --java"
    exit 1
fi

# Check if java library was added to plugin structure
if [[ ! -d "${FAKE_HOME}/.gemini/config/plugins/google_ads_assistant_plugin/client_libs/google-ads-java" ]]; then
    echo "FAIL: google-ads-java was not added to plugin client_libs"
    exit 1
fi

# Mock python
cat > "${FAKE_HOME}/bin/python" <<EOF
#!/bin/bash
if [[ "\$1" == "-m" ]] && [[ "\$2" == "pip" ]]; then
    echo "MOCK: python \$*" >> "${TEST_TMP_DIR}/install_log.txt"
else
    echo "Mock python: \$*"
fi
EOF
chmod +x "${FAKE_HOME}/bin/python"

# Mock composer
cat > "${FAKE_HOME}/bin/composer" <<EOF
#!/bin/bash
echo "MOCK: composer \$*" >> "${TEST_TMP_DIR}/install_log.txt"
EOF
chmod +x "${FAKE_HOME}/bin/composer"

# Mock bundle
cat > "${FAKE_HOME}/bin/bundle" <<EOF
#!/bin/bash
echo "MOCK: bundle \$*" >> "${TEST_TMP_DIR}/install_log.txt"
EOF
chmod +x "${FAKE_HOME}/bin/bundle"

# Create dummy composer.json and Gemfile for detection
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-php"
touch "${FAKE_PROJECT}/client_libs/google-ads-php/composer.json"
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-ruby"
touch "${FAKE_PROJECT}/client_libs/google-ads-ruby/Gemfile"




echo "ALL TESTS PASSED"

