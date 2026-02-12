#!/bin/bash

# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Description:
#   Integration tests for update.sh.

set -eu

# --- Environment Setup ---
# Create a temporary directory for tests
TEST_DIR=$(mktemp -d "/tmp/test_update_sh_XXXXXX")
trap 'rm -rf "${TEST_DIR}"' EXIT

echo "Running tests in ${TEST_DIR}"

FAKE_HOME="${TEST_DIR}/fake_home"
FAKE_PROJECT="${TEST_DIR}/fake_project"
mkdir -p "${FAKE_HOME}/bin"
mkdir -p "${FAKE_PROJECT}/.gemini"

# Resolve real script path before mocking git
REAL_UPDATE_SCRIPT="$(git rev-parse --show-toplevel)/update.sh"

# Mock git
cat > "${FAKE_HOME}/bin/git" <<EOF
#!/bin/bash
if [[ "\$1" == "rev-parse" ]]; then
    echo "${FAKE_PROJECT}"
elif [[ "\$1" == "clone" ]]; then
    target="\$3"
    mkdir -p "\$target/.git"
    echo "Mock cloned into \$target"
elif [[ "\$1" == "pull" ]]; then
    echo "Mock pull successful"
elif [[ "\$1" == "ls-files" ]]; then
    # Simulate file is tracked
    exit 0
elif [[ "\$1" == "checkout" ]]; then
    echo "Mock checkout successful"
else
    echo "Mock git: command \$* ignored"
fi
EOF
chmod +x "${FAKE_HOME}/bin/git"

# Mock jq
cat > "${FAKE_HOME}/bin/jq" <<EOF
#!/bin/bash
/usr/bin/jq "\$@"
EOF
chmod +x "${FAKE_HOME}/bin/jq"

# Add fake bin to PATH
export PATH="${FAKE_HOME}/bin:${PATH}"

# Create dummy settings.json
echo '{"context": {"includeDirectories": ["'"${FAKE_PROJECT}"'/client_libs/google-ads-python"]}}' > "${FAKE_PROJECT}/.gemini/settings.json"
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-python/.git"

# Copy the real update.sh for testing
UPDATE_SCRIPT_PATH="${FAKE_PROJECT}/update.sh"
cp "${REAL_UPDATE_SCRIPT}" "${UPDATE_SCRIPT_PATH}"
chmod +x "${UPDATE_SCRIPT_PATH}"

# --- Test Case 1: Run update.sh (no flags) ---
echo "--- Test Case 1: Default Update ---"
(cd "${FAKE_PROJECT}" && bash update.sh)

# Verify python was "updated"
# (Mock pull output would be in stdout, but the script continues if it works)

# --- Test Case 2: Run update.sh --php (Add new library) ---
echo "--- Test Case 2: Add PHP library ---"
(cd "${FAKE_PROJECT}" && bash update.sh --php)

# Check if php cloned
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-php/.git" ]]; then
    echo "FAIL: google-ads-php was not cloned"
    exit 1
fi

# Check if settings.json updated
if /usr/bin/jq -r '.context.includeDirectories[]' "${FAKE_PROJECT}/.gemini/settings.json" | grep -q "google-ads-php"; then
    echo "PASS: settings.json updated with php path"
else
    echo "FAIL: settings.json missing php path"
    cat "${FAKE_PROJECT}/.gemini/settings.json"
    exit 1
fi

# --- Test Case 3: Run update.sh --php (Already exists) ---
echo "--- Test Case 3: Update existing PHP library ---"
# We just run it again, it should not clone but pull (mock handled)
(cd "${FAKE_PROJECT}" && bash update.sh --php)
echo "PASS: update.sh --php ran successfully with existing lib"

echo "ALL TESTS PASSED"
