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
    # Mock clone: just create directory
    target="\$3"
    mkdir -p "\$target/.git"
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

# --- Test Case 1: Run install.sh ---
echo "--- Running install.sh ---"
if ! bash "${SETUP_SCRIPT_PATH}"; then
    echo "FAIL: install.sh failed"
    exit 1
fi

# Check if directory created (mock clone)
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-python/.git" ]]; then
    echo "FAIL: google-ads-python was not 'cloned' (mocked)"
    exit 1
fi

# Check that other languages are NOT cloned
for lang in php ruby java dotnet; do
    if [[ -d "${FAKE_PROJECT}/client_libs/google-ads-${lang}" ]]; then
        echo "FAIL: google-ads-${lang} was cloned but should not have been (default is Python only)"
        exit 1
    fi
done

# --- Test Case 2: Run install.sh --java ---
echo "--- Running install.sh --java ---"
if ! bash "${SETUP_SCRIPT_PATH}" --java; then
    echo "FAIL: install.sh failed with --java"
    exit 1
fi

# Check if java directory created
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-java/.git" ]]; then
    echo "FAIL: google-ads-java was not 'cloned'"
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
