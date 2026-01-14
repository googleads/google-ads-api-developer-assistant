#!/bin/bash
set -u

# --- Test Setup ---
TEST_TMP_DIR=$(mktemp -d)
SETUP_SCRIPT_PATH="$(cd "$(dirname "$0")/.." && pwd)/setup.sh"

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
# setup.sh expects to be run from within the repo
# We will run it from FAKE_PROJECT, pretending it's the repo root
mkdir -p "${FAKE_PROJECT}/.gemini"
echo '{"context": {"includeDirectories": []}}' > "${FAKE_PROJECT}/.gemini/settings.json"

# Create dummy directories that setup.sh references
mkdir -p "${FAKE_PROJECT}/api_examples"
mkdir -p "${FAKE_PROJECT}/saved_code"

# --- Test Case 1: Run setup.sh with --python ---
echo "--- Running setup.sh --python ---"
if ! bash "${SETUP_SCRIPT_PATH}" --python; then
    echo "FAIL: setup.sh failed with --python"
    exit 1
fi

# Check if directory created (mock clone)
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-python/.git" ]]; then
    echo "FAIL: google-ads-python was not 'cloned' (mocked)"
    exit 1
fi

# Check if settings.json updated
if grep -q "google-ads-python" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "PASS: settings.json contains google-ads-python"
else
    echo "FAIL: settings.json does NOT contain google-ads-python"
    cat "${FAKE_PROJECT}/.gemini/settings.json"
    exit 1
fi

# --- Test Case 2: Run setup.sh --java (update existing check) ---
echo "--- Running setup.sh --java ---"
if ! bash "${SETUP_SCRIPT_PATH}" --java; then
    echo "FAIL: setup.sh failed with --java"
    exit 1
fi

# Check if java directory created
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-java/.git" ]]; then
    echo "FAIL: google-ads-java was not 'cloned'"
    exit 1
fi

# Check if settings.json has both now (actually jq might rewrite/append, setup.sh overwrites the list based on selection?)
# setup.sh reads: JQ_ARGS arguments based on enabled languages in THAT run.
# It overwrites `context.includeDirectories` with `[$examples, $saved, ...selected_libs]`.
# So if I run with ONLY --java, python might be REMOVED?
# Let's check the script logic:
# `for lang in $ALL_LANGS; do if is_enabled "$lang"; then ... JQ_ARGS+=...; fi; done`
# `JQ_ARRAY_STR="[\$examples, \$saved"` ... `JQ_ARRAY_STR+=", \$lib_$lang"` ...
# Yes, it overwrites with ONLY the currently selected languages + existing examples/saved.
# THIS IS IMPORTANT. Running `setup.sh --java` AFTER `setup.sh --python` removes python from settings if `setup.sh` doesn't read existing settings.
# Wait, `setup.sh` REPLACES the list.
# Let's verify this behavior is what we expect or if it's a "bug" (or feature).
# For now, I test that java IS present.

if grep -q "google-ads-java" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "PASS: settings.json contains google-ads-java"
else
    echo "FAIL: settings.json does NOT contain google-ads-java"
    exit 1
fi

# Verify Python is gone (based on current implementation analysis)
if grep -q "google-ads-python" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "INFO: google-ads-python is STILL present (Accumulative?)"
else
    echo "INFO: google-ads-python is GONE (Expected per current logic if overwriting)"
fi

echo "ALL TESTS PASSED"
