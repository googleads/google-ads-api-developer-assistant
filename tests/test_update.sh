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
mkdir -p "${FAKE_HOME}/.gemini/config/projects"
mkdir -p "${FAKE_PROJECT}/.agents"

# Resolve real script path before mocking git
REAL_ROOT=$(git rev-parse --show-toplevel)
REAL_UPDATE_SCRIPT="${REAL_ROOT}/update.sh"

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

# Add fake bin to PATH and export FAKE_HOME as HOME
export PATH="${FAKE_HOME}/bin:${PATH}"
export HOME="${FAKE_HOME}"

# Create dummy python repository structure under client_libs/
mkdir -p "${FAKE_PROJECT}/client_libs/google-ads-python/.git"

# Copy the real update.sh and helper script for testing
UPDATE_SCRIPT_PATH="${FAKE_PROJECT}/update.sh"
cp "${REAL_UPDATE_SCRIPT}" "${UPDATE_SCRIPT_PATH}"
chmod +x "${UPDATE_SCRIPT_PATH}"

cp "${REAL_ROOT}/update_project_context.py" "${FAKE_PROJECT}/update_project_context.py"

# Create fake virtual env python for script execution
mkdir -p "${FAKE_PROJECT}/.venv/bin"
ln -s "$(which python3)" "${FAKE_PROJECT}/.venv/bin/python3"

# Setup fake project configuration
cat > "${FAKE_HOME}/.gemini/config/projects/6039b1bb-7a20-43ad-b2b7-e64ce62a74ce.json" <<EOF
{
  "id": "6039b1bb-7a20-43ad-b2b7-e64ce62a74ce",
  "name": "${FAKE_PROJECT}",
  "projectResources": {
    "resources": [
      {
        "folderUri": "file://${FAKE_PROJECT}"
      }
    ]
  }
}
EOF

# --- Test Case 1: Run update.sh (no flags) ---
echo "--- Test Case 1: Default Update ---"
(cd "${FAKE_PROJECT}" && bash update.sh)

# --- Test Case 2: Run update.sh --php (Add new library) ---
echo "--- Test Case 2: Add PHP library ---"
(cd "${FAKE_PROJECT}" && bash update.sh --php)

# Check if php cloned
if [[ ! -d "${FAKE_PROJECT}/client_libs/google-ads-php/.git" ]]; then
    echo "FAIL: google-ads-php was not cloned"
    exit 1
fi

# --- Test Case 3: Run update.sh --php (Already exists) ---
echo "--- Test Case 3: Update existing PHP library ---"
# We just run it again, it should not clone but pull (mock handled)
(cd "${FAKE_PROJECT}" && bash update.sh --php)
echo "PASS: update.sh --php ran successfully with existing lib"

# --- Test Case 4: Run update.sh with valid context path ---
echo "--- Test Case 4: Add valid context path ---"
VALID_DIR="${TEST_DIR}/valid_dir"
mkdir -p "${VALID_DIR}"
(cd "${FAKE_PROJECT}" && bash update.sh --context_path "${VALID_DIR}")

# Verify it was added to json
if ! grep -q "valid_dir" "${FAKE_HOME}/.gemini/config/projects/6039b1bb-7a20-43ad-b2b7-e64ce62a74ce.json"; then
    echo "FAIL: valid_dir was not added to project configuration"
    exit 1
fi
echo "PASS: valid context path added"

# --- Test Case 5: Run update.sh with invalid context path ---
echo "--- Test Case 5: Add invalid context path ---"
INVALID_DIR="${TEST_DIR}/non_existent_dir"
if (cd "${FAKE_PROJECT}" && bash update.sh --context_path "${INVALID_DIR}" 2>/dev/null); then
    echo "FAIL: update.sh succeeded with non-existent context path"
    exit 1
fi
echo "PASS: invalid context path rejected"

echo "ALL TESTS PASSED"
