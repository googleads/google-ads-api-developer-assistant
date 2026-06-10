# Copyright 2026 Google LLC
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

import os
import sys
import unittest
from unittest.mock import patch, mock_open

# Add scripts directory to sys.path
scripts_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../scripts")
)
sys.path.append(scripts_dir)

from get_extension_version import get_extension_version  # noqa: E402


class TestGetExtensionVersion(unittest.TestCase):

    def test_get_extension_version_success(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data='{"version": "3.0.0"}')), \
             patch("builtins.print") as mock_print:
            get_extension_version()
            mock_print.assert_called_once_with("3.0.0")

    def test_get_extension_version_missing_version_field(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data='{}')), \
             patch("builtins.print") as mock_print:
            get_extension_version()
            mock_print.assert_called_once_with("Version not found")

    def test_get_extension_version_file_not_found(self):
        # We need mock_open to raise FileNotFoundError when called
        m_open = mock_open()
        m_open.side_effect = FileNotFoundError()
        with patch("os.path.exists", return_value=False), \
             patch("builtins.open", m_open), \
             patch("sys.stderr.write"), \
             patch("sys.exit") as mock_exit:
            get_extension_version()
            mock_exit.assert_called_once_with(1)

    def test_get_extension_version_invalid_json(self):
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data='{invalid json')), \
             patch("sys.stderr.write"), \
             patch("sys.exit") as mock_exit:
            get_extension_version()
            mock_exit.assert_called_once_with(1)

    def test_get_extension_version_generic_exception(self):
        m_open = mock_open()
        m_open.side_effect = Exception("unexpected error")
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", m_open), \
             patch("sys.stderr.write"), \
             patch("sys.exit") as mock_exit:
            get_extension_version()
            mock_exit.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
