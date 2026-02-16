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
mkdir -p "${FAKE_PROJECT}/.gemini"
echo '{"context": {"includeDirectories": []}}' > "${FAKE_PROJECT}/.gemini/settings.json"

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

# Check if settings.json updated
if grep -q "google-ads-python" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "PASS: settings.json contains google-ads-python"
else
    echo "FAIL: settings.json does NOT contain google-ads-python"
    cat "${FAKE_PROJECT}/.gemini/settings.json"
    exit 1
fi

# Verify other languages are NOT in settings.json
for lang in php ruby java dotnet; do
    if grep -q "google-ads-${lang}" "${FAKE_PROJECT}/.gemini/settings.json"; then
        echo "FAIL: settings.json contains google-ads-${lang} but should not (default is Python only)"
        exit 1
    fi
done

# --- Test Case 2: Run install.sh --java (update existing check) ---
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

# Check if settings.json has both now (actually jq might rewrite/append, install.sh overwrites the list based on selection?)
# install.sh reads: JQ_ARGS arguments based on enabled languages in THAT run.
# It overwrites `context.includeDirectories` with `[$examples, $saved, ...selected_libs]`.
# So if I run with ONLY --java, python might be REMOVED?
# Let's check the script logic:
# `for lang in $ALL_LANGS; do if is_enabled "$lang"; then ... JQ_ARGS+=...; fi; done`
# `JQ_ARRAY_STR="[\$examples, \$saved"` ... `JQ_ARRAY_STR+=", \$lib_$lang"` ...
# Yes, it overwrites with ONLY the currently selected languages + existing examples/saved.
# THIS IS IMPORTANT. Running `install.sh --java` AFTER `install.sh --python` removes python from settings if `install.sh` doesn't read existing settings.
# Wait, `install.sh` REPLACES the list.
# Let's verify this behavior is what we expect or if it's a "bug" (or feature).
# For now, I test that java IS present.

if grep -q "google-ads-java" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "PASS: settings.json contains google-ads-java"
else
    echo "FAIL: settings.json does NOT contain google-ads-java"
    exit 1
fi

# Verify Python is present (Since Python is now always enabled)
if grep -q "google-ads-python" "${FAKE_PROJECT}/.gemini/settings.json"; then
    echo "INFO: google-ads-python is STILL present (Always enabled)"
else
    echo "FAIL: google-ads-python is GONE (It should always be present)"
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


# --- Test Case 3: Install Deps ---
echo "--- Running install.sh --php --ruby --install-deps ---"
# Clear log
rm -f "${TEST_TMP_DIR}/install_log.txt"

if ! bash "${SETUP_SCRIPT_PATH}" --php --ruby --install-deps; then
    echo "FAIL: install.sh failed with --install-deps"
    exit 1
fi

LOG_CONTENT=$(cat "${TEST_TMP_DIR}/install_log.txt" 2>/dev/null || true)
echo "Install Log Content:"
echo "$LOG_CONTENT"

if echo "$LOG_CONTENT" | grep -q "python -m pip install --upgrade google-ads"; then
    echo "PASS: python pip install detected"
else
    echo "FAIL: python pip install NOT detected"
    exit 1
fi

if echo "$LOG_CONTENT" | grep -q "composer install"; then
    echo "PASS: composer install detected"
else
    echo "FAIL: composer install NOT detected"
    exit 1
fi

if echo "$LOG_CONTENT" | grep -q "bundle install"; then
    echo "PASS: bundle install detected"
else
    echo "FAIL: bundle install NOT detected"
    exit 1
fi

# --- Test Case 4: No Install Deps (Verify NO install) ---
echo "--- Running install.sh --php --ruby (NO deps) ---"
rm -f "${TEST_TMP_DIR}/install_log.txt"

if ! bash "${SETUP_SCRIPT_PATH}" --php --ruby; then
    echo "FAIL: install.sh failed without --install-deps"
    exit 1
fi

if [[ -f "${TEST_TMP_DIR}/install_log.txt" ]]; then
    echo "FAIL: install_log.txt should not exist (or be empty) but found content:"
    cat "${TEST_TMP_DIR}/install_log.txt"
    exit 1
else
    echo "PASS: No install commands executed"
fi

echo "ALL TESTS PASSED"
