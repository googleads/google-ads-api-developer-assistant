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

"""Unit tests for validate_conversion_upload skill script."""

import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)

import validate_conversion_upload


class TestValidateConversionUpload(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = os.path.join(self.temp_dir.name, "test_upload.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_validate_csv_success(self, mock_stdout) -> None:
        with open(self.csv_path, "w", encoding="utf-8") as f:
            f.write("gclid,conversion_time,conversion_value\n")
            f.write("12345678901234567890,2026-01-01 12:00:00-05:00,100.0\n")

        validate_conversion_upload.validate_conversion_csv(self.csv_path, "v24")
        output = mock_stdout.getvalue()
        self.assertIn("SUCCESS: Conversion Upload CSV parsed cleanly with valid formatting rules.", output)

    @mock.patch.object(sys, "stderr", new_callable=io.StringIO)
    def test_validate_csv_missing_file(self, mock_stderr) -> None:
        with self.assertRaises(SystemExit) as cm:
            validate_conversion_upload.validate_conversion_csv("non_existent.csv", "v24")
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("ERROR: CSV file not found at 'non_existent.csv'.", mock_stderr.getvalue())

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_validate_csv_invalid_date(self, mock_stdout) -> None:
        with open(self.csv_path, "w", encoding="utf-8") as f:
            f.write("gclid,conversion_time,conversion_value\n")
            f.write("12345678901234567890,invalid_date,100.0\n")

        with self.assertRaises(SystemExit) as cm:
            validate_conversion_upload.validate_conversion_csv(self.csv_path, "v24")
        self.assertEqual(cm.exception.code, 1)
        output = mock_stdout.getvalue()
        self.assertIn("ERROR: Invalid conversion_time format", output)


if __name__ == "__main__":
    unittest.main()
